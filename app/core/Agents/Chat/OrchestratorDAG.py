"""
OrchestratorDAG: 기존 고정 DAG 기반 오케스트레이터 (백업/롤백용)

대화형 챗봇 시스템의 진입점입니다.
히스토리 로드 → 주제 필터 → 의도 분류 → 브랜치 라우팅 → 히스토리 저장.

Human-in-the-loop:
    추가 정보가 필요한 경우 interrupt()로 그래프를 일시정지하고,
    사용자 응답 후 Command(resume=...)로 재개합니다.

NOTE: ReAct 패턴 마이그레이션 이전의 원본 Orchestrator입니다.
      롤백 시 deps.py에서 이 클래스를 import하면 됩니다:
      from app.core.Agents.Chat.OrchestratorDAG import OrchestratorDAG as Orchestrator
"""
import logging
from typing import Literal, Optional

from pydantic import BaseModel, Field

from langgraph.graph import StateGraph, END
from langgraph.types import interrupt

from app.core.LLMClient.BaseLlmClient import BaseLLMClient
from app.core.models.LlmClientDataclass.ChatMessageDataclass import (
    ChatMessage,
    MessageData,
)
from app.core.Agents.Chat.ChatState import ChatState, UserIntent
from app.core.Agents.Chat.TopicFilter import TopicFilter
from app.core.Agents.Chat.History.MongoHistoryStore import MongoHistoryStore
from app.core.Agents.Chat.ScheduleChange.ScheduleChangeAgent import ScheduleChangeAgent
from app.core.Agents.Chat.InfoAgent.InfoAgent import InfoAgent
from app.core.langfuse_setup import get_langfuse_handler
from app.schemas.Itinerary import ItineraryResponse

try:
    from langfuse import observe
except ImportError:
    def observe(**kwargs):
        def decorator(fn):
            return fn
        return decorator

logger = logging.getLogger(__name__)


# ─── 상수 ────────────────────────────────────────────

MAX_HISTORY_TURNS = 10
CONTEXT_TURNS = 3
CLARIFICATION_CONFIDENCE_THRESHOLD = 0.6


# ─── 의도 분류 Pydantic 모델 ─────────────────────────

class IntentClassificationResult(BaseModel):
    """의도 분류 결과"""
    intent: Literal[
        "info_recommend",
        "info_delivery",
        "schedule_edit",
        "schedule_delete",
        "schedule_add",
        "needs_clarification",
        "unresolvable",
    ] = Field(description="분류된 사용자 의도")
    confidence: float = Field(
        ge=0.0, le=1.0,
        description="분류 확신도 (0.0~1.0)"
    )
    reasoning: str = Field(
        description="분류 근거 (한 문장)"
    )
    clarification_question: Optional[str] = Field(
        default=None,
        description="needs_clarification일 때 사용자에게 할 질문"
    )


# ─── 의도 분류 프롬프트 ──────────────────────────────

INTENT_SYSTEM_PROMPT = """당신은 여행 챗봇의 의도 분류기입니다.
사용자의 여행 관련 요청을 아래 카테고리 중 하나로 분류하세요.

## 분류 카테고리

| intent | 설명 | 예시 |
|--------|------|------|
| info_recommend | 여행지/맛집/카페/관광지 추천 | "도쿄 맛집 추천해줘", "교토에서 가볼 만한 곳" |
| info_delivery | 일반 여행 정보 전달 | "일본 환율", "도쿄 날씨", "비자 필요해?" |
| schedule_edit | 기존 일정 수정 | "2일차 점심을 다른 곳으로 바꿔줘" |
| schedule_delete | 기존 일정 삭제 | "3일차 저녁 일정 빼줘" |
| schedule_add | 일정에 새 장소 추가 | "2일차에 아사쿠사 추가해줘" |
| needs_clarification | 추가 정보가 필요함 | "바꿔줘" (대상 불명), "좋은 곳 추천" (카테고리 불명) |
| unresolvable | 처리 불가능 | 일정 없이 일정 변경 요청 등 |

## 판단 기준
- 의도가 명확하면 해당 카테고리로 분류하세요.
- 의도가 모호하거나 추가 정보가 필요하면 `needs_clarification`으로 분류하고, `clarification_question`에 사용자에게 할 질문을 작성하세요.
- 일정 변경(schedule_*) 요청인데 현재 일정이 없으면: needs_clarification으로 분류하고 일정이 필요하다고 안내하세요.
- confidence가 0.6 미만이면 needs_clarification으로 분류하는 것을 고려하세요.
"""


