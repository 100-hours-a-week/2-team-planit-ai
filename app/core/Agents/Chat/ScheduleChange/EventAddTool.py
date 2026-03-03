"""
EventAddTool: ItineraryResponse에 새 이벤트를 추가하는 도구

지정된 일차(day)와 위치(position)에 새 Activity를 삽입하고,
전후 route를 적절히 배치합니다.
검증된 장소 정보(resolved_place)를 사용하여 Activity를 생성할 수 있습니다.
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


class EventAddTool:
    """이벤트 추가 도구

    ItineraryResponse의 특정 일차에 새 이벤트를 삽입합니다.
    삽입 위치를 지정할 수 있으며, 기본적으로 마지막에 추가됩니다.
    """

    @staticmethod
    def add(
        itinerary: ItineraryResponse,
        day: int,
        activity: ActivityResponse,
        position: Optional[int] = None,
    ) -> tuple[ItineraryResponse, Optional[str]]:
        """이벤트 추가 실행

        Args:
            itinerary: 현재 일정 (원본은 수정하지 않음)
            day: 추가할 일차 (1-indexed)
            activity: 추가할 Activity
            position: 삽입 위치 (1-indexed, POI 기준). None이면 마지막에 추가

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
        poi_activities = _get_poi_activities(day_itin)

        # 삽입 위치 결정
        if position is None:
            # 마지막에 추가
            insert_idx = len(day_itin.activities)
        else:
            if position < 1 or position > len(poi_activities) + 1:
                return itinerary, (
                    f"{day}일차에는 {len(poi_activities)}개의 이벤트가 있습니다. "
                    f"1~{len(poi_activities) + 1} 위치 중 선택해주세요."
                )

            if position > len(poi_activities):
                insert_idx = len(day_itin.activities)
            else:
                target_poi = poi_activities[position - 1]
                insert_idx = day_itin.activities.index(target_poi)

        # 이벤트 삽입
        day_itin.activities.insert(insert_idx, activity)

        # route 정리
        _ensure_routes_between_pois(day_itin)

        # eventOrder 재정렬
        _reorder_events(day_itin)

        logger.info(
            f"이벤트 추가 완료: {day}일차 "
            f"'{activity.placeName}' (위치: {position or '마지막'})"
        )

        return modified, None

    @staticmethod
    def create_activity_from_resolved(
        resolved_place: dict,
        duration: int = 60,
        activity_type: str = "attraction",
    ) -> ActivityResponse:
        """검증된 장소 정보(resolved_place)로 ActivityResponse 생성

        poi_detail(VectorDB 상세 데이터)이 있으면 카테고리, URL, 평점 등을 활용합니다.

        Args:
            resolved_place: PlaceResolver의 결과 dict (poi_detail 포함 가능)
            duration: 체류 시간 (분)
            activity_type: 활동 타입 (poi_detail이 있으면 자동 결정)

        Returns:
            ActivityResponse: 생성된 Activity
        """
        place_name = resolved_place.get("place_name", "새 장소")
        google_place_id = resolved_place.get("google_place_id")
        poi_detail = resolved_place.get("poi_detail")

        # VectorDB 상세 데이터가 있으면 활용
        if poi_detail:
            # 카테고리 → activity type 매핑
            category = poi_detail.get("category", "")
            if category:
                activity_type = _category_to_type(category)

            # Google Maps URI (VectorDB에서 가져온 것 우선)
            google_map_url = poi_detail.get("google_maps_uri")

            # 이름 (VectorDB 이름 우선)
            place_name = poi_detail.get("name") or place_name

            # memo에 상세 정보 포함
            memo_parts = [f"챗봇에서 추가됨 (source: {resolved_place.get('source', 'unknown')})"]
            if poi_detail.get("google_rating"):
                memo_parts.append(f"평점: {poi_detail['google_rating']}")
            if poi_detail.get("address"):
                memo_parts.append(f"주소: {poi_detail['address']}")
            memo = " | ".join(memo_parts)
        else:
            # VectorDB 데이터 없으면 place_id 기반 URL 생성
            google_map_url = None
            if google_place_id:
                google_map_url = (
                    f"https://www.google.com/maps/place/"
                    f"?q=place_id:{google_place_id}"
                )
            memo = f"챗봇에서 추가됨 (source: {resolved_place.get('source', 'unknown')})"

        return ActivityResponse(
            placeName=place_name,
            type=activity_type,
            eventOrder=0,  # reorder에서 갱신
            duration=duration,
            googleMapUrl=google_map_url,
            memo=memo,
        )


def _category_to_type(category: str) -> str:
    """PoiCategory → ActivityResponse.type 매핑"""
    mapping = {
        "restaurant": "restaurant",
        "cafe": "cafe",
        "attraction": "attraction",
        "accommodation": "accommodation",
        "shopping": "shopping",
        "entertainment": "entertainment",
    }
    return mapping.get(category, "attraction")


def _get_poi_activities(
    day_itin: DayItineraryResponse,
) -> list[ActivityResponse]:
    """route가 아닌 POI 활동만 필터링"""
    return [a for a in day_itin.activities if a.type != "route"]


def _ensure_routes_between_pois(
    day_itin: DayItineraryResponse,
) -> None:
    """POI 사이에 route가 없으면 빈 route placeholder를 삽입"""
    activities = day_itin.activities
    if len(activities) <= 1:
        return

    i = 0
    while i < len(activities) - 1:
        current = activities[i]
        next_act = activities[i + 1]

        if current.type != "route" and next_act.type != "route":
            placeholder = ActivityResponse(
                type="route",
                eventOrder=0,
                duration=0,
                memo="이동 정보 미계산",
            )
            activities.insert(i + 1, placeholder)
            i += 2
        else:
            i += 1


def _reorder_events(day_itin: DayItineraryResponse) -> None:
    """eventOrder를 1부터 순차 재배치"""
    for i, activity in enumerate(day_itin.activities, 1):
        activity.eventOrder = i
