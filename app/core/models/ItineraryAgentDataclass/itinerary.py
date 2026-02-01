"""
여행 일정 관련 데이터 모델

Transfer: POI 간 이동 정보
Itinerary: 하루 일정
ItineraryPlanState: LangGraph 상태
"""
from pydantic import BaseModel, Field
from typing import List, Optional, TypedDict
from enum import Enum

from app.core.models.PoiAgentDataclass.poi import PoiData


class TravelMode(str, Enum):
    """Google Maps API 지원 이동 수단"""
    DRIVING = "driving"
    WALKING = "walking"
    TRANSIT = "transit"
    BICYCLING = "bicycling"


class Transfer(BaseModel):
    """POI 간 이동 정보"""
    from_poi_id: str = Field(..., description="시작 POI ID")
    to_poi_id: str = Field(..., description="도착 POI ID")
    travel_mode: TravelMode = Field(default=TravelMode.WALKING, description="이동 수단")
    duration_minutes: int = Field(default=0, description="이동 시간(분)")
    distance_km: float = Field(default=0.0, description="거리(km)")


class ScheduledPoiEntry(BaseModel):
    """POI별 시간 배정 정보"""
    poi_id: str = Field(..., description="POI ID")
    start_time: str = Field(..., description="시작 시간 (HH:MM)")
    duration_minutes: int = Field(default=60, description="체류 시간 (분)")


class Itinerary(BaseModel):
    """하루 일정"""
    date: str = Field(..., description="날짜 (YYYY-MM-DD)")
    pois: List[PoiData] = Field(default_factory=list, description="POI 목록")
    schedule: List[ScheduledPoiEntry] = Field(default_factory=list, description="POI별 시간 배정 (pois와 1:1 대응)")
    transfers: List[Transfer] = Field(default_factory=list, description="이동 정보 (pois 개수 - 1)")
    total_duration_minutes: int = Field(default=0, description="총 소요 시간")
    
    def validate_transfers_count(self) -> bool:
        """Transfer 개수가 POI 개수 - 1인지 검증"""
        if len(self.pois) <= 1:
            return len(self.transfers) == 0
        return len(self.transfers) == len(self.pois) - 1


class ItineraryPlanState(TypedDict):
    """LangGraph 상태"""
    # 입력 데이터
    pois: List[PoiData]
    travel_destination: str
    travel_start_date: str
    travel_end_date: str
    total_budget: int
    persona_summary: str
    
    # 일정 데이터
    itineraries: List[Itinerary]
    
    # 피드백
    validation_feedback: Optional[str]
    schedule_feedback: Optional[str]
    
    # POI 충분성
    is_poi_sufficient: bool
    poi_enrich_attempts: int

    # 반복 제어
    iteration_count: int

    # 변경 감지용 필드
    previous_poi_ids: List[str]
    is_poi_changed: bool
    best_itineraries: Optional[List[Itinerary]]

    # Task Queue
    task_queue: List[str]
    current_task: Optional[str]
