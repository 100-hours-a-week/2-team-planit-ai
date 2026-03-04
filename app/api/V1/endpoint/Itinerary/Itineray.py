from fastapi import APIRouter, Depends
import json
import time

from app.schemas.persona import ItineraryRequest
from app.schemas.Itinerary import ItineraryResponse
from app.service.Ininerary.gen_init_Ininerary import GenInitItineraryService
from app.api.deps import get_gen_itinerary_service
from app.core.redis_client import RedisClient
from app.core.config import settings

router = APIRouter(prefix="/itinerary", tags=["Itinerary"])


@router.post("", response_model=ItineraryResponse)
async def gen_itinerary_endpoint(
    request: ItineraryRequest,
    service: GenInitItineraryService = Depends(get_gen_itinerary_service),
):
    return await service.gen_init_itinerary(request)


@router.post("/gen_dummy_redis")
async def gen_dummy_to_redis(request: ItineraryRequest):
    """Redis 완료큐(stream:itinerary-results)에 더미 결과를 push하는 테스트 엔드포인트"""
    dummy_response = {
        "message": "SUCCESS",
        "tripId": request.tripId,
        "itineraries": [
            {
                "day": 1,
                "date": "2026-03-01",
                "activities": [
                    {
                        "placeName": "도톤보리",
                        "type": "attraction",
                        "eventOrder": 1,
                        "startTime": "10:00",
                        "duration": 120,
                        "cost": 0,
                        "memo": "오사카의 대표 관광지",
                        "googleMapUrl": "https://maps.google.com/?cid=17238952707303622496",
                    },
                    {
                        "placeName": None,
                        "transport": "walk",
                        "type": "route",
                        "eventOrder": 2,
                        "startTime": "12:00",
                        "duration": 15,
                    },
                    {
                        "placeName": "이치란 라멘 도톤보리점",
                        "type": "restaurant",
                        "eventOrder": 3,
                        "startTime": "12:15",
                        "duration": 60,
                        "cost": 15000,
                        "memo": "점심 식사",
                        "googleMapUrl": "https://maps.google.com/?cid=2565965656862750409",
                    },
                ],
            },
            {
                "day": 2,
                "date": "2026-03-02",
                "activities": [
                    {
                        "placeName": "오사카성",
                        "type": "attraction",
                        "eventOrder": 1,
                        "startTime": "09:00",
                        "duration": 180,
                        "cost": 10000,
                        "memo": "오사카성 천수각 관람",
                        "googleMapUrl": "https://maps.google.com/?cid=1955127484666331742",
                    },
                    {
                        "placeName": None,
                        "transport": "subway",
                        "type": "route",
                        "eventOrder": 2,
                        "startTime": "12:00",
                        "duration": 30,
                    },
                    {
                        "placeName": "쿠로몬 시장",
                        "type": "attraction",
                        "eventOrder": 3,
                        "startTime": "12:30",
                        "duration": 120,
                        "cost": 30000,
                        "memo": "해산물 먹방 투어",
                        "googleMapUrl": "https://maps.google.com/?cid=7785923974874169613",
                    },
                ],
            },
        ],
    }

    # Redis 완료큐에 push (워커와 동일한 필드 포맷)
    r = await RedisClient.get_instance()
    await r.xadd(
        settings.redis_result_stream,
        {
            "tripId": str(request.tripId),
            "status": "SUCCESS",
            "payload": json.dumps(dummy_response, ensure_ascii=False),
        },
        maxlen=settings.redis_max_stream_len,
    )

    return {
        "message": "더미 결과가 Redis 완료큐에 push되었습니다.",
        "stream": settings.redis_result_stream,
        "tripId": request.tripId,
    }

@router.post("/gen_dummy")
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
                        "googleMapUrl": "https://maps.google.com/?cid=17238952707303622496&g_mp=Cidnb29nbGUubWFwcy5wbGFjZXMudjEuUGxhY2VzLlNlYXJjaFRleHQQAhgEIAA",
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
                        "googleMapUrl": "https://maps.google.com/?cid=2565965656862750409&g_mp=Cidnb29nbGUubWFwcy5wbGFjZXMudjEuUGxhY2VzLlNlYXJjaFRleHQQAhgEIAA",
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
                        "googleMapUrl": "https://maps.google.com/?cid=1955127484666331742&g_mp=Cidnb29nbGUubWFwcy5wbGFjZXMudjEuUGxhY2VzLlNlYXJjaFRleHQQAhgEIAA",
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
                        "googleMapUrl": "https://maps.google.com/?cid=7785923974874169613&g_mp=Cidnb29nbGUubWFwcy5wbGFjZXMudjEuUGxhY2VzLlNlYXJjaFRleHQQAhgEIAA",
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
                        "googleMapUrl": "https://maps.google.com/?cid=17238952707303622496&g_mp=Cidnb29nbGUubWFwcy5wbGFjZXMudjEuUGxhY2VzLlNlYXJjaFRleHQQAhgEIAA",
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
                        "googleMapUrl": "https://maps.google.com/?cid=2565965656862750409&g_mp=Cidnb29nbGUubWFwcy5wbGFjZXMudjEuUGxhY2VzLlNlYXJjaFRleHQQAhgEIAA",
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
