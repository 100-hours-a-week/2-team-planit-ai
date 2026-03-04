"""
PlaceSearchAgent: 멀티소스 장소 검색 에이전트

기존 인프라를 활용하여 여러 소스에서 장소 정보를 검색합니다:
1. SQLite (PoiAliasCache) - 이름 기반 빠른 조회
2. ChromaDB (VectorSearchAgent) - 시맨틱 벡터 검색
3. Google Maps (GoogleMapsPoiMapper) - 외부 API 검색
4. Tavily (TavilySearchTool) - 웹 검색
"""
import logging
from dataclasses import dataclass, field
from typing import List, Optional

from app.core.Agents.Chat.InfoAgent.TavilySearchTool import TavilySearchTool
from app.core.Agents.Poi.PoiAliasCache import PoiAliasCache
from app.core.Agents.Poi.PoiMapper.GoogleMapsPoiMapper import GoogleMapsPoiMapper
from app.core.Agents.Poi.VectorDB.VectorSearchAgent import VectorSearchAgent
from app.core.models.PoiAgentDataclass.poi import PoiCategory, PoiData, PoiInfo

logger = logging.getLogger(__name__)

MAX_VECTOR_RESULTS = 5
MAX_TAVILY_RESULTS = 3


@dataclass
class PlaceSearchResult:
    """장소 검색 통합 결과"""

    places: List[PoiData] = field(default_factory=list)
    tavily_summary: Optional[str] = None
    sources_used: List[str] = field(default_factory=list)

    def to_dict_list(self) -> List[dict]:
        """검색 결과를 dict 리스트로 변환 (ChatState.search_results 호환)"""
        results = []
        for poi in self.places:
            d = poi.model_dump(exclude_none=True)
            if "created_at" in d:
                d["created_at"] = str(d["created_at"])
            if "opening_hours" in d:
                d.pop("opening_hours", None)
            results.append(d)
        return results


class PlaceSearchAgent:
    """멀티소스 장소 검색 에이전트

    검색 전략 (비용 낮은 순):
    1. SQLite 별칭 캐시로 빠른 조회 시도
    2. VectorDB에서 시맨틱 검색
    3. 결과 부족 시 Google Maps API로 보충
    4. Tavily 웹 검색으로 추가 정보 수집
    """

    def __init__(
        self,
        alias_cache: Optional[PoiAliasCache] = None,
        vector_search: Optional[VectorSearchAgent] = None,
        google_mapper: Optional[GoogleMapsPoiMapper] = None,
        tavily_tool: Optional[TavilySearchTool] = None,
    ):
        self.alias_cache = alias_cache or PoiAliasCache()
        self.vector_search = vector_search
        self.google_mapper = google_mapper or GoogleMapsPoiMapper()
        self.tavily_tool = tavily_tool or TavilySearchTool()

    async def search(
        self,
        query: str,
        city: str,
        max_results: int = 5,
        use_web: bool = True,
    ) -> PlaceSearchResult:
        """멀티소스 장소 검색 수행

        Args:
            query: 검색 쿼리 (예: "도쿄 라멘 맛집", "시부야 카페")
            city: 도시명 (예: "도쿄", "오사카")
            max_results: 최대 결과 수
            use_web: Tavily 웹 검색 사용 여부

        Returns:
            PlaceSearchResult: 통합 검색 결과
        """
        result = PlaceSearchResult()
        found_place_ids: set = set()

        # 1. SQLite 별칭 캐시 조회
        sqlite_place_id = await self._search_sqlite(query, city)
        if sqlite_place_id and self.vector_search:
            result.sources_used.append("sqlite")
            poi_data = await self.vector_search.find_by_google_place_id(
                sqlite_place_id, city_filter=city
            )
            if poi_data:
                result.places.append(poi_data)
                found_place_ids.add(poi_data.google_place_id or poi_data.id)

        # 2. VectorDB 시맨틱 검색
        vector_results = await self._search_vector(query, city, max_results)
        if vector_results:
            result.sources_used.append("vector_db")
            for poi_data in vector_results:
                pid = poi_data.google_place_id or poi_data.id
                if pid not in found_place_ids:
                    result.places.append(poi_data)
                    found_place_ids.add(pid)

        # 3. Google Maps 검색 (로컬 DB에서 충분한 결과가 없을 때)
        if len(result.places) < max_results:
            gmaps_results = await self._search_google_maps(query, city)
            if gmaps_results:
                result.sources_used.append("google_maps")
                for poi_data in gmaps_results:
                    pid = poi_data.google_place_id or poi_data.id
                    if pid not in found_place_ids:
                        result.places.append(poi_data)
                        found_place_ids.add(pid)

        # 4. Tavily 웹 검색 (추가 정보)
        if use_web:
            tavily_summary = await self._search_tavily(query, city)
            if tavily_summary:
                result.sources_used.append("tavily")
                result.tavily_summary = tavily_summary

        # 결과 수 제한
        result.places = result.places[:max_results]

        logger.info(
            f"PlaceSearch 완료: query='{query}', city='{city}', "
            f"결과={len(result.places)}건, 소스={result.sources_used}"
        )

        return result

    async def _search_sqlite(self, query: str, city: str) -> Optional[str]:
        """SQLite 별칭 캐시에서 google_place_id 조회"""
        try:
            place_id = await self.alias_cache.find_by_name(query, city)
            if place_id:
                logger.info(f"SQLite 캐시 히트: '{query}' -> {place_id}")
            return place_id
        except Exception as e:
            logger.error(f"SQLite 검색 오류: {e}")
            return None

    async def _search_vector(
        self, query: str, city: str, k: int = MAX_VECTOR_RESULTS
    ) -> List[PoiData]:
        """VectorDB 시맨틱 검색"""
        if not self.vector_search:
            return []

        try:
            paired_results = await self.vector_search.search_by_text_with_data(
                query=query, k=k, city_filter=city
            )
            return [poi_data for _, poi_data in paired_results]
        except Exception as e:
            logger.error(f"VectorDB 검색 오류: {e}")
            return []

    async def _search_google_maps(
        self, query: str, city: str
    ) -> List[PoiData]:
        """Google Maps API로 장소 검색"""
        try:
            poi_info = PoiInfo(
                id="search_temp",
                name=query,
                category=PoiCategory.OTHER,
                description="",
                summary="검색 중",
            )
            poi_data = await self.google_mapper.map_poi(poi_info, city)
            if poi_data:
                return [poi_data]
            return []
        except Exception as e:
            logger.error(f"Google Maps 검색 오류: {e}")
            return []

    async def _search_tavily(self, query: str, city: str) -> Optional[str]:
        """Tavily로 웹 검색하여 텍스트 요약 반환"""
        try:
            search_query = f"{city} {query} 여행 추천" if city else f"{query} 여행 추천"
            response = await self.tavily_tool.search(
                query=search_query,
                include_answer=True,
                max_results=MAX_TAVILY_RESULTS,
            )
            return self.tavily_tool.format_results_as_text(response)
        except Exception as e:
            logger.error(f"Tavily 검색 오류: {e}")
            return None
