from pydantic import BaseModel, Field
from typing import Annotated, Dict, List, Optional, TypedDict
from datetime import datetime, time
from enum import Enum, IntEnum

DEFAULT_DISTANCE = 1.0
DEFAULT_DOCUMENT = None
DEFAULT_METADATA = None


class PoiValidationError(Exception):
    """Raised when POI cannot be validated via external API (e.g., Google Maps)."""
    pass

class PoiCategory(str, Enum):
    """POI 카테고리"""
    RESTAURANT = "restaurant"
    CAFE = "cafe"
    ATTRACTION = "attraction"
    ACCOMMODATION = "accommodation"
    SHOPPING = "shopping"
    ENTERTAINMENT = "entertainment"
    REGION = "region"
    OTHER = "other"


class PoiSource(str, Enum):
    """POI 데이터 출처"""
    WEB_SEARCH = "web_search"
    EMBEDDING_DB = "embedding_db"
    USER_FEEDBACK = "user_feedback"


class DayOfWeek(IntEnum):
    """요일 (ISO 8601 기준: 월=1, 일=7)"""
    MONDAY = 1
    TUESDAY = 2
    WEDNESDAY = 3
    THURSDAY = 4
    FRIDAY = 5
    SATURDAY = 6
    SUNDAY = 7


class TimeSlot(BaseModel):
    """시간 슬롯"""
    open_time: time = Field(..., description="오픈 시간")
    close_time: time = Field(..., description="마감 시간")
    
    def contains(self, check_time: time) -> bool:
        """주어진 시간이 이 슬롯 내에 있는지 확인"""
        # 자정 넘기는 경우 처리 (ex: 22:00 ~ 02:00)
        if self.open_time <= self.close_time:
            return self.open_time <= check_time <= self.close_time
        else:
            return check_time >= self.open_time or check_time <= self.close_time


class DailyOpeningHours(BaseModel):
    """하루 영업시간"""
    day: DayOfWeek = Field(..., description="요일")
    slots: List[TimeSlot] = Field(default_factory=list, description="영업 시간 슬롯")
    is_closed: bool = Field(default=False, description="휴무일 여부")
    
    def is_open_at(self, check_time: time) -> bool:
        """주어진 시간에 영업 중인지 확인"""
        if self.is_closed:
            return False
        return any(slot.contains(check_time) for slot in self.slots)


class OpeningHours(BaseModel):
    """주간 영업시간"""
    periods: List[DailyOpeningHours] = Field(default_factory=list, description="요일별 영업시간")
    raw_text: Optional[List[str]] = Field(None, description="원본 텍스트 (백업용)")
    
    def is_open_at(self, check_datetime: datetime) -> bool:
        """주어진 날짜/시간에 영업 중인지 확인"""
        day = DayOfWeek(check_datetime.isoweekday())
        check_time = check_datetime.time()
        
        for period in self.periods:
            if period.day == day:
                return period.is_open_at(check_time)
        
        return False
    
    def get_hours_for_day(self, day: DayOfWeek) -> Optional[DailyOpeningHours]:
        """특정 요일의 영업시간 반환"""
        for period in self.periods:
            if period.day == day:
                return period
        return None


class PoiData(BaseModel):
    """수집된 POI 원본 데이터 (Google Maps 연동)"""
    # 기본 필드
    id: str = Field(..., description="POI 고유 ID")
    name: str = Field(..., description="POI 이름")
    category: PoiCategory = Field(default=PoiCategory.OTHER, description="POI 카테고리")
    description: str = Field(default="", description="POI 설명")
    city: Optional[str] = Field(None, description="POI가 위치한 도시 (필터링용)")
    address: Optional[str] = Field(None, description="상세 주소")
    source: PoiSource = Field(..., description="데이터 출처")
    source_url: Optional[str] = Field(None, description="출처 URL")
    raw_text: str = Field(..., description="임베딩 생성용 원본 텍스트")
    created_at: datetime = Field(default_factory=datetime.now, description="생성 시간")
    
    # Google Maps 필드
    google_place_id: Optional[str] = Field(None, description="Google Place ID")
    latitude: Optional[float] = Field(None, description="위도")
    longitude: Optional[float] = Field(None, description="경도")
    google_maps_uri: Optional[str] = Field(None, description="구글맵 링크")
    types: List[str] = Field(default_factory=list, description="장소 유형")
    primary_type: Optional[str] = Field(None, description="주요 유형")
    
    # 상세 정보 (Enterprise SKU)
    google_rating: Optional[float] = Field(None, description="Google 평점")
    user_rating_count: Optional[int] = Field(None, description="리뷰 수")
    price_level: Optional[str] = Field(None, description="가격대")
    price_range: Optional[str] = Field(None, description="가격 범위 (최저 ~ 최고)")
    website_uri: Optional[str] = Field(None, description="공식 웹사이트")
    phone_number: Optional[str] = Field(None, description="전화번호")
    
    # 영업시간
    opening_hours: Optional[OpeningHours] = Field(None, description="영업시간")


