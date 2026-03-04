"""
ChatbotService: 챗봇 비즈니스 로직 서비스

백엔드에서 일정 조회 → Orchestrator로 메시지 처리 → 응답 반환.
일정 수정은 ScheduleChangeAgent의 CRUD 도구 내부에서 PATCH API를 호출합니다.
"""
import logging
from typing import Optional

from app.core.BackendClient import BackendClient
from app.core.Agents.Chat.Orchestrator import Orchestrator
from app.schemas.chatbot import ChatbotRequest, ChatbotResponse
from app.schemas.Itinerary import (
    ActivityResponse,
    DayItineraryResponse,
    ItineraryResponse,
)

logger = logging.getLogger(__name__)


class ChatbotService:
    """챗봇 서비스

    요청 흐름:
    1. BackendClient로 현재 일정 조회 (GET)
    2. 백엔드 응답을 ItineraryResponse로 변환
    3. Orchestrator 실행 (session_id = tripId)
    4. 응답 반환 (PATCH는 ScheduleChangeAgent 내부에서 처리됨)
    """

    def __init__(
        self,
        orchestrator: Orchestrator,
        backend_client: BackendClient,
    ):
        """
        Args:
            orchestrator: 대화 오케스트레이터
            backend_client: 백엔드 API 클라이언트
        """
        self.orchestrator = orchestrator
        self.backend_client = backend_client

    async def chat(self, request: ChatbotRequest) -> ChatbotResponse:
        """챗봇 메시지 처리

        Args:
            request: 챗봇 요청 (tripId, content, userJWT)

        Returns:
            ChatbotResponse: 챗봇 응답 (tripId, content)
        """
        # 1. 백엔드에서 현재 일정 조회
        current_itinerary = None
        backend_trip_data = None

        try:
            raw_response = await self.backend_client.get_itineraries(
                trip_id=request.tripId,
                user_jwt=request.userJWT,
            )
            backend_trip_data = raw_response.get("data", {})
            current_itinerary = self._convert_to_itinerary_response(
                backend_trip_data, request.tripId,
            )
            logger.info(
                f"일정 조회 완료: tripId={request.tripId}, "
                f"days={len(current_itinerary.itineraries)}"
            )
        except Exception as e:
            logger.warning(f"일정 조회 실패 (계속 진행): {e}")

        # 2. Orchestrator 실행 (session_id = tripId)
        result = await self.orchestrator.run(
            session_id=str(request.tripId),
            user_message=request.content,
            current_itinerary=current_itinerary,
            user_jwt=request.userJWT,
            backend_itinerary_data=backend_trip_data,
        )

        # 3. 응답 반환 (PATCH는 이미 CRUD 도구에서 처리됨)
        response_text = result.get("response", "")
        if not response_text:
            response_text = "요청을 처리했습니다."

        return ChatbotResponse(
            tripId=request.tripId,
            content=response_text,
        )

    @staticmethod
    def _convert_to_itinerary_response(
        trip_data: dict,
        trip_id: int,
    ) -> ItineraryResponse:
        """백엔드 GET 응답을 ItineraryResponse로 변환

        백엔드 형식:
            { tripId, title, startDate, endDate, itineraries: [
                { itineraryDayId, day, date, activities: [
                    { activityId, placeName, transport, type, eventOrder,
                      startTime, duration, cost, memo, googleMapUrl }
                ] }
            ] }

        → ItineraryResponse (기존 내부 형식)
        """
        itineraries_data = trip_data.get("itineraries", [])
        day_responses = []

        for itin in itineraries_data:
            activities = []
            for act in itin.get("activities", []):
                activities.append(ActivityResponse(
                    placeName=act.get("placeName"),
                    transport=act.get("transport"),
                    type=act.get("type", "attraction"),
                    eventOrder=act.get("eventOrder", 0),
                    startTime=act.get("startTime"),
                    duration=act.get("duration", 0),
                    cost=act.get("cost"),
                    memo=act.get("memo"),
                    googleMapUrl=act.get("googleMapUrl"),
                ))

            day_responses.append(DayItineraryResponse(
                day=itin.get("day", 0),
                date=itin.get("date", ""),
                activities=activities,
            ))

        return ItineraryResponse(
            tripId=trip_id,
            itineraries=day_responses,
        )
