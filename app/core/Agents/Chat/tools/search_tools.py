"""
search_tools: 정보 검색 및 장소 추천 도구

ReAct 에이전트가 사용하는 검색 관련 도구들입니다.
"""
import logging
from typing import Optional

from langchain_core.tools import tool

from app.core.Agents.Chat.InfoAgent.PlaceSearchAgent import PlaceSearchAgent
from app.core.Agents.Chat.InfoAgent.TavilySearchTool import TavilySearchTool

logger = logging.getLogger(__name__)


def create_search_tools(
    tavily_tool: TavilySearchTool,
    place_search: PlaceSearchAgent,
) -> list:
    """검색 관련 도구 생성

    Args:
        tavily_tool: Tavily 검색 도구
        place_search: 멀티소스 장소 검색 에이전트

    Returns:
        list: 검색 관련 도구 함수 리스트
    """

    @tool
    async def search_travel_info(query: str) -> str:
        """여행 관련 일반 정보를 웹에서 검색합니다.

        날씨, 환율, 교통, 비자, 문화, 팁 등 여행 관련 정보를 검색합니다.

        Args:
            query: 검색 쿼리 (예: "도쿄 3월 날씨", "일본 환율")

        Returns:
            검색 결과 텍스트
        """
        try:
            response = await tavily_tool.search(
                query=query,
                include_answer=True,
                max_results=5,
            )
            return tavily_tool.format_results_as_text(response)
        except Exception as e:
            logger.error(f"여행 정보 검색 실패: {e}")
            return f"검색 중 오류가 발생했습니다: {str(e)}"

    @tool
    async def recommend_places(query: str, city: str = "") -> str:
        """여행지, 맛집, 카페, 관광지 등 장소를 추천합니다.

        VectorDB, Google Maps, 웹 검색을 활용하여 장소를 검색합니다.

        Args:
            query: 검색 쿼리 (예: "라멘 맛집", "벚꽃 명소", "카페 추천")
            city: 도시 이름 (예: "도쿄", "오사카"). 비어있으면 전체 검색

        Returns:
            추천 장소 목록 텍스트
        """
        try:
            result = await place_search.search(
                query=query,
                city=city,
                max_results=5,
                use_web=True,
            )

            if not result.places and not result.tavily_summary:
                return f"'{query}'에 대한 장소를 찾지 못했습니다."

            lines = [f"'{query}' 검색 결과 (소스: {', '.join(result.sources_used)}):"]

            for i, poi in enumerate(result.places, 1):
                name = poi.name or "이름 없음"
                category = poi.category.value if poi.category else ""
                rating = f" (평점: {poi.google_rating})" if poi.google_rating else ""
                address = f" - {poi.address}" if poi.address else ""
                description = ""
                if poi.description:
                    desc_text = poi.description[:100]
                    if len(poi.description) > 100:
                        desc_text += "..."
                    description = f"\n     {desc_text}"

                lines.append(
                    f"\n  {i}. {name} [{category}]{rating}{address}{description}"
                )

            if result.tavily_summary:
                lines.append(f"\n\n추가 정보:\n{result.tavily_summary[:500]}")

            return "\n".join(lines)

        except Exception as e:
            logger.error(f"장소 추천 실패: {e}")
            return f"장소 검색 중 오류가 발생했습니다: {str(e)}"

    return [search_travel_info, recommend_places]
