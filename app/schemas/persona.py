from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Union

class ItineraryRequest(BaseModel):
    tripId: int = Field(..., description="여행 ID")
    arrivalDate: str = Field(..., description="도착 날짜 (YYYY-MM-DD)")
    arrivalTime: str = Field(..., description="도착 시간 (HH:MM)")
    departureDate: str = Field(..., description="출발 날짜 (YYYY-MM-DD)")
    departureTime: str = Field(..., description="출발 시간 (HH:MM)")
    travelCity: str = Field(..., description="여행 도시")
    totalBudget: int = Field(..., description="총 예산")
    travelTheme: List[str] = Field(..., description="여행 테마 리스트")
    # companion: List[str] = Field(..., description="동반인 리스트")
    # pace: str = Field(..., description="여행 일정 밀도 (여유롭게/보통/빡빡하게 등)")
    wantedPlace: List[str] = Field(..., description="가고 싶은 장소 리스트")


