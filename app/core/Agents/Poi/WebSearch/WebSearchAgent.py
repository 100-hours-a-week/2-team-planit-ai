import asyncio
import logging
from typing import List, Optional

from tavily import TavilyClient

from app.core.Agents.Poi.WebSearch.BaseWebSearchAgent import BaseWebSearchAgent
from app.core.Agents.Poi.WebSearch.Extractor import LangExtractor, JinaReader
from app.core.Agents.Poi.WebSearch.UrlCache import UrlCache
from app.core.models.PoiAgentDataclass.poi import PoiSearchResult, PoiSource
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

    async def search(self, query: str, destination: str = "") -> List[PoiSearchResult]:
        """
        단일 쿼리로 웹 검색 실행

        Flow: Tavily (URL 수집) → 캐시 확인 → Jina Reader (텍스트 추출) → Extractor (POI 추출)
        캐시에 있으면 Jina + Extractor를 건너뛰고 캐시 결과를 반환합니다.

        Args:
            query: 검색 쿼리
            destination: 여행지 (캐시 인덱싱용)
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
            for item in response.get("results", []):
                url = item.get("url")

                # Jina Reader + Extractor 파이프라인
                if url and self.extractor and self.jina_reader:
                    # 캐시 확인: 이미 추출한 URL이면 캐시 결과 사용
                    cached = self.url_cache.get(url, destination)
                    if cached is not None:
                        logger.info(f"URL 캐시 히트: {url}")
                        results.extend(cached)
                        continue

                    jina_text = await self.jina_reader.read(url)
                    if jina_text:
                        extracted = self.extractor.extract(
                            raw_content=jina_text['data']['content'],
                            url=url,
                        )
                        # 추출 결과를 캐시에 저장 (빈 결과도 저장하여 재시도 방지)
                        self.url_cache.put(url, destination, extracted or [])
                        if extracted:
                            results.extend(extracted)
                            continue

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
    ) -> List[PoiSearchResult]:
        """
        여러 쿼리로 병렬 검색 후 결과 병합

        Args:
            queries: 검색 쿼리 리스트
            destination: 여행지 (캐시 인덱싱용)
        """
        if not queries:
            return []

        # 병렬 검색 실행
        tasks = [
            self.search(query, destination=destination)
            for query in queries
        ]
        results_list = await asyncio.gather(*tasks)

        # 결과 병합 및 중복 제거
        seen_urls = set()
        # merged_results = []
        merged_results = [result for results in results_list for result in results]
        
        # print(results_list)
        # print(type(results_list))

        # for results in results_list:
        #     for result in results:
        #         try:
        #             if result.url and result.url not in seen_urls:
        #                 seen_urls.add(result.url)
        #                 merged_results.append(result)
        #             elif not result.url:
        #                 merged_results.append(result)
        #         except Exception as e:
        #             print(f"Error processing result: {e}")
                

        # 관련도 점수로 정렬
        # merged_results.sort(key=lambda x: x.relevance_score, reverse=True)

        return merged_results
