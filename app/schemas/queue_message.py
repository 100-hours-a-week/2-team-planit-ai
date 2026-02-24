"""
Redis Stream 메시지 스키마

결과(JobResult) 메시지 정의.
요청은 클라이언트가 개별 필드(tripId, payload, createdAt)로 전송하므로 별도 스키마 불필요.
"""
from pydantic import BaseModel
from typing import Optional

from app.schemas.Itinerary import ItineraryResponse


class JobResult(BaseModel):
    """Redis Stream 결과 메시지"""
    trip_id: str
    status: str  # "success" | "failed"
    result: Optional[ItineraryResponse] = None
    error: Optional[str] = None
