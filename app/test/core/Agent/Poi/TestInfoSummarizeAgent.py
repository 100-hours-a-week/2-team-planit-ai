import pytest
from unittest.mock import AsyncMock, MagicMock
from app.core.Agents.Poi.InfoSummaizeAgent import InfoSummarizeAgent
from app.core.models.PoiAgentDataclass.poi import PoiSearchResult, PoiInfo, PoiSource, PoiCategory

# =============================================================================
# 단위 테스트: 모든 의존성 Mock 사용
# =============================================================================
class TestInfoSummarizeAgentUnit:
    """InfoSummarizeAgent 단위 테스트 (Mock LLM 사용)"""
    
    @pytest.fixture
    def mock_llm_client(self):
        """Mock LLM Client 생성"""
        client = MagicMock()
        client.call_llm = AsyncMock()
        return client
    
    @pytest.fixture
    def summarizer(self, mock_llm_client):
        """InfoSummarizeAgent 인스턴스 생성"""
        return InfoSummarizeAgent(mock_llm_client)
    
    @pytest.fixture
    def sample_results(self):
        """샘플 검색 결과"""
        return [
            PoiSearchResult(
                title="테스트 맛집 1",
                snippet="맛있는 음식점입니다.",
                url="https://example.com/1",
                source=PoiSource.WEB_SEARCH,
                relevance_score=0.9
            ),
            PoiSearchResult(
                title="테스트 카페 1",
                snippet="분위기 좋은 카페입니다.",
                url="https://example.com/2",
                source=PoiSource.WEB_SEARCH,
                relevance_score=0.8
            )
        ]
    
    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_summarize_empty_results(self, summarizer):
        """빈 결과 처리 테스트"""
        result = await summarizer.summarize(merged_results=[])
        assert result == []
    
    @pytest.mark.unit
    def test_format_results(self, summarizer, sample_results):
        """_format_results 테스트"""
        formatted = summarizer._format_results(sample_results)
        
        assert isinstance(formatted, str)
        assert "<title>테스트 맛집 1</title>" in formatted
        assert "<content>맛있는 음식점입니다.</content>" in formatted
        assert "<title>테스트 카페 1</title>" in formatted
        assert "<content>분위기 좋은 카페입니다.</content>" in formatted
    
    @pytest.mark.unit
    def test_parse_poi_list(self, summarizer):
        """_parse_poi_list 테스트"""
        response = """
        <poi_list>
        <poi>
        <name>테스트 맛집</name>
        <category>restaurant</category>
        <description>맛있는 음식점입니다.</description>
        <summary>좋은 맛집입니다</summary>
        <address>서울특별시 중구</address>
        <highlights>특징1, 특징2</highlights>
        </poi>
        </poi_list>
        """
        
        result = summarizer._parse_poi_list(response)
        
        assert len(result) == 1
        assert isinstance(result[0], PoiInfo)
        assert result[0].name == "테스트 맛집"
        assert result[0].category == PoiCategory.RESTAURANT
        assert result[0].description == "맛있는 음식점입니다."
        assert result[0].summary == "좋은 맛집입니다"
        assert result[0].address == "서울특별시 중구"
        assert result[0].highlights == ["특징1", "특징2"]
    
    @pytest.mark.unit
    def test_parse_single_poi(self, summarizer):
        """_parse_single_poi 테스트"""
        poi_text = """
        <name>카페 테스트</name>
        <category>cafe</category>
        <summary>조용한 카페입니다</summary>
        <highlights>조용함, 커피 맛있음, 디저트</highlights>
        """
        
        result = summarizer._parse_single_poi(poi_text)
        
        assert result.name == "카페 테스트"
        assert result.category == PoiCategory.CAFE
        assert result.summary == "조용한 카페입니다"
        assert len(result.highlights) == 3
        assert "조용함" in result.highlights
        assert "커피 맛있음" in result.highlights
        assert "디저트" in result.highlights
    
    @pytest.mark.unit
    def test_parse_single_poi_without_name_returns_none(self, summarizer):
        """이름 없으면 None 반환 테스트"""
        poi_text = """
        <category>cafe</category>
        <summary>설명</summary>
        """
        
        result = summarizer._parse_single_poi(poi_text)
        
        assert result is None


# =============================================================================
# 통합 테스트: 모든 의존성 실제 사용
# =============================================================================
class TestInfoSummarizeAgentIntegration:
    """InfoSummarizeAgent 통합 테스트 (실제 LLM 사용)"""
    
    @pytest.fixture
    def real_llm_client(self):
        """실제 LLM Client 생성"""
        try:
            from app.core.LLMClient.VllmClient import VllmClient
            return VllmClient()
        except Exception as e:
            pytest.skip(f"LLM Client 초기화 실패: {e}")
    
    @pytest.fixture
    def summarizer(self, real_llm_client):
        """InfoSummarizeAgent 인스턴스 생성"""
        return InfoSummarizeAgent(real_llm_client)
    
    @pytest.fixture
    def real_sample_results(self):
        """실제 웹 검색 결과 가져오기"""
        import asyncio
        try:
            from app.core.Agents.Poi.WebSearch.WebSearchAgent import WebSearchAgent
            agent = WebSearchAgent()
            result = asyncio.run(agent.search("서울 맛집", num_results=5))
            print(result)
            return result
        except Exception as e:
            pytest.skip(f"WebSearchAgent 초기화 실패: {e}")
    
    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_summarize_with_real_llm(self, summarizer, real_sample_results):
        """실제 LLM으로 요약 테스트"""
        if not real_sample_results:
            pytest.skip("검색 결과 없음")
        
        result = await summarizer.summarize(
            merged_results=real_sample_results,
            persona_summary="혼자 여행하는 20대",
            max_pois=2
        )
        
        print(result)

        assert isinstance(result, list)
        assert len(result) > 0 and len(result) <= 2
        assert isinstance(result[0], PoiInfo)
       
