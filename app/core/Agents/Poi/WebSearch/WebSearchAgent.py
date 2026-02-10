import asyncio
import logging
from typing import List, Optional

from tavily import TavilyClient

from app.core.Agents.Poi.WebSearch.BaseWebSearchAgent import BaseWebSearchAgent
from app.core.Agents.Poi.WebSearch.Extractor import LangExtractor, JinaReader
from app.core.Agents.Poi.WebSearch.UrlCache import UrlCache
from app.core.models.PoiAgentDataclass.poi import PoiSearchResult, PoiSource, PoiSearchStats, PagePoiStats
from app.core.config import settings

logger = logging.getLogger(__name__)


class WebSearchAgent(BaseWebSearchAgent):
    """
    웹 검색 에이전트 구현

    Tavily API로 URL을 검색하고, Jina Reader로 본문을 추출한 뒤,
    Extractor를 통해 POI 정보를 구조적으로 추출합니다.
    URL 캐시를 통해 이미 추출한 URL은 재처리하지 않습니다.
    """

    def __init__(
        self,
        extractor: LangExtractor,
        jina_reader: JinaReader,
        num_results: int,
        base_url: str = "https://api.tavily.com",
        url_cache: Optional[UrlCache] = None,
    ):
        self.api_key = settings.tavily_api_key
        self.base_url = base_url
        if not self.api_key:
            raise ValueError("API 키가 없습니다.")
        self.client = TavilyClient(api_key=self.api_key)
        self.extractor = extractor
        self.jina_reader = jina_reader
        self.num_results = num_results
        self.url_cache = url_cache or UrlCache()

    async def search(
        self, 
        query: str, 
        destination: str = "",
        stats: Optional[PoiSearchStats] = None
    ) -> List[PoiSearchResult]:
        """
        단일 쿼리로 웹 검색 실행

        Flow: Tavily (URL 수집) → 캐시 확인 → Jina Reader (텍스트 추출) → Extractor (POI 추출)
        캐시에 있으면 Jina + Extractor를 건너뛰고 캐시 결과를 반환합니다.

        Args:
            query: 검색 쿼리
            destination: 여행지 (캐시 인덱싱용)
            stats: 통계 수집용 객체 (선택적)
        """

        if query is None or query == "":
            return []

        try:
            response = self.client.search(
                query=query,
                max_results=self.num_results,
                include_answer=False,
                include_images=False,
            )

            results = []
            seen_titles: set = set()
            for item in response.get("results", []):
                url = item.get("url")

                # Jina Reader + Extractor 파이프라인
                if url and self.extractor and self.jina_reader:
                    # 캐시 확인: 이미 추출한 URL이면 캐시 결과 사용
                    cached = self.url_cache.get(url, destination)
                    if cached is not None:
                        logger.info(f"URL 캐시 히트: {url}")
                        # 통계 수집: 캐시 히트
                        if stats is not None:
                            stats["cache_hit_pages"] = stats.get("cache_hit_pages", 0) + 1
                            # 캐시 히트 페이지도 통계에 기록
                            page_stat: PagePoiStats = {
                                "url": url,
                                "status": "cache",
                                "raw_count": len(cached),
                                "dup_count": 0,
                                "final_count": len(cached)
                            }
                            if "pages_poi_stats" not in stats:
                                stats["pages_poi_stats"] = []
                            stats["pages_poi_stats"].append(page_stat)
                        for poi in cached:
                            logger.info(f"추출된 POI: {poi.title}")
                        results.extend(cached)
                        continue

                    jina_text = await self.jina_reader.read(url)
                    if jina_text:
                        extracted = self.extractor.extract(
                            raw_content=jina_text['data']['content'],
                            url=url,
                        )
                        if extracted:
                            unique_extracted = []
                            raw_count = len(extracted)
                            for poi in extracted:
                                normalized = poi.title.strip().lower()
                                if normalized not in seen_titles:
                                    seen_titles.add(normalized)
                                    unique_extracted.append(poi)
                                    logger.info(f"추출된 POI: {poi.title}")
                                else:
                                    logger.info(f"title 중복 제거: {poi.title}")
                            # 통계 수집: 페이지별 POI 추출 통계
                            if stats is not None:
                                page_stat: PagePoiStats = {
                                    "url": url,
                                    "status": "success",
                                    "raw_count": raw_count,
                                    "dup_count": raw_count - len(unique_extracted),
                                    "final_count": len(unique_extracted)
                                }
                                if "pages_poi_stats" not in stats:
                                    stats["pages_poi_stats"] = []
                                stats["pages_poi_stats"].append(page_stat)
                            # 중복 제거된 결과를 캐시에 저장
                            self.url_cache.put(url, destination, unique_extracted)
                            results.extend(unique_extracted)
                            continue
                        else:
                            # 빈 결과: 통계에 기록
                            if stats is not None:
                                page_stat: PagePoiStats = {
                                    "url": url,
                                    "status": "empty",
                                    "raw_count": 0,
                                    "dup_count": 0,
                                    "final_count": 0
                                }
                                if "pages_poi_stats" not in stats:
                                    stats["pages_poi_stats"] = []
                                stats["pages_poi_stats"].append(page_stat)
                            # 빈 결과도 캐시에 저장하여 재시도 방지
                            self.url_cache.put(url, destination, [])
                    else:
                        # Jina Reader 실패: 통계에 기록
                        if stats is not None:
                            page_stat: PagePoiStats = {
                                "url": url,
                                "status": "jina_failed",
                                "raw_count": 0,
                                "dup_count": 0,
                                "final_count": 0
                            }
                            if "pages_poi_stats" not in stats:
                                stats["pages_poi_stats"] = []
                            stats["pages_poi_stats"].append(page_stat)
                        
                # 폴백: 기존 snippet 기반 로직
                result = PoiSearchResult(
                    title=item.get("title", ""),
                    snippet=item.get("content", ""),
                    url=url,
                    source=PoiSource.WEB_SEARCH,
                    relevance_score=item.get("score", 0.0)
                )
                results.append(result)

            return results

        except Exception as e:
            logger.error(f"Web search error: {e}")
            return []

    async def search_multiple(
        self,
        queries: List[str],
        destination: str = "",
        stats: Optional[PoiSearchStats] = None
    ) -> List[PoiSearchResult]:
        """
        여러 쿼리로 병렬 검색 후 결과 병합

        Args:
            queries: 검색 쿼리 리스트
            destination: 여행지 (캐시 인덱싱용)
            stats: 통계 수집용 객체 (선택적)
        """
        if not queries:
            return []

        # 통계: 키워드 목록 저장
        if stats is not None:
            stats["keywords"] = list(queries)
            stats["keyword_count"] = len(queries)

        # 병렬 검색 실행
        tasks = [
            self.search(query, destination=destination, stats=stats)
            for query in queries
        ]
        results_list = await asyncio.gather(*tasks)

        # 통계: 키워드별 페이지 수, 전체 페이지 수
        if stats is not None:
            pages_per_keyword = {}
            total_pages = 0
            for i, query in enumerate(queries):
                # 각 키워드 검색 결과에서 고유 URL 수 계산 (결과 기반 추정)
                if i < len(results_list):
                    page_count = len(set(r.url for r in results_list[i] if r.url))
                    pages_per_keyword[query] = page_count
                    total_pages += page_count
            stats["pages_per_keyword"] = pages_per_keyword
            stats["total_pages"] = total_pages

        # 결과 병합
        merged_results = [result for results in results_list for result in results]

        return merged_results
