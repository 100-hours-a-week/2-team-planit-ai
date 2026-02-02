"""
PoiEnrichAgent: POI 보충 에이전트

주요 기능:
- POI가 부족할 때 PoiGraph를 호출하여 추가 POI 생성
"""
from typing import List

from app.core.models.PoiAgentDataclass.poi import PoiData
from app.core.Agents.Poi.PoiGraph import PoiGraph


class PoiEnrichAgent:
    """POI 보충 에이전트 - PoiGraph 호출하여 추가 POI 생성"""

    # 기본 설정: 최소 POI 개수
    DEFAULT_MIN_POI_COUNT = 5

    def __init__(
        self,
        poi_graph: PoiGraph,
        min_poi_count: int = DEFAULT_MIN_POI_COUNT
    ):
        """
        Args:
            poi_graph: POI 검색 그래프
            min_poi_count: 최소 필요 POI 개수
        """
        self.poi_graph = poi_graph
        self.min_poi_count = min_poi_count

    def is_poi_sufficient(self, pois: List[PoiData]) -> bool:
        """
        POI 개수가 충분한지 확인

        Args:
            pois: 현재 POI 리스트

        Returns:
            충분 여부
        """
        return len(pois) >= self.min_poi_count

    async def enrich(
        self,
        current_pois: List[PoiData],
        persona_summary: str,
        travel_destination: str
    ) -> List[PoiData]:
        """
        POI 보충

        Args:
            current_pois: 현재 POI 리스트
            persona_summary: 사용자 페르소나
            travel_destination: 여행지

        Returns:
            보충된 POI 리스트 (기존 + 새로운)
        """
        # 기존 POI가 충분하면 그대로 반환
        if self.is_poi_sufficient(current_pois):
            return current_pois

        # 부족한 만큼 추가 POI 생성
        needed_count = self.min_poi_count - len(current_pois)

        # PoiGraph를 통해 추가 POI 검색 (List[PoiData] 반환)
        new_pois = await self.poi_graph.run(
            persona_summary=persona_summary,
            travel_destination=travel_destination
        )

        # 중복 제거 후 합치기
        existing_ids = {poi.id for poi in current_pois}
        unique_new_pois = [poi for poi in new_pois if poi.id not in existing_ids]

        # 필요한 만큼만 추가
        return current_pois + unique_new_pois[:needed_count]
