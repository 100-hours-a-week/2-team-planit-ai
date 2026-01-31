import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from app.core.Agents.Poi.WebSearch.LangchainWebSearchAgent import LangchainWebSearchAgent
from app.core.models.PoiAgentDataclass.poi import PoiSearchResult, PoiSource


# =============================================================================
# 단위 테스트: 모든 의존성 Mock 사용
# =============================================================================
class TestLangchainWebSearchAgentUnit:
    """LangchainWebSearchAgent 단위 테스트 (Mock 사용)"""
    
    @pytest.fixture
    def mock_tool(self):
        """Mock TavilySearchResults Tool"""
        tool = MagicMock()
        tool.invoke = MagicMock(return_value=[
            {
                "url": "https://example.com/1",
                "content": "테스트 맛집 설명입니다."
            },
            {
                "url": "https://example.com/2",
                "content": "테스트 카페 설명입니다."
            }
        ])
        return tool
    
    @pytest.mark.unit
    def test_initialization(self):
        """초기화 테스트"""
        agent = LangchainWebSearchAgent(max_results=10)
        
        assert agent.max_results == 10
    
    @pytest.mark.unit
    def test_extract_title_from_url(self):
        """URL에서 제목 추출 테스트"""
        agent = LangchainWebSearchAgent()
        
        url1 = "https://www.example.com/restaurants/seoul-best"
        title1 = agent._extract_title_from_url(url1)
        assert title1 == "Seoul Best"
        
        url2 = "https://blog.naver.com/test/post123"
        title2 = agent._extract_title_from_url(url2)
        assert len(title2) > 0
    
    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_search_empty_query(self):
        """빈 쿼리 처리 테스트"""
        agent = LangchainWebSearchAgent()
        
        results = await agent.search("", num_results=5)
        
        assert results == []
    
    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_search_multiple_empty_queries(self):
        """빈 쿼리 리스트 처리 테스트"""
        agent = LangchainWebSearchAgent()
        
        results = await agent.search_multiple([])
        
        assert results == []


# =============================================================================
# 통합 테스트: 모든 의존성 실제 사용
# =============================================================================
class TestLangchainWebSearchAgentIntegration:
    """LangchainWebSearchAgent 통합 테스트 (실제 Tavily API 사용)"""
    
    @pytest.fixture
    def agent(self):
        """LangchainWebSearchAgent 인스턴스 생성"""
        try:
            return LangchainWebSearchAgent(max_results=5)
        except Exception as e:
            pytest.skip(f"LangchainWebSearchAgent 초기화 실패: {e}")
    
    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_search_returns_results(self, agent):
        """단일 쿼리 검색 테스트"""
        if not agent.api_key:
            pytest.skip("API 키 없음")
        
        results = await agent.search("서울 맛집", num_results=5)
        
        print(f"\n[LangChain search] 검색 결과 수: {len(results)}")
        for i, result in enumerate(results[:3]):
            print(f"  {i+1}. {result.title}")
        
        assert isinstance(results, list)
        assert len(results) > 0
        
        for result in results:
            assert isinstance(result, PoiSearchResult)
            assert result.source == PoiSource.WEB_SEARCH
    
    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_search_multiple_queries(self, agent):
        """여러 쿼리 병렬 검색 테스트"""
        if not agent.api_key:
            pytest.skip("API 키 없음")
        
        queries = ["서울 혼밥 맛집", "강남 카페"]
        results = await agent.search_multiple(queries, num_results_per_query=3)
        
        print(f"\n[LangChain search_multiple] 검색 결과 수: {len(results)}")
        
        assert isinstance(results, list)
        assert len(results) > 0
    
    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_search_result_has_url(self, agent):
        """검색 결과에 URL이 있는지 확인"""
        if not agent.api_key:
            pytest.skip("API 키 없음")
        
        results = await agent.search("서울 관광지", num_results=1)
        
        if results:
            assert results[0].url is not None
            assert results[0].url.startswith("http")
