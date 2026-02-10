import pytest
from unittest.mock import AsyncMock, MagicMock
from app.core.Agents.Persona.TravelPersonaAgent import (
    TravelPersonaAgent,
    TravelPersonaState,
    itinerary_request_to_pre_survey,
    qa_items_to_qa_answers
)
from app.schemas.persona import ItineraryRequest
from app.core.models.PersonaAgentDataclass.persona import QAItem, Persona


# =============================================================================
# Fixture 데이터
# =============================================================================
@pytest.fixture
def mock_itinerary_request() -> ItineraryRequest:
    """테스트용 ItineraryRequest"""
    return ItineraryRequest(
        tripId=1,
        arrivalDate="2025-01-21",
        arrivalTime="12:00",
        departureDate="2025-01-22",
        departureTime="12:00",
        travelCity="Seoul",
        totalBudget=100000,
        travelTheme=["food", "shopping"],
        wantedPlace=["Museum", "Park"]
    )


@pytest.fixture
def mock_qa_history() -> list[QAItem]:
    """테스트용 QA 히스토리"""
    return [
        QAItem(
            id=1,
            question="이번 여행에서 가장 얻고 싶은 감정?",
            answer="설렘과 '우리 취향 딱이야'라는 만족감"
        ),
        QAItem(
            id=2,
            question="이번 여행은 어떤 의미를 가지고 있나요?",
            answer="기념일을 특별하게 보내며 서로의 취향을 더 알아가는 여행"
        ),
        QAItem(
            id=3,
            question="관심사 키워드?",
            answer=["파인다이닝", "와인바", "베이커리"]
        )
    ]


@pytest.fixture
def mock_llm_client():
    """Mock LLM Client"""
    client = MagicMock()
    client.call_llm = AsyncMock(return_value="""
    <final_response>20대 혼자 여행하는 미식가. 로컬 맛집과 분위기 좋은 카페를 선호하며 가성비를 중시함.</final_response>
    """)
    return client


@pytest.fixture
def mock_persona_prompt():
    """Mock Persona Prompt"""
    return """
    여행 정보:
    {pre_survey}
    
    Q&A:
    {qa_answers}
    
    위 정보를 바탕으로 여행자 페르소나를 생성해주세요.
    <final_response>페르소나 요약</final_response>
    """


@pytest.fixture
def mock_system_prompt():
    """Mock System Prompt"""
    return "당신은 여행 페르소나 생성 전문가입니다."


# =============================================================================
# 단위 테스트: 헬퍼 함수 테스트
# =============================================================================
class TestTravelPersonaAgentUnit:
    """TravelPersonaAgent 단위 테스트"""
    
    @pytest.mark.unit
    def test_itinerary_request_to_pre_survey(self, mock_itinerary_request):
        """ItineraryRequest -> XML 변환 테스트"""
        result = itinerary_request_to_pre_survey(mock_itinerary_request)
        
        assert isinstance(result, str)
        assert "<tripId>1</tripId>" in result
        assert "<travelCity>Seoul</travelCity>" in result
        assert "<totalBudget>100000</totalBudget>" in result
        assert "food, shopping" in result  # travelTheme 리스트
        assert "Museum, Park" in result  # wantedPlace 리스트
    
    @pytest.mark.unit
    def test_qa_items_to_qa_answers(self, mock_qa_history):
        """QAItem 리스트 -> XML 변환 테스트"""
        result = qa_items_to_qa_answers(mock_qa_history)
        
        assert isinstance(result, str)
        assert "<qa>" in result
        assert "</qa>" in result
        assert "<question>" in result
        assert "</question>" in result
        assert "<answer>" in result
        assert "</answer>" in result
        assert "이번 여행에서 가장 얻고 싶은 감정?" in result
    
    @pytest.mark.unit
    def test_itinerary_request_to_pre_survey_indent(self, mock_itinerary_request):
        """들여쓰기 옵션 테스트"""
        result = itinerary_request_to_pre_survey(
            mock_itinerary_request,
            intend=4,
            indent_char="  "
        )
        
        # 4 * 2 공백 = 8 공백으로 시작해야 함
        lines = result.split("\n")
        assert lines[0].startswith("        ")  # 8 spaces
    
    @pytest.mark.unit
    def test_qa_items_to_qa_answers_empty(self):
        """빈 QA 리스트 처리 테스트"""
        result = qa_items_to_qa_answers([])
        assert result == ""