class PoiSearchResult(BaseModel):
    """검색 결과 (웹/임베딩 통합)"""
    poi_id: Optional[str] = Field(None, description="POI ID (임베딩 검색 시)")
    title: str = Field(..., description="제목")
    snippet: str = Field(..., description="요약 텍스트")
    url: Optional[str] = Field(None, description="출처 URL")
    source: PoiSource = Field(..., description="검색 출처")
    relevance_score: float = Field(default=0.0, description="관련도 점수")


class PoiInfo(BaseModel):
    """최종 POI 정보"""
    id: str = Field(..., description="POI 고유 ID")
    name: str = Field(..., description="POI 이름")
    category: PoiCategory = Field(..., description="카테고리")
    description: str = Field(default="", description="POI 객관적 설명")
    summary: str = Field(..., description="페르소나 맞춤 추천 이유")
    address: Optional[str] = Field(None, description="주소")
    rating: Optional[float] = Field(None, description="평점")
    price_level: Optional[str] = Field(None, description="가격대")
    highlights: List[str] = Field(default_factory=list, description="주요 특징")


def _merge_poi_data_map(existing: Dict[str, "PoiData"], new: Dict[str, "PoiData"]) -> Dict[str, "PoiData"]:
    """poi_data_map 병합용 리듀서 (병렬 노드에서 동시 업데이트 지원)"""
    merged = {**(existing or {}), **(new or {})}
    return merged


class PoiAgentState(TypedDict):
    """LangGraph 상태"""
    travel_destination: str  # 사용자가 여행하는 지역
    persona_summary: str
    start_date: str
    end_date: str
    
    keywords: List[str]  # 페르소나에서 추출된 검색 키워드
    web_results: List[PoiSearchResult]
    embedding_results: List[PoiSearchResult]
    reranked_web_results: List[PoiSearchResult]  # 리랭킹된 웹 결과
    reranked_embedding_results: List[PoiSearchResult]  # 리랭킹된 임베딩 결과
    merged_results: List[PoiSearchResult]
    poi_data_map: Annotated[Dict[str, PoiData], _merge_poi_data_map]  # poi_id → PoiData 매핑
    final_poi_data: List[PoiData]  # 최종 반환용 PoiData 리스트
    final_pois: List[PoiInfo]
    final_poi_count: int

def _convert_poi_info_to_data(poi_info: PoiInfo, travel_destination: str) -> PoiData:
    """
    PoiInfo를 VectorDB 저장용 PoiData로 변환
    
    Args:
        poi_info: InfoSummarizeAgent에서 생성된 POI 정보
        travel_destination: 여행 도시 (필터링용)
    
    Returns:
        VectorDB 저장용 PoiData
    """
    # 임베딩용 텍스트 생성
    raw_text = f"{poi_info.name}."
    if poi_info.description:
        raw_text += f" {poi_info.description}"
    if poi_info.address:
        raw_text += f" 위치: {poi_info.address}"
    if poi_info.highlights:
        raw_text += f" 특징: {', '.join(poi_info.highlights)}"
    
    return PoiData(
        id=poi_info.id,
        name=poi_info.name,
        category=poi_info.category,
        description=poi_info.description,
        city=travel_destination,
        address=poi_info.address,
        source=PoiSource.WEB_SEARCH,
        source_url=None,
        raw_text=raw_text
    )