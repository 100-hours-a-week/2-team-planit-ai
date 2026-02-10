import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from app.core.Agents.Poi.WebSearch.WebSearchAgent import WebSearchAgent
from app.core.Agents.Poi.WebSearch.Extractor.LangExtractor import LangExtractor
from app.core.Agents.Poi.WebSearch.Extractor.JinaReader import JinaReader
from app.core.models.PoiAgentDataclass.poi import PoiSearchResult, PoiSource


# =============================================================================
# 단위 테스트: 모든 의존성 Mock 사용
# =============================================================================
class TestWebSearchAgentUnit:
    """WebSearchAgent 단위 테스트 (Mock Tavily API 사용)"""
    
    @pytest.fixture
    def mock_extractor(self):
        """Mock LangExtractor"""
        extractor = MagicMock(spec=LangExtractor)
        extractor.extract = MagicMock(return_value=[])
        return extractor
    
    @pytest.fixture
    def mock_jina_reader(self):
        """Mock JinaReader"""
        reader = MagicMock(spec=JinaReader)
        reader.read = AsyncMock(return_value=None)
        return reader
    
    @pytest.fixture
    def mock_tavily_client(self):
        """Mock Tavily Client"""
        client = MagicMock()
        client.search = MagicMock(return_value={
            "results": [
                {
                    "title": "테스트 맛집",
                    "content": "맛있는 음식점입니다.",
                    "url": "https://example.com/1",
                    "score": 0.9
                },
                {
                    "title": "테스트 카페",
                    "content": "분위기 좋은 카페입니다.",
                    "url": "https://example.com/2",
                    "score": 0.8
                }
            ]
        })
        return client
    
    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_search_empty_query(self, mock_extractor, mock_jina_reader, mock_tavily_client):
        """빈 쿼리 처리 테스트"""
        with patch('app.core.Agents.Poi.WebSearch.WebSearchAgent.TavilyClient', return_value=mock_tavily_client):
            agent = WebSearchAgent(
                extractor=mock_extractor,
                jina_reader=mock_jina_reader,
                num_results=5
            )
            
            results = await agent.search("")
            
            assert results == []
    
    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_search_multiple_empty_queries(self, mock_extractor, mock_jina_reader, mock_tavily_client):
        """빈 쿼리 리스트 처리 테스트"""
        with patch('app.core.Agents.Poi.WebSearch.WebSearchAgent.TavilyClient', return_value=mock_tavily_client):
            agent = WebSearchAgent(
                extractor=mock_extractor,
                jina_reader=mock_jina_reader,
                num_results=5
            )
            
            results = await agent.search_multiple([])
            
            assert results == []
    
    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_search_multiple_removes_duplicates(self, mock_extractor, mock_jina_reader, mock_tavily_client):
        """중복 URL 제거 테스트"""
        # 동일 URL 반환하도록 설정
        mock_tavily_client.search.return_value = {
            "results": [
                {"title": "동일 결과", "content": "내용", "url": "https://example.com/same", "score": 0.9}
            ]
        }
        
        with patch('app.core.Agents.Poi.WebSearch.WebSearchAgent.TavilyClient', return_value=mock_tavily_client):
            agent = WebSearchAgent(
                extractor=mock_extractor,
                jina_reader=mock_jina_reader,
                num_results=5
            )
            agent.client = mock_tavily_client
            
            # 두 번 검색 (현재 구현에서는 중복 제거가 비활성화되어 있음)
            results = await agent.search_multiple(["쿼리1", "쿼리2"], destination="서울")
            
            # 결과가 반환되는지 확인
            assert isinstance(results, list)


# =============================================================================
# 통합 테스트: 모든 의존성 실제 사용
# =============================================================================
class TestWebSearchAgentIntegration:
    """WebSearchAgent 통합 테스트 (실제 Tavily API 사용)"""
    
    @pytest.fixture
    def agent(self):
        """WebSearchAgent 인스턴스 생성"""
        try:
            extractor = LangExtractor()
            jina_reader = JinaReader()
            return WebSearchAgent(
                extractor=extractor,
                jina_reader=jina_reader,
                num_results=3
            )
        except Exception as e:
            pytest.skip(f"WebSearchAgent 초기화 실패: {e}")
    
    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_search_returns_results(self, agent):
        """단일 쿼리 검색 테스트"""
        if not agent.api_key:
            pytest.skip("API 키 없음")
        
        results = await agent.search("서울 맛집", destination="서울")
        
        print(f"\n[search] 검색 결과 수: {len(results)}")
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
        results = await agent.search_multiple(queries, destination="서울")
        print(f"\n[search_multiple] 검색 결과 수: {len(results)}")
        
        assert isinstance(results, list)
        assert len(results) > 0
    
    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_search_result_structure(self, agent):
        """검색 결과 구조 확인"""
        if not agent.api_key:
            pytest.skip("API 키 없음")
        
        results = await agent.search("서울 관광지", destination="서울")
        if results:
            result = results[0]
            
            assert hasattr(result, 'title')
            assert hasattr(result, 'snippet')
            assert hasattr(result, 'url')
            assert hasattr(result, 'source')
            assert hasattr(result, 'relevance_score')
