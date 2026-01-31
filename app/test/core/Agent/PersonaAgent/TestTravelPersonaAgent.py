import asyncio
from app.core.Agents.Persona.TravelPersonaAgent import TravelPersonaAgent, TravelPersonaState
from app.core.LLMClient.OpenAiApiClient import OpenAiApiClient
from app.schemas.persona import ItineraryRequest
from app.core.models.PersonaAgentDataclass.persona import QAItem

mock_itinerary_request_data = {
    "travelId": 1,
    "arrivalDate": "2025-01-21",
    "arrivalTime": "12:00",
    "departureDate": "2025-01-22",
    "departureTime": "12:00",
    "travelCity": "Seoul",
    "totalBudget": 100000,
    "theme": ["food", "shopping"],
    "companion": ["friend", "family"],
    "pace": "normal",
    "wantedPlace": ["Museum", "Park"]
}

# 객체로 변환
mock_itinerary_request = ItineraryRequest(**mock_itinerary_request_data)

mock_qa_history_data = [
    {
        "id": 1,
        "question": "이번 여행에서 가장 얻고 싶은 감정?",
        "answer": "설렘과 '우리 취향 딱이야'라는 만족감"
    },
    {
        "id": 2,
        "question": "이번 여행은 어떤 의미를 가지고 있나요?",
        "answer": "기념일을 특별하게 보내며 서로의 취향을 더 알아가는 여행"
    },
    {
        "id": 3,
        "question": "이번 여행의 제약 조건?",
        "answer": ["웨이팅 1시간 이상 회피", "과음 지양", "예산 2인 250만 내외", "예약/동선 효율 중요"]
    },
    {
        "id": 4,
        "question": "여행이 끝났을 때 “잘 다녀왔다”라고 말할 기준?",
        "answer": "최고의 한 끼가 3번 이상 있었고 다툼 없이 즐기면 성공"
    },
    {
        "id": 5,
        "question": "관심사 키워드?",
        "answer": ["파인다이닝", "와인바", "베이커리", "재래시장", "야경 레스토랑"]
    }
]

# 객체 리스트로 변환
mock_qa_history = [QAItem(**item) for item in mock_qa_history_data]

mock_travelPersonaState = TravelPersonaState(
    initial_info=mock_itinerary_request,
    qa_history=mock_qa_history,
    current_question_count=0,
    final_persona=None,
    next_step=""
)

async def main():
    
    # 1. ItineraryRequest 포맷팅 루틴 확인
    from app.core.Agents.Persona.TravelPersonaAgent import itinerary_request_to_pre_survey
    itinerary_xml_output = itinerary_request_to_pre_survey(mock_itinerary_request)
    print("--- itinerary_xml_output ---")
    print(itinerary_xml_output)

    print()

    # 2. QAHistory 포맷팅 루틴 확인
    from app.core.Agents.Persona.TravelPersonaAgent import qa_items_to_qa_answers
    qa_xml_output = qa_items_to_qa_answers(mock_qa_history)
    print("--- qa_xml_output ---")
    print(qa_xml_output)

    print()

    # 3. TravelPersonaAgent 실행
    from app.core.Agents.Persona.TravelPersonaAgent import TravelPersonaAgent
    from app.core.LLMClient.OpenAiApiClient import OpenAiApiClient
    from app.core.Prompt.PersonaAgentPrompt import TEST_SYSTEM_PROMPT, TEST_PERSONA_PROMPT
    
    agent = TravelPersonaAgent(OpenAiApiClient(), TEST_PERSONA_PROMPT, TEST_SYSTEM_PROMPT)
    
    final_persona = await agent.run(mock_itinerary_request, mock_qa_history)
    print("--- final_persona ---")
    print(final_persona)

if __name__ == "__main__":
    asyncio.run(main())
