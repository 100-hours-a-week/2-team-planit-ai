from pydantic import BaseModel, Field
from typing import List, Optional, TypedDict
from datetime import datetime
from enum import Enum

DEFAULT_DISTANCE = 1.0
DEFAULT_DOCUMENT = None
DEFAULT_METADATA = None

class PoiCategory(str, Enum):
    """POI 카테고리"""
    RESTAURANT = "restaurant"
    CAFE = "cafe"
    ATTRACTION = "attraction"
    ACCOMMODATION = "accommodation"
    SHOPPING = "shopping"
    ENTERTAINMENT = "entertainment"
    OTHER = "other"


class PoiSource(str, Enum):
    """POI 데이터 출처"""
    WEB_SEARCH = "web_search"
    EMBEDDING_DB = "embedding_db"
    USER_FEEDBACK = "user_feedback"


class PoiData(BaseModel):
    """수집된 POI 원본 데이터"""
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


class PoiAgentState(TypedDict):
    """LangGraph 상태"""
    travel_destination: str  # 사용자가 여행하는 지역
    persona_summary: str
    keywords: List[str]  # 페르소나에서 추출된 검색 키워드
    web_results: List[PoiSearchResult]
    embedding_results: List[PoiSearchResult]
    reranked_web_results: List[PoiSearchResult]  # 리랭킹된 웹 결과
    reranked_embedding_results: List[PoiSearchResult]  # 리랭킹된 임베딩 결과
    merged_results: List[PoiSearchResult]
    final_pois: List[PoiInfo]

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