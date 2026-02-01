"""
Itinerary 응답 스키마 및 변환 함수

Itinerary 도메인 모델 → API 응답 형식 변환
"""
from pydantic import BaseModel
from typing import List, Optional

from app.core.models.ItineraryAgentDataclass.itinerary import Itinerary


class ActivityResponse(BaseModel):
    placeName: Optional[str] = None
    transport: Optional[str] = None
    type: str
    eventOrder: int
    startTime: Optional[str] = None
    duration: int = 0
    cost: Optional[int] = None
    memo: Optional[str] = None
    googleMapUrl: Optional[str] = None


class DayItineraryResponse(BaseModel):
    day: int
    date: str
    activities: List[ActivityResponse]


class ItineraryResponse(BaseModel):
    message: str = "SUCCESS"
    tripId: int
    itineraries: List[DayItineraryResponse]


def gen_itinerary(trip_id: int, itineraries: List[Itinerary]) -> ItineraryResponse:
    """Itinerary 도메인 모델 리스트를 API 응답 형식으로 변환한다.

    POI와 Transfer를 교차 배치하여 activities를 생성한다.
    예: [POI_A, Transfer_AB, POI_B, Transfer_BC, POI_C]

    Args:
        trip_id: 여행 ID
        itineraries: 일정 리스트 (하루 단위)

    Returns:
        ItineraryResponse: API 응답 Pydantic 모델
    """
    day_responses: List[DayItineraryResponse] = []

    for day_index, itinerary in enumerate(itineraries):
        activities: List[ActivityResponse] = []
        event_order = 1

        for poi_index, poi in enumerate(itinerary.pois):
            # schedule에서 시간 정보 추출
            if itinerary.schedule and poi_index < len(itinerary.schedule):
                entry = itinerary.schedule[poi_index]
                start_time = entry.start_time
                duration = entry.duration_minutes
            else:
                start_time = None
                duration = 0

            # POI 활동
            activities.append(ActivityResponse(
                placeName=poi.name,
                type=poi.category.value,
                eventOrder=event_order,
                startTime=start_time,
                duration=duration,
                googleMapUrl=poi.google_maps_uri,
            ))
            event_order += 1

            # POI 뒤에 Transfer 삽입 (마지막 POI 제외)
            if poi_index < len(itinerary.transfers):
                transfer = itinerary.transfers[poi_index]
                activities.append(ActivityResponse(
                    transport=transfer.travel_mode.value,
                    type="route",
                    eventOrder=event_order,
                    duration=transfer.duration_minutes,
                ))
                event_order += 1

        day_responses.append(DayItineraryResponse(
            day=day_index + 1,
            date=itinerary.date,
            activities=activities,
        ))

    return ItineraryResponse(
        tripId=trip_id,
        itineraries=day_responses,
    )