# =============================================================================
# 단위 테스트: Agent 테스트 (Mock LLM)
# =============================================================================
class TestTravelPersonaAgentWithMock:
    """TravelPersonaAgent Mock 테스트"""
    
    @pytest.mark.unit
    def test_agent_initialization(
        self, 
        mock_llm_client, 
        mock_persona_prompt, 
        mock_system_prompt
    ):
        """Agent 초기화 테스트"""
        agent = TravelPersonaAgent(
            llm_client=mock_llm_client,
            persona_prompt=mock_persona_prompt,
            system_prompt=mock_system_prompt
        )
        
        assert agent.llm == mock_llm_client
        assert agent.persona_prompt == mock_persona_prompt
        assert agent.system_prompt == mock_system_prompt
        assert agent.graph is not None
    
    @pytest.mark.unit
    def test_generate_question_node(
        self,
        mock_llm_client,
        mock_persona_prompt,
        mock_system_prompt,
        mock_itinerary_request,
        mock_qa_history
    ):
        """generate_question 노드 테스트"""
        agent = TravelPersonaAgent(
            llm_client=mock_llm_client,
            persona_prompt=mock_persona_prompt,
            system_prompt=mock_system_prompt
        )
        
        state: TravelPersonaState = {
            "itinerary_request": mock_itinerary_request,
            "qa_items": mock_qa_history,
            "final_persona": None,
            "messages": None
        }
        
        result = agent.generate_question(state)
        
        assert "messages" in result
        assert result["messages"] is not None
        # ChatMessage 구조 확인
        assert len(result["messages"].content) == 2
        assert result["messages"].content[0].role == "system"
        assert result["messages"].content[1].role == "user"
    
    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_run_with_mock_llm(
        self,
        mock_llm_client,
        mock_persona_prompt,
        mock_system_prompt,
        mock_itinerary_request,
        mock_qa_history
    ):
        """run 메서드 테스트 (Mock LLM)"""
        agent = TravelPersonaAgent(
            llm_client=mock_llm_client,
            persona_prompt=mock_persona_prompt,
            system_prompt=mock_system_prompt
        )
        
        result = await agent.run(
            itinerary_request=mock_itinerary_request,
            qa_history=mock_qa_history
        )
        
        assert isinstance(result, str)
        assert len(result) > 0
        mock_llm_client.call_llm.assert_called_once()


# =============================================================================
# 통합 테스트: 실제 LLM 사용
# =============================================================================
class TestTravelPersonaAgentIntegration:
    """TravelPersonaAgent 통합 테스트 (실제 LLM 사용)"""
    
    @pytest.fixture
    def real_llm_client(self):
        """실제 LLM Client"""
        try:
            from app.core.LLMClient.OpenAiApiClient import OpenAiApiClient
            return OpenAiApiClient()
        except Exception as e:
            pytest.skip(f"LLM Client 초기화 실패: {e}")
    
    @pytest.fixture
    def real_prompts(self):
        """실제 프롬프트"""
        try:
            from app.core.Prompt.PersonaAgentPrompt import TEST_SYSTEM_PROMPT, TEST_PERSONA_PROMPT
            return TEST_PERSONA_PROMPT, TEST_SYSTEM_PROMPT
        except ImportError:
            pytest.skip("PersonaAgentPrompt 모듈 없음")
    
    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_run_with_real_llm(
        self,
        real_llm_client,
        real_prompts,
        mock_itinerary_request,
        mock_qa_history
    ):
        """실제 LLM으로 run 테스트"""
        persona_prompt, system_prompt = real_prompts
        
        agent = TravelPersonaAgent(
            llm_client=real_llm_client,
            persona_prompt=persona_prompt,
            system_prompt=system_prompt
        )
        
        result = await agent.run(
            itinerary_request=mock_itinerary_request,
            qa_history=mock_qa_history
        )
        
        print(f"생성된 페르소나: {result}")
        
        assert isinstance(result, str)
        assert len(result) > 0
