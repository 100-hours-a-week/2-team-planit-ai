"""
ConsistencyChecker: 정합성 검사 통합 모듈

기존 ConstraintValidAgent(시간/예산), ScheduleAgent(균형)를 조합하여
변경된 일정의 정합성을 검증합니다.

기존 에이전트는 수정 없이 import하여 호출만 합니다.

NOTE: 기존 에이전트들은 Itinerary(도메인 모델)을 입력으로 받지만,
      챗봇 시스템은 ItineraryResponse(API 모델)을 사용합니다.
      따라서 ItineraryResponse → Itinerary 변환이 필요합니다.
"""
import logging
from typing import Optional

from app.core.Agents.ItineraryPlan.ConstraintValidAgent import ConstraintValidAgent
from app.core.Agents.ItineraryPlan.ScheduleAgent import ScheduleAgent
from app.core.models.ItineraryAgentDataclass.itinerary import Itinerary
from app.core.models.PoiAgentDataclass.poi import PoiData, PoiCategory, PoiSource
from app.schemas.Itinerary import (
    DayItineraryResponse,
    ItineraryResponse,
)

logger = logging.getLogger(__name__)

# 정합성 재시도 최대 횟수
MAX_CONSISTENCY_ATTEMPTS = 3


class ConsistencyChecker:
    """정합성 검사 통합기

    기존 ConstraintValidAgent(시간/예산)과 ScheduleAgent(일정 균형)를
    조합하여 정합성을 검증합니다.

    ItineraryResponse ↔ Itinerary 변환을 내부에서 처리합니다.
    """

    def __init__(
        self,
        total_budget: int = 1_000_000,
        travel_start_date: str = "",
        travel_end_date: str = "",
        max_daily_minutes: int = 12 * 60,
    ):
        """
        Args:
            total_budget: 총 예산 (원)
            travel_start_date: 여행 시작일 (YYYY-MM-DD)
            travel_end_date: 여행 종료일 (YYYY-MM-DD)
            max_daily_minutes: 하루 최대 활동 시간 (분)
        """
        self._constraint_agent = ConstraintValidAgent(
            max_daily_minutes=max_daily_minutes
        )
        self._schedule_agent = ScheduleAgent()
        self._total_budget = total_budget
        self._travel_start_date = travel_start_date
        self._travel_end_date = travel_end_date

    def check(
        self, itinerary_response: ItineraryResponse
    ) -> tuple[bool, Optional[str]]:
        """정합성 검사 실행

        Args:
            itinerary_response: 검사할 일정 (ItineraryResponse 형식)

        Returns:
            tuple[bool, Optional[str]]:
                - 정합성 통과 여부
                - 피드백 (통과 시 None)
        """
        # ItineraryResponse → List[Itinerary] 변환
        itineraries = _response_to_itineraries(itinerary_response)

        feedbacks = []

        # 1. 제약 조건 검증 (시간 / 예산 / 날짜)
        constraint_feedback = self._constraint_agent.validate(
            itineraries=itineraries,
            total_budget=self._total_budget,
            travel_start_date=self._travel_start_date,
            travel_end_date=self._travel_end_date,
        )
        if constraint_feedback:
            feedbacks.append(constraint_feedback)
            logger.info(f"제약 조건 피드백: {constraint_feedback}")

        # 2. 일정 균형 분석
        schedule_feedback = self._schedule_agent.analyze(
            itineraries=itineraries,
        )
        if schedule_feedback:
            feedbacks.append(schedule_feedback)
            logger.info(f"균형 피드백: {schedule_feedback}")

        if feedbacks:
            combined = "\n".join(feedbacks)
            return False, combined

        logger.info("정합성 검사 통과")
        return True, None


def _response_to_itineraries(
    response: ItineraryResponse,
) -> list[Itinerary]:
    """ItineraryResponse → List[Itinerary] 변환

    API 응답 모델을 도메인 모델로 변환합니다.
    ActivityResponse → PoiData (최소한의 필드만 매핑)
    """
    itineraries = []

    for day_itin in response.itineraries:
        pois = []
        total_minutes = 0

        for activity in day_itin.activities:
            if activity.type == "route":
                total_minutes += activity.duration
                continue

            # ActivityResponse → PoiData (최소 매핑)
            poi = PoiData(
                id=f"chat_poi_{day_itin.day}_{activity.eventOrder}",
                name=activity.placeName or "이름 없음",
                category=_map_type_to_category(activity.type),
                address="",
                source=PoiSource.USER_FEEDBACK,
                raw_text=activity.placeName or "이름 없음",
            )
            pois.append(poi)
            total_minutes += activity.duration

        itinerary = Itinerary(
            date=day_itin.date,
            pois=pois,
            total_duration_minutes=total_minutes,
        )
        itineraries.append(itinerary)

    return itineraries


def _map_type_to_category(activity_type: str) -> PoiCategory:
    """ActivityResponse.type → PoiCategory 매핑"""
    type_map = {
        "restaurant": PoiCategory.RESTAURANT,
        "cafe": PoiCategory.CAFE,
        "attraction": PoiCategory.ATTRACTION,
        "accommodation": PoiCategory.ACCOMMODATION,
        "shopping": PoiCategory.SHOPPING,
    }
    return type_map.get(activity_type, PoiCategory.ATTRACTION)
