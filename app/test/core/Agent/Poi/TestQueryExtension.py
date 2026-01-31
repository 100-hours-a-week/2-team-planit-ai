import pytest
from unittest.mock import AsyncMock, MagicMock
from app.core.Agents.Poi.QueryExtention.QueryExtention import QueryExtension
from app.core.models.LlmClientDataclass.ChatMessageDataclass import ChatMessage, MessageData


# =============================================================================
# 단위 테스트: 모든 의존성 Mock 사용
# =============================================================================
class TestKeywordExtractorUnit:
    """KeywordExtractor 단위 테스트 (Mock LLM 사용)"""
    
    @pytest.fixture
    def mock_llm_client(self):
        """Mock LLM Client 생성"""
        client = MagicMock()
        client.call_llm = AsyncMock()
        return client
    
    @pytest.fixture
    def extractor(self, mock_llm_client):
        """KeywordExtractor 인스턴스 생성"""
        return QueryExtension(mock_llm_client)
    
    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_extract_keywords_empty_persona_returns_empty(self, extractor):
        """빈 페르소나 처리 테스트"""
        result = await extractor.extract_keywords("")
        assert result == []
    
    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_extract_keywords_parses_response(self, extractor, mock_llm_client):
        """XML 응답 파싱 테스트"""
        mock_llm_client.call_llm.return_value = """
        <keywords>
        <keyword>서울 혼밥 맛집</keyword>
        <keyword>강남 카페</keyword>
        </keywords>
        """
        
        result = await extractor.extract_keywords("테스트 페르소나")
        
        assert isinstance(result, list)
        assert len(result) == 2
        assert "서울 혼밥 맛집" in result
        assert "강남 카페" in result
    
    @pytest.mark.unit
    def test_parse_keywords_extracts_correctly(self, extractor):
        """_parse_keywords 메서드 테스트"""
        response = """
        <keywords>
        <keyword>키워드1</keyword>
        <keyword>키워드2</keyword>
        <keyword>  키워드3  </keyword>
        </keywords>
        """
        
        result = extractor._parse_keywords(response)
        
        assert isinstance(result, list)
        assert len(result) == 3
        assert result[0] == "키워드1"
        assert result[1] == "키워드2"
        assert result[2] == "키워드3"  # 공백 제거 확인
    
    @pytest.mark.unit
    def test_parse_keywords_handles_empty_tags(self, extractor):
        """빈 태그 무시 테스트"""
        response = """
        <keywords>
        <keyword>유효한 키워드</keyword>
        <keyword></keyword>
        <keyword>   </keyword>
        </keywords>
        """
        
        result = extractor._parse_keywords(response)
        
        assert isinstance(result, list)
        assert len(result) == 1
        assert result[0] == "유효한 키워드"


# =============================================================================
# 통합 테스트: 모든 의존성 실제 사용
# =============================================================================
class TestKeywordExtractorIntegration:
    """KeywordExtractor 통합 테스트 (실제 LLM 사용)"""
    
    @pytest.fixture
    def real_llm_client(self):
        """실제 LLM Client 생성"""
        try:
            from app.core.LLMClient.VllmClient import VllmClient
            return VllmClient()
        except Exception as e:
            pytest.skip(f"LLM Client 초기화 실패: {e}")
    
    @pytest.fixture
    def extractor(self, real_llm_client):
        """KeywordExtractor 인스턴스 생성"""
        return QueryExtension(real_llm_client)
    
    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_extract_keywords_with_real_llm(self, extractor):
        """실제 LLM으로 키워드 추출 테스트"""
        result = await extractor.extract_keywords("혼자 여행하는 20대, 서울 여행")
        
        print(f"추출된 키워드: {result}")
        assert isinstance(result, list)
        assert len(result) > 0
