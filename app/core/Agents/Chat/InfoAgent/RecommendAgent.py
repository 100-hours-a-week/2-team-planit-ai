"""
RecommendAgent: 맞춤 추천 생성 에이전트

PlaceSearchAgent의 결과를 기반으로 사용자에게 맞춤 추천을 생성합니다.
LLM을 사용하여 검색된 장소 정보를 자연스러운 추천 텍스트로 변환합니다.
"""
import logging
from typing import Optional

from app.core.Agents.Chat.ChatState import ChatState
from app.core.Agents.Chat.InfoAgent.PlaceSearchAgent import (
    PlaceSearchAgent,
)
from app.core.LLMClient.BaseLlmClient import BaseLLMClient
from app.core.models.LlmClientDataclass.ChatMessageDataclass import (
    ChatMessage,
    MessageData,
)
from app.core.models.PoiAgentDataclass.poi import PoiData

logger = logging.getLogger(__name__)

RECOMMEND_SYSTEM_PROMPT = (
    "당신은 친절한 여행 추천 전문가입니다. "
    "검색된 장소 정보와 웹 검색 결과를 바탕으로 "
    "사용자에게 맞춤 추천을 제공합니다.\n"
    "- 각 장소의 특징과 추천 이유를 자연스럽게 설명하세요.\n"
    "- 평점, 가격대, 위치 등 유용한 정보를 포함하세요.\n"
    "- 한국어로 친근하게 답변하세요.\n"
    "- 추천 장소가 없으면 솔직하게 알려주세요."
)


class RecommendAgent:
    """맞춤 추천 생성 에이전트

    PlaceSearchAgent의 검색 결과와 사용자의 질문을 조합하여
    자연스러운 추천 응답을 생성합니다.
    """

    def __init__(
        self,
        llm_client: BaseLLMClient,
        place_search: PlaceSearchAgent,
    ):
        self.llm_client = llm_client
        self.place_search = place_search

    async def recommend(self, state: ChatState) -> dict:
        """추천 수행

        1. PlaceSearchAgent로 장소 검색
        2. 검색 결과를 LLM에 전달하여 추천 텍스트 생성

        Args:
            state: 현재 대화 상태

        Returns:
            dict: ChatState 업데이트 (search_results, response)
        """
        user_message = state.get("current_user_message", "")
        city = self._extract_city(state)

        # 1. 장소 검색
        search_result = await self.place_search.search(
            query=user_message,
            city=city,
        )

        search_dicts = search_result.to_dict_list()

        if not search_result.places and not search_result.tavily_summary:
            return {
                "search_results": [],
                "response": (
                    f"죄송합니다. '{user_message}'에 대한 추천 장소를 "
                    f"찾지 못했습니다. 다른 키워드로 다시 시도해주세요."
                ),
            }

        # 2. LLM으로 추천 텍스트 생성
        response_text = await self._generate_recommendation(
            user_message=user_message,
            places=search_result.places,
            tavily_summary=search_result.tavily_summary,
            city=city,
        )

        return {
            "search_results": search_dicts,
            "response": response_text,
        }

    async def _generate_recommendation(
        self,
        user_message: str,
        places: list[PoiData],
        tavily_summary: Optional[str],
        city: str,
    ) -> str:
        """LLM을 사용하여 추천 텍스트 생성"""
        places_info = self._format_places(places)

        web_info = ""
        if tavily_summary:
            web_info = f"\n\n[웹 검색 결과]\n{tavily_summary}"

        prompt = ChatMessage(content=[
            MessageData(
                role="system",
                content=RECOMMEND_SYSTEM_PROMPT,
            ),
            MessageData(
                role="user",
                content=(
                    f"사용자 질문: {user_message}\n"
                    f"도시: {city or '미지정'}\n\n"
                    f"[검색된 장소 정보]\n{places_info}"
                    f"{web_info}\n\n"
                    f"위 정보를 바탕으로 사용자에게 맞춤 추천을 해주세요."
                ),
            ),
        ])

        try:
            return await self.llm_client.call_llm(prompt)
        except Exception as e:
            logger.error(f"추천 생성 LLM 호출 실패: {e}")
            return self._fallback_response(places)

    @staticmethod
    def _format_places(places: list[PoiData]) -> str:
        """장소 목록을 LLM 프롬프트용 텍스트로 포맷"""
        if not places:
            return "검색된 장소 없음"

        texts = []
        for i, poi in enumerate(places, 1):
            lines = [f"{i}. {poi.name}"]
            if poi.category:
                lines[0] += f" ({poi.category.value})"
            if poi.address:
                lines.append(f"   주소: {poi.address}")
            if poi.description:
                lines.append(f"   설명: {poi.description}")
            if poi.google_rating:
                rating_text = f"   평점: {poi.google_rating}"
                if poi.user_rating_count:
                    rating_text += f" ({poi.user_rating_count}개 리뷰)"
                lines.append(rating_text)
            if poi.price_range:
                lines.append(f"   가격대: {poi.price_range}")
            if poi.editorial_summary:
                lines.append(f"   요약: {poi.editorial_summary}")
            if poi.review_summary:
                lines.append(f"   리뷰: {poi.review_summary[:200]}")
            texts.append("\n".join(lines))

        return "\n\n".join(texts)

    @staticmethod
    def _fallback_response(places: list[PoiData]) -> str:
        """LLM 실패 시 폴백 응답"""
        if places:
            items = "\n".join(
                f"- {poi.name} ({poi.address or '주소 미확인'})"
                for poi in places
            )
            return f"추천 장소:\n{items}"
        return "추천 장소를 찾지 못했습니다."

    @staticmethod
    def _extract_city(state: ChatState) -> str:
        """상태에서 도시 정보 추출

        ItineraryResponse에는 city 필드가 없으므로
        일정의 활동 장소명에서 추론하거나 빈 문자열을 반환합니다.
        """
        itinerary = state.get("current_itinerary")
        if not itinerary:
            return ""

        # ItineraryResponse.itineraries[0].date 등에서 도시를 직접 추출할 수 없으므로
        # 빈 문자열 반환 (향후 ChatState에 travel_city 필드 추가 시 활용)
        return ""