# ─── OrchestratorDAG 클래스 ──────────────────────────

class OrchestratorDAG:
    """기존 고정 DAG 기반 오케스트레이터 (롤백용)

    Flow:
    1. load_history: MongoDB에서 대화 히스토리 로드
    2. filter_topic: TopicFilter로 주제 필터링
       → off_topic → off_topic_response → save_history → END
    3. classify_intent: vLLM structured output으로 의도 분류
       → needs_clarification → request_clarification (interrupt) → classify_intent
       → info_* → handle_info → save_history → END
       → schedule_* → handle_schedule → save_history → END
       → unresolvable → off_topic_response → save_history → END
    4. save_history: 사용자 메시지 + 응답을 MongoDB에 저장
    """

    def __init__(
        self,
        llm_client: BaseLLMClient,
        history_store: MongoHistoryStore,
        schedule_change_agent: ScheduleChangeAgent,
        info_agent: InfoAgent,
        checkpointer=None,
    ):
        self.llm_client = llm_client
        self.history_store = history_store
        self.schedule_change_agent = schedule_change_agent
        self.info_agent = info_agent
        self.topic_filter = TopicFilter(llm_client)

        if checkpointer is None:
            from langgraph.checkpoint.memory import MemorySaver
            checkpointer = MemorySaver()

        self.graph = self._build_graph(checkpointer)

    def _build_graph(self, checkpointer) -> StateGraph:
        graph = StateGraph(ChatState)

        graph.add_node("load_history", self._load_history)
        graph.add_node("filter_topic", self._filter_topic)
        graph.add_node("classify_intent", self._classify_intent)
        graph.add_node("request_clarification", self._request_clarification)
        graph.add_node("handle_info", self._handle_info)
        graph.add_node("handle_schedule", self._handle_schedule)
        graph.add_node("off_topic_response", self._off_topic_response)
        graph.add_node("save_history", self._save_history)

        graph.set_entry_point("load_history")
        graph.add_edge("load_history", "filter_topic")

        graph.add_conditional_edges(
            "filter_topic",
            self._route_after_filter,
            {
                "on_topic": "classify_intent",
                "off_topic": "off_topic_response",
            },
        )

        graph.add_conditional_edges(
            "classify_intent",
            self._route_after_classify,
            {
                "info": "handle_info",
                "schedule": "handle_schedule",
                "clarification": "request_clarification",
                "off_topic": "off_topic_response",
            },
        )

        graph.add_edge("request_clarification", "classify_intent")
        graph.add_edge("handle_info", "save_history")
        graph.add_edge("handle_schedule", "save_history")
        graph.add_edge("off_topic_response", "save_history")
        graph.add_edge("save_history", END)

        return graph.compile(checkpointer=checkpointer)

    # ─── 노드 구현 ───────────────────────────────────────

    async def _load_history(self, state: ChatState) -> dict:
        session_id = state.get("session_id", "")
        if not session_id:
            return {"messages": []}

        try:
            messages = await self.history_store.get_messages(
                session_id=session_id,
                limit=MAX_HISTORY_TURNS * 2,
            )
            logger.debug(f"히스토리 로드: session={session_id}, {len(messages)}개 메시지")
            return {"messages": messages}
        except Exception as e:
            logger.error(f"히스토리 로드 실패: {e}")
            return {"messages": []}

    async def _filter_topic(self, state: ChatState) -> dict:
        user_message = state.get("current_user_message", "")
        messages = state.get("messages", [])
        recent = messages[-(CONTEXT_TURNS * 2):] if messages else []

        result = await self.topic_filter.filter(
            user_message=user_message,
            recent_messages=recent,
        )

        return {"is_on_topic": result.is_on_topic}

    async def _classify_intent(self, state: ChatState) -> dict:
        user_message = state.get("current_user_message", "")
        messages = state.get("messages", [])
        has_itinerary = state.get("current_itinerary") is not None

        user_prompt = self._build_intent_prompt(user_message, messages, has_itinerary)

        prompt = ChatMessage(content=[
            MessageData(role="system", content=INTENT_SYSTEM_PROMPT),
            MessageData(role="user", content=user_prompt),
        ])

        try:
            result = await self.llm_client.call_llm_structured(
                prompt=prompt,
                model=IntentClassificationResult,
            )

            logger.info(
                f"의도 분류: intent={result.intent}, "
                f"confidence={result.confidence:.2f}, "
                f"reasoning={result.reasoning}"
            )

            if (
                result.intent != "needs_clarification"
                and result.confidence < CLARIFICATION_CONFIDENCE_THRESHOLD
            ):
                return {
                    "user_intent": UserIntent.UNRESOLVABLE,
                    "needs_clarification": True,
                    "clarification_question": (
                        result.clarification_question
                        or "좀 더 구체적으로 말씀해 주시겠어요?"
                    ),
                }

            if result.intent == "needs_clarification":
                return {
                    "user_intent": UserIntent.UNRESOLVABLE,
                    "needs_clarification": True,
                    "clarification_question": (
                        result.clarification_question
                        or "좀 더 구체적으로 말씀해 주시겠어요?"
                    ),
                }

            intent_map = {
                "info_recommend": UserIntent.INFO_RECOMMEND,
                "info_delivery": UserIntent.INFO_DELIVERY,
                "schedule_edit": UserIntent.SCHEDULE_EDIT,
                "schedule_delete": UserIntent.SCHEDULE_DELETE,
                "schedule_add": UserIntent.SCHEDULE_ADD,
                "unresolvable": UserIntent.UNRESOLVABLE,
            }

            return {
                "user_intent": intent_map.get(result.intent, UserIntent.UNRESOLVABLE),
                "needs_clarification": False,
            }

        except Exception as e:
            logger.error(f"의도 분류 LLM 호출 실패: {e}")
            return {
                "user_intent": UserIntent.UNRESOLVABLE,
                "needs_clarification": True,
                "clarification_question": "요청을 이해하지 못했습니다. 좀 더 구체적으로 말씀해 주시겠어요?",
            }

    async def _request_clarification(self, state: ChatState) -> dict:
        question = state.get(
            "clarification_question",
            "좀 더 구체적으로 말씀해 주시겠어요?",
        )
        logger.info(f"Clarification 요청: {question}")

        user_answer = interrupt(question)
        logger.info(f"사용자 보충 답변: {user_answer}")

        original_message = state.get("current_user_message", "")
        enriched_message = f"{original_message} — 보충: {user_answer}"

        return {
            "user_clarification": user_answer,
            "current_user_message": enriched_message,
            "needs_clarification": False,
            "clarification_question": None,
        }

    async def _handle_info(self, state: ChatState) -> dict:
        try:
            result = await self.info_agent.run(state)
            return {
                "response": result.get("response", ""),
                "search_results": result.get("search_results", []),
            }
        except Exception as e:
            logger.error(f"InfoAgent 실행 실패: {e}")
            return {"response": f"정보 검색 중 오류가 발생했습니다: {str(e)}"}

    async def _handle_schedule(self, state: ChatState) -> dict:
        if not state.get("current_itinerary"):
            return {
                "response": "현재 일정이 없습니다. 일정을 먼저 생성해주세요.",
            }

        try:
            result = await self.schedule_change_agent.run(state)
            return {
                "response": result.get("response", ""),
                "modified_itinerary": result.get("modified_itinerary"),
            }
        except Exception as e:
            logger.error(f"ScheduleChangeAgent 실행 실패: {e}")
            return {"response": f"일정 변경 중 오류가 발생했습니다: {str(e)}"}

    def _off_topic_response(self, state: ChatState) -> dict:
        is_on_topic = state.get("is_on_topic", True)

        if not is_on_topic:
            return {
                "response": (
                    "죄송합니다. 저는 여행 관련 질문만 도와드릴 수 있어요. "
                    "여행지 추천, 일정 변경, 여행 정보 등에 대해 물어봐 주세요!"
                ),
            }

        return {
            "response": (
                "죄송합니다. 요청을 처리할 수 없습니다. "
                "좀 더 구체적으로 말씀해 주시겠어요?"
            ),
        }

    async def _save_history(self, state: ChatState) -> dict:
        session_id = state.get("session_id", "")
        if not session_id:
            return {}

        user_message = state.get("current_user_message", "")
        response = state.get("response", "")

        try:
            if user_message:
                await self.history_store.add_message(
                    session_id=session_id,
                    role="user",
                    content=user_message,
                )
            if response:
                await self.history_store.add_message(
                    session_id=session_id,
                    role="assistant",
                    content=response,
                )
            logger.debug(f"히스토리 저장 완료: session={session_id}")
        except Exception as e:
            logger.error(f"히스토리 저장 실패: {e}")

        return {}

    # ─── 라우팅 함수 ─────────────────────────────────────

    def _route_after_filter(self, state: ChatState) -> str:
        if state.get("is_on_topic", False):
            return "on_topic"
        return "off_topic"

    def _route_after_classify(self, state: ChatState) -> str:
        if state.get("needs_clarification", False):
            return "clarification"

        intent = state.get("user_intent", "")

        if intent in (UserIntent.INFO_RECOMMEND, UserIntent.INFO_DELIVERY):
            return "info"

        if intent in (
            UserIntent.SCHEDULE_EDIT,
            UserIntent.SCHEDULE_DELETE,
            UserIntent.SCHEDULE_ADD,
        ):
            return "schedule"

        return "off_topic"

    # ─── 프롬프트 빌더 ───────────────────────────────────

    def _build_intent_prompt(
        self,
        user_message: str,
        messages: list,
        has_itinerary: bool,
    ) -> str:
        parts = []

        recent = messages[-(CONTEXT_TURNS * 2):] if messages else []
        if recent:
            parts.append("## 최근 대화 맥락")
            for msg in recent:
                role = "사용자" if msg.get("role") == "user" else "어시스턴트"
                content = msg.get("content", "")
                if len(content) > 200:
                    content = content[:200] + "..."
                parts.append(f"- {role}: {content}")
            parts.append("")

        parts.append(f"## 현재 일정 데이터: {'있음' if has_itinerary else '없음'}")
        if not has_itinerary:
            parts.append("> 일정 변경(schedule_*) 요청이지만 일정이 없으면 needs_clarification으로 분류하세요.")
        parts.append("")

        parts.append(f"## 현재 사용자 메시지\n{user_message}")
        parts.append("\n위 메시지의 의도를 분류하세요.")

        return "\n".join(parts)

    # ─── 실행 ────────────────────────────────────────────

    @observe(name="orchestrator-dag")
    async def run(
        self,
        session_id: str,
        user_message: str,
        current_itinerary: Optional[ItineraryResponse] = None,
        user_jwt: Optional[str] = None,
        backend_itinerary_data: Optional[dict] = None,
    ) -> ChatState:
        initial_state: ChatState = {
            "session_id": session_id,
            "current_user_message": user_message,
            "current_itinerary": current_itinerary,
            "user_jwt": user_jwt,
            "backend_itinerary_data": backend_itinerary_data,
            "messages": [],
            "is_on_topic": False,
            "user_intent": "",
            "needs_clarification": False,
            "clarification_question": None,
            "user_clarification": None,
            "response": "",
        }

        callbacks = []
        handler = get_langfuse_handler(tags=["orchestrator-dag"])
        if handler:
            callbacks.append(handler)

        config = {
            "configurable": {"thread_id": session_id},
        }
        if callbacks:
            config["callbacks"] = callbacks

        result = await self.graph.ainvoke(initial_state, config=config)
        return result

    @observe(name="orchestrator-dag-resume")
    async def resume(
        self,
        session_id: str,
        user_answer: str,
    ) -> ChatState:
        from langgraph.types import Command

        callbacks = []
        handler = get_langfuse_handler(tags=["orchestrator-dag-resume"])
        if handler:
            callbacks.append(handler)

        config = {
            "configurable": {"thread_id": session_id},
        }
        if callbacks:
            config["callbacks"] = callbacks

        result = await self.graph.ainvoke(
            Command(resume=user_answer),
            config=config,
        )
        return result
