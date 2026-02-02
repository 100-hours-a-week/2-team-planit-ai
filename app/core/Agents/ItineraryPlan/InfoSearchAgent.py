"""
InfoSearchAgent: POI 정보 보충 에이전트

주요 기능:
- POI 정보가 부족할 때 웹 검색으로 보충
"""
from typing import List, Optional

from app.core.models.PoiAgentDataclass.poi import PoiData
from app.core.Agents.Poi.WebSearch.WebSearchAgent import WebSearchAgent


class InfoSearchAgent:
    """POI 정보 보충 에이전트 - 웹 검색으로 누락된 정보 보충"""

    def __init__(self, web_search_agent: Optional[WebSearchAgent] = None):
        """
        Args:
            web_search_agent: 웹 검색 에이전트 (None이면 새로 생성)
        """
        self.web_search = web_search_agent or WebSearchAgent()

    def needs_enrichment(self, poi: PoiData) -> bool:
        """
        POI 정보 보충이 필요한지 확인

        Args:
            poi: POI 정보

        Returns:
            보충 필요 여부
        """
        # 주소가 없거나 설명이 너무 짧으면 보충 필요
        if not poi.address:
            return True
        if len(poi.description) < 20:
            return True
        return False

    async def enrich_poi(self, poi: PoiData) -> PoiData:
        """
        단일 POI 정보 보충

        Args:
            poi: 보충할 POI

        Returns:
            보충된 POI
        """
        if not self.needs_enrichment(poi):
            return poi

        # 웹 검색으로 추가 정보 조회
        search_query = f"{poi.name} 주소 정보"
        search_results = await self.web_search.search(search_query)

        if search_results:
            # 첫 번째 검색 결과에서 정보 추출
            first_result = search_results[0]

            # 설명이 부족하면 보충
            description = poi.description
            if len(description) < 20 and first_result.snippet:
                description = first_result.snippet[:200]

            return poi.model_copy(update={"description": description})

        return poi

    async def enrich_pois(self, pois: List[PoiData]) -> List[PoiData]:
        """
        여러 POI 정보 일괄 보충

        Args:
            pois: POI 리스트

        Returns:
            보충된 POI 리스트
        """
        enriched = []
        for poi in pois:
            if self.needs_enrichment(poi):
                enriched_poi = await self.enrich_poi(poi)
                enriched.append(enriched_poi)
            else:
                enriched.append(poi)
        return enriched
