from app.core.models.PoiAgentDataclass.poi import (
    PoiData,
    PoiSearchResult,
    PoiInfo,
    PoiCategory,
    PoiSource,
    PoiAgentState
)
from datetime import datetime


class TestPoiDataModels:
    """POI 데이터 모델 테스트"""
    
    def test_poi_category_enum(self):
        """PoiCategory Enum 값 확인"""
        assert PoiCategory.RESTAURANT.value == "restaurant"
        assert PoiCategory.CAFE.value == "cafe"
        assert PoiCategory.ATTRACTION.value == "attraction"
        assert PoiCategory.OTHER.value == "other"
    
    def test_poi_source_enum(self):
        """PoiSource Enum 값 확인"""
        assert PoiSource.WEB_SEARCH.value == "web_search"
        assert PoiSource.EMBEDDING_DB.value == "embedding_db"
        assert PoiSource.USER_FEEDBACK.value == "user_feedback"
    
    def test_poi_data_creation(self):
        """PoiData 모델 생성 테스트"""
        poi = PoiData(
            id="test-123",
            name="테스트 맛집",
            category=PoiCategory.RESTAURANT,
            description="맛있는 음식점입니다",
            address="서울시 강남구",
            source=PoiSource.WEB_SEARCH,
            source_url="https://example.com",
            raw_text="테스트 맛집. 맛있는 음식점입니다. 위치: 서울시 강남구"
        )
        
        assert poi.id == "test-123"
        assert poi.name == "테스트 맛집"
        assert poi.category == PoiCategory.RESTAURANT
        assert poi.source == PoiSource.WEB_SEARCH
        assert isinstance(poi.created_at, datetime)
    
    def test_poi_data_default_values(self):
        """PoiData 기본값 테스트"""
        poi = PoiData(
            id="test-456",
            name="기본값 테스트",
            source=PoiSource.WEB_SEARCH,
            raw_text="기본값 테스트"
        )
        
        assert poi.category == PoiCategory.OTHER
        assert poi.description == ""
        assert poi.address is None
        assert poi.source_url is None
    
    def test_poi_search_result_creation(self):
        """PoiSearchResult 모델 생성 테스트"""
        result = PoiSearchResult(
            poi_id="poi-123",
            title="검색 결과 제목",
            snippet="검색 결과 요약 텍스트",
            url="https://example.com/poi",
            source=PoiSource.EMBEDDING_DB,
            relevance_score=0.95
        )
        
        assert result.poi_id == "poi-123"
        assert result.title == "검색 결과 제목"
        assert result.source == PoiSource.EMBEDDING_DB
        assert result.relevance_score == 0.95
    
    def test_poi_search_result_default_values(self):
        """PoiSearchResult 기본값 테스트"""
        result = PoiSearchResult(
            title="최소 필드 테스트",
            snippet="요약",
            source=PoiSource.WEB_SEARCH
        )
        
        assert result.poi_id is None
        assert result.url is None
        assert result.relevance_score == 0.0
    
    def test_poi_info_creation(self):
        """PoiInfo 모델 생성 테스트"""
        poi_info = PoiInfo(
            id="info-123",
            name="추천 맛집",
            category=PoiCategory.RESTAURANT,
            summary="혼밥하기 좋은 분위기의 맛집입니다.",
            address="서울시 마포구",
            rating=4.5,
            price_level="중간",
            highlights=["혼밥 가능", "로컬 맛집", "저렴한 가격"]
        )
        
        assert poi_info.id == "info-123"
        assert poi_info.name == "추천 맛집"
        assert poi_info.rating == 4.5
        assert len(poi_info.highlights) == 3
        assert "혼밥 가능" in poi_info.highlights
    
    def test_poi_info_default_values(self):
        """PoiInfo 기본값 테스트"""
        poi_info = PoiInfo(
            id="info-456",
            name="기본값 테스트",
            category=PoiCategory.CAFE,
            summary="테스트 요약"
        )
        
        assert poi_info.address is None
        assert poi_info.rating is None
        assert poi_info.price_level is None
        assert poi_info.highlights == []
    
    def test_poi_agent_state_structure(self):
        """PoiAgentState TypedDict 구조 테스트 (리팩토링 반영)"""
        state: PoiAgentState = {
            "travel_destination": "서울",
            "persona_summary": "혼자 여행하는 20대, 로컬 음식 선호",
            "keywords": ["서울 혼밥 맛집", "서울 로컬 맛집"],
            "web_results": [],
            "embedding_results": [],
            "reranked_web_results": [],
            "reranked_embedding_results": [],
            "merged_results": [],
            "final_pois": []
        }
        
        assert state["persona_summary"] == "혼자 여행하는 20대, 로컬 음식 선호"
        assert len(state["keywords"]) == 2
        assert isinstance(state["web_results"], list)
        assert isinstance(state["reranked_web_results"], list)
