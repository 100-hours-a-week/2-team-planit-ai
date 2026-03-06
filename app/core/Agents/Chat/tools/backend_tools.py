"""
backend_tools: 백엔드 동기화 도구

일정 CRUD 도구 내부에서 자동으로 호출되므로,
이 도구는 동기화 실패 시 수동 재시도용입니다.
"""
import logging
from typing import Optional

from langchain_core.tools import tool

from app.core.BackendClient import BackendClient
from app.schemas.Itinerary import ItineraryResponse

logger = logging.getLogger(__name__)


def create_backend_tools(
    state_container: dict,
    backend_client: Optional[BackendClient] = None,
) -> list:
    """백엔드 동기화 도구 생성

    Args:
        state_container: 요청별 상태 컨테이너
        backend_client: 백엔드 API 클라이언트

    Returns:
        list: 백엔드 관련 도구 함수 리스트
    """

    @tool
    async def sync_to_backend(day: int) -> str:
        """특정 일차의 일정을 백엔드 서버에 동기화합니다.

        일정 CRUD 도구가 자동으로 백엔드에 반영하므로,
        이 도구는 동기화가 실패했을 때 수동으로 재시도할 때 사용합니다.

        Args:
            day: 동기화할 일차 (1-indexed)

        Returns:
            동기화 결과 메시지
        """
        if not backend_client:
            return "백엔드 클라이언트가 설정되어 있지 않습니다."

        itinerary: Optional[ItineraryResponse] = state_container.get("current_itinerary")
        if not itinerary:
            return "동기화할 일정이 없습니다."

        user_jwt = state_container.get("user_jwt")
        backend_data = state_container.get("backend_itinerary_data")

        if not user_jwt:
            return "인증 정보(JWT)가 없어 백엔드에 동기화할 수 없습니다."

        if not backend_data:
            return "백엔드 원본 데이터가 없어 동기화할 수 없습니다."

        try:
            backend_itineraries = backend_data.get("itineraries", [])
            if day < 1 or day > len(backend_itineraries):
                return (
                    f"유효하지 않은 일차입니다. "
                    f"1~{len(backend_itineraries)}일차 중 선택해주세요."
                )

            day_data = backend_itineraries[day - 1]
            day_id = day_data.get("itineraryDayId")

            if day_id is None:
                return "백엔드 데이터에서 itineraryDayId를 찾을 수 없습니다."

            from app.core.Agents.Chat.ScheduleChange.ScheduleChangeAgent import (
                ScheduleChangeAgent,
            )
            places = ScheduleChangeAgent._convert_to_patch_format(
                itinerary, day, day_data,
            )

            await backend_client.update_day_itinerary(
                trip_id=itinerary.tripId,
                day_id=day_id,
                places=places,
                user_jwt=user_jwt,
            )

            return f"{day}일차 일정이 백엔드에 성공적으로 동기화되었습니다."

        except Exception as e:
            logger.error(f"백엔드 동기화 실패: {e}")
            return f"백엔드 동기화 실패: {str(e)}"

    return [sync_to_backend]
