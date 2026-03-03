"""
EventDeleteTool: ItineraryResponse에서 이벤트를 삭제하는 도구

지정된 일차(day)와 이벤트 순서(event_index)에 해당하는
Activity를 제거하고, eventOrder를 재배치합니다.
전체일(all_day) 삭제도 지원합니다.
"""
import logging
from copy import deepcopy
from typing import Optional

from app.schemas.Itinerary import (
    ActivityResponse,
    DayItineraryResponse,
    ItineraryResponse,
)

logger = logging.getLogger(__name__)


class EventDeleteTool:
    """이벤트 삭제 도구

    ItineraryResponse에서 특정 일차의 특정 이벤트 또는 전체 이벤트를 삭제합니다.
    삭제 후 eventOrder를 재정렬하고, 인접한 route 활동도
    필요시 자동 제거합니다.
    """

    @staticmethod
    def delete(
        itinerary: ItineraryResponse,
        day: int,
        event_index: Optional[int] = None,
        target_scope: str = "single",
    ) -> tuple[ItineraryResponse, Optional[str]]:
        """이벤트 삭제 실행

        Args:
            itinerary: 현재 일정 (원본은 수정하지 않음)
            day: 삭제할 일차 (1-indexed)
            event_index: 해당 일차 내 이벤트 순서 (1-indexed, POI 기준). all_day면 무시
            target_scope: "single" (단건) 또는 "all_day" (전체일)

        Returns:
            tuple[ItineraryResponse, Optional[str]]:
                - 수정된 일정
                - 에러 메시지 (성공 시 None)
        """
        modified = deepcopy(itinerary)

        # 일차 유효성 검사
        if day < 1 or day > len(modified.itineraries):
            return itinerary, (
                f"유효하지 않은 일차입니다. "
                f"1~{len(modified.itineraries)}일차 중 선택해주세요."
            )

        day_itin = modified.itineraries[day - 1]

        # 전체일 삭제
        if target_scope == "all_day":
            return EventDeleteTool._delete_all_day(modified, day_itin, day)

        # 단건 삭제
        poi_activities = _get_poi_activities(day_itin)

        if event_index is None:
            return itinerary, "단건 삭제 시 event_index가 필요합니다."

        if event_index < 1 or event_index > len(poi_activities):
            return itinerary, (
                f"{day}일차에는 {len(poi_activities)}개의 이벤트가 있습니다. "
                f"1~{len(poi_activities)} 중 선택해주세요."
            )

        # 삭제할 POI의 실제 activities 인덱스 찾기
        target_poi = poi_activities[event_index - 1]
        target_idx = day_itin.activities.index(target_poi)

        # POI 삭제
        day_itin.activities.pop(target_idx)

        # 인접 route 제거
        _remove_orphan_routes(day_itin)

        # eventOrder 재정렬
        _reorder_events(day_itin)

        logger.info(
            f"이벤트 삭제 완료: {day}일차 {event_index}번째 "
            f"'{target_poi.placeName}'"
        )

        return modified, None

    @staticmethod
    def _delete_all_day(
        itinerary: ItineraryResponse,
        day_itin: DayItineraryResponse,
        day: int,
    ) -> tuple[ItineraryResponse, Optional[str]]:
        """해당 일차 전체 활동 삭제"""
        deleted_count = sum(
            1 for a in day_itin.activities if a.type != "route"
        )
        day_itin.activities.clear()

        logger.info(
            f"전체일 삭제 완료: {day}일차 ({deleted_count}개 이벤트 삭제)"
        )

        return itinerary, None


def _get_poi_activities(
    day_itin: DayItineraryResponse,
) -> list[ActivityResponse]:
    """route가 아닌 POI 활동만 필터링"""
    return [a for a in day_itin.activities if a.type != "route"]


def _remove_orphan_routes(day_itin: DayItineraryResponse) -> None:
    """연속된 route 또는 맨 앞/뒤의 lone route를 제거"""
    activities = day_itin.activities
    if not activities:
        return

    # 맨 앞이 route이면 제거
    while activities and activities[0].type == "route":
        activities.pop(0)

    # 맨 뒤가 route이면 제거
    while activities and activities[-1].type == "route":
        activities.pop()

    # 연속 route 제거
    cleaned = []
    prev_is_route = False
    for act in activities:
        if act.type == "route":
            if prev_is_route:
                continue
            prev_is_route = True
        else:
            prev_is_route = False
        cleaned.append(act)

    day_itin.activities = cleaned


def _reorder_events(day_itin: DayItineraryResponse) -> None:
    """eventOrder를 1부터 순차 재배치"""
    for i, activity in enumerate(day_itin.activities, 1):
        activity.eventOrder = i
