from fastapi import APIRouter, Depends
import time

from app.schemas.persona import ItineraryRequest
from app.schemas.Itinerary import ItineraryResponse
from app.service.Ininerary.gen_init_Ininerary import GenInitItineraryService
from app.api.deps import get_gen_itinerary_service

router = APIRouter(prefix="/itinerary", tags=["Itinerary"])


@router.post("/gen", response_model=ItineraryResponse)
async def gen_itinerary_endpoint(
    request: ItineraryRequest,
    service: GenInitItineraryService = Depends(get_gen_itinerary_service),
):
    return await service.gen_init_itinerary(request)


@router.post("")
def gen_itinerary_dummy(request: ItineraryRequest):
    """더미 응답을 반환하는 테스트 엔드포인트"""
    time.sleep(10)
    return {
        "message": "SUCCESS",
        "tripId": request.tripId,
        "itineraries": [
            {
                "day": 1,
                "date": "2026-01-06",
                "activities": [
                    {
                        "placeName": "맛집 A",
                        "transport": None,
                        "type": "restaurant",
                        "eventOrder": 1,
                        "startTime": "12:00",
                        "duration": 120,
                        "cost": 10000,
                        "memo": "점심 식사",
                        "googleMapUrl": "https://maps.google.com/example1",
                    },
                    {
                        "placeName": None,
                        "transport": "bus",
                        "type": "route",
                        "eventOrder": 2,
                        "startTime": "14:00",
                        "duration": 30,
                        "cost": None,
                        "memo": None,
                        "googleMapUrl": None,
                    },
                    {
                        "placeName": "관광지 B",
                        "transport": None,
                        "type": "attraction",
                        "eventOrder": 3,
                        "startTime": "14:30",
                        "duration": 120,
                        "cost": 10000,
                        "memo": "메모 내용",
                        "googleMapUrl": "https://maps.google.com/example2",
                    },
                ],
            },
            {
                "day": 2,
                "date": "2026-01-07",
                "activities": [
                    {
                        "placeName": "카페 C",
                        "transport": None,
                        "type": "restaurant",
                        "eventOrder": 1,
                        "startTime": "09:00",
                        "duration": 60,
                        "cost": 5000,
                        "memo": "아침 커피",
                        "googleMapUrl": "https://maps.google.com/example3",
                    },
                    {
                        "placeName": None,
                        "transport": "walk",
                        "type": "route",
                        "eventOrder": 2,
                        "startTime": "10:00",
                        "duration": 15,
                        "cost": None,
                        "memo": None,
                        "googleMapUrl": None,
                    },
                    {
                        "placeName": "박물관 D",
                        "transport": None,
                        "type": "attraction",
                        "eventOrder": 3,
                        "startTime": "10:15",
                        "duration": 180,
                        "cost": 15000,
                        "memo": "전시 관람",
                        "googleMapUrl": "https://maps.google.com/example4",
                    },
                ],
            },
        ],
    }


@router.post("/{trip_id}")
def get_itinerary(trip_id: int):
    time.sleep(10)
    return {
        "message": "SUCCESS",
        "tripId": trip_id,
        "itineraries": [
            {
                "day": 1,
                "date": "2026-01-06",
                "activities": [
                    {
                        "placeName": "맛집 A",
                        "transport": None,
                        "type": "restaurant",
                        "eventOrder": 1,
                        "startTime": "12:00",
                        "duration": 120,
                        "cost": 10000,
                        "memo": "점심 식사",
                        "googleMapUrl": "https://maps.google.com/example1",
                    },
                    {
                        "placeName": None,
                        "transport": "bus",
                        "type": "route",
                        "eventOrder": 2,
                        "startTime": "14:00",
                        "duration": 30,
                        "cost": None,
                        "memo": None,
                        "googleMapUrl": None,
                    },
                    {
                        "placeName": "관광지 B",
                        "transport": None,
                        "type": "attraction",
                        "eventOrder": 3,
                        "startTime": "14:30",
                        "duration": 120,
                        "cost": 10000,
                        "memo": "메모 내용",
                        "googleMapUrl": "https://maps.google.com/example2",
                    },
                ],
            },
            {
                "day": 2,
                "date": "2026-01-07",
                "activities": [
                    {
                        "placeName": "카페 C",
                        "transport": None,
                        "type": "restaurant",
                        "eventOrder": 1,
                        "startTime": "09:00",
                        "duration": 60,
                        "cost": 5000,
                        "memo": "아침 커피",
                        "googleMapUrl": "https://maps.google.com/example3",
                    },
                    {
                        "placeName": None,
                        "transport": "walk",
                        "type": "route",
                        "eventOrder": 2,
                        "startTime": "10:00",
                        "duration": 15,
                        "cost": None,
                        "memo": None,
                        "googleMapUrl": None,
                    },
                    {
                        "placeName": "박물관 D",
                        "transport": None,
                        "type": "attraction",
                        "eventOrder": 3,
                        "startTime": "10:15",
                        "duration": 180,
                        "cost": 15000,
                        "memo": "전시 관람",
                        "googleMapUrl": "https://maps.google.com/example4",
                    },
                ],
            },
        ],
    }
