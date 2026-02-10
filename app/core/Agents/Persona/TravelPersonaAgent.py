from typing import List, Optional, TypedDict
from langgraph.graph import StateGraph, END
from app.core.models.PersonaAgentDataclass.persona import QAItem, Persona
from app.core.models.LlmClientDataclass.ChatMessageDataclass import ChatMessage, MessageData
from app.schemas.persona import ItineraryRequest
from app.core.LLMClient.BaseLlmClient import BaseLLMClient
import logging

logger = logging.getLogger(__name__)

class TravelPersonaState(TypedDict):
    itinerary_request: Optional[ItineraryRequest]
    qa_items: List[QAItem]
    final_persona: Optional[Persona]
    messages: Optional[ChatMessage]



class TravelPersonaAgent:
    def __init__(
        self,
        llm_client: BaseLLMClient,
        persona_prompt: str,
        system_prompt: str
    ):
        self.llm = llm_client
        self.persona_prompt = persona_prompt
        self.system_prompt = system_prompt
        self.graph = self._build_graph()

    def _build_graph(self):
        # 1. StateGraph 초기화
        workflow = StateGraph(TravelPersonaState)

        # 2. 노드 추가
        workflow.add_node("generate_question", self.generate_question)
        workflow.add_node("finalize_persona", self.finalize_persona)

        # 3. 엣지 연결
        workflow.set_entry_point("generate_question")
        workflow.add_edge("generate_question", "finalize_persona")
        workflow.add_edge("finalize_persona", END)

        return workflow.compile()

    def generate_question(self, state: TravelPersonaState) -> TravelPersonaState:
        """
        사용자에게 던질 질문을 생성하거나, 질문 개수가 차면 다음 단계로 이동하는 단계
        """
        user_prompt = self.persona_prompt.format(
            pre_survey=itinerary_request_to_pre_survey(state["itinerary_request"]),
            qa_answers=qa_items_to_qa_answers(state["qa_items"]),
        )

        logger.info("유저 페르소나 에이전트 질문 생성")

        messages = ChatMessage(content=[
            MessageData(role="system", content=self.system_prompt),
            MessageData(role="user", content=user_prompt),
        ])

        return {
            "messages": messages,
        }

    async def finalize_persona(self, state: TravelPersonaState) -> TravelPersonaState:
        """
        수집된 정보들을 바탕으로 최종 페르소나를 생성하는 단계
        """

        logger.info("유저 페르소나 에이전트 최종 페르소나 생성 LLM 요청")
        response = await self.llm.call_llm(state["messages"])
        
        logger.info("유저 페르소나 에이전트 최종 페르소나 생성 LLM 응답")
        logger.info(response)

        answer = response.split("<final_response>")[1].split("</final_response>")[0]
        
        return {
            "final_persona": Persona(
                summary=answer
            )
        }

    async def run(self, itinerary_request: ItineraryRequest, qa_history: List[QAItem]) -> str:
        """
        워크플로우 실행 메서드
        """
        state = TravelPersonaState(
            itinerary_request=itinerary_request,
            qa_items=qa_history,
            final_persona=None,
            messages=[],
        )

        # compile()된 graph를 invoke하여 실행 (async 지원 필요 시 ainvoke 사용)
        return (await self.graph.ainvoke(state))["final_persona"].summary


def itinerary_request_to_pre_survey(itinerary_request: ItineraryRequest, intend: int = 2, indent_char: str =  "    ") -> str:
    """
    ItineraryRequest 객체를 XML 형식의 문자열로 변환합니다.
    """
    data = itinerary_request.model_dump()
    xml_lines = []
    for key, value in data.items():
        if isinstance(value, list):
            content = ", ".join(map(str, value))
            xml_lines.append(indent_char * intend + f"<{key}>{content}</{key}>")
        else:
            xml_lines.append(indent_char * intend + f"<{key}>{value}</{key}>")
    return "\n".join(xml_lines)

def qa_items_to_qa_answers(qa_items: List[QAItem], intend: int = 2, indent_char: str =  "    ") -> str:
    """
    QAItem 리스트를 XML 형식의 문자열로 변환합니다.
    """
    qa_lines = []
    for item in qa_items:
        qa_lines.append(indent_char * intend + "<qa>")
        qa_lines.append(indent_char * (intend + 1) + f"<question>{item.question}</question>")
        qa_lines.append(indent_char * (intend + 1) + f"<answer>{item.answer}</answer>")
        qa_lines.append(indent_char * intend + "</qa>")
    return "\n".join(qa_lines)