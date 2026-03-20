"""
Orchestrator: ReAct 패턴 기반 최상위 오케스트레이터

LLM이 자율적으로 도구를 선택하는 ReAct 패턴으로 동작합니다.
create_react_agent를 사용하여 도구 호출 루프를 자동 관리합니다.

이전 고정 DAG 기반 구현은 OrchestratorDAG.py에 백업되어 있습니다.
"""
import logging
from typing import Optional

from langchain_core.messages import HumanMessage, SystemMessage, AIMessage
from langgraph.checkpoint.memory import MemorySaver
from langgraph.prebuilt import create_react_agent

from app.core.LLMClient.LangchainClient import LangchainClient
from app.core.LLMClient.BaseLlmClient import BaseLLMClient
from app.core.Agents.Chat.ChatState import ReActChatState
from app.core.Agents.Chat.History.MongoHistoryStore import MongoHistoryStore
from app.core.Agents.Chat.system_prompt import build_system_prompt, summarize_itinerary
from app.core.Agents.Chat.tools import create_tools
from app.core.Agents.Chat.ScheduleChange.PlaceResolver import PlaceResolver
from app.core.Agents.Chat.ScheduleChange.EventEditAgent import EventEditAgent
from app.core.Agents.Chat.ScheduleChange.ConsistencyChecker import ConsistencyChecker
from app.core.Agents.Chat.InfoAgent.PlaceSearchAgent import PlaceSearchAgent
from app.core.Agents.Chat.InfoAgent.TavilySearchTool import TavilySearchTool
from app.core.BackendClient import BackendClient
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

# 히스토리 로드 시 최대 턴 수 (1턴 = user + assistant)
MAX_HISTORY_TURNS = 10


class Orchestrator:
    """ReAct 패턴 기반 오케스트레이터

    LLM이 자율적으로 도구를 선택하여 사용자 요청을 처리합니다.
    - 여행 정보 검색, 장소 추천
    - 일정 조회, 수정, 삭제, 추가
    - off-topic 질문은 도구 호출 없이 거절

    run() 메서드의 시그니처와 반환 형식은 기존 DAG Orchestrator와 동일합니다.
    """

    def __init__(
        self,
        langchain_client: LangchainClient,
        llm_client: BaseLLMClient,
        history_store: MongoHistoryStore,
        place_resolver: PlaceResolver,
        event_edit_agent: EventEditAgent,
        consistency_checker: ConsistencyChecker,
        place_search: PlaceSearchAgent,
        tavily_tool: TavilySearchTool,
        backend_client: Optional[BackendClient] = None,
        checkpointer=None,
    ):
        """
        Args:
            langchain_client: LangChain ChatOpenAI 클라이언트 (bind_tools용)
            llm_client: 하위 에이전트용 BaseLLMClient (structured output)
            history_store: MongoDB 대화 히스토리 저장소
            place_resolver: 장소 검증 모듈
            event_edit_agent: 이벤트 수정 에이전트
            consistency_checker: 정합성 검사 모듈
            place_search: 멀티소스 장소 검색 에이전트
            tavily_tool: Tavily 검색 도구
            backend_client: 백엔드 API 클라이언트
            checkpointer: LangGraph 체크포인터 (None이면 MemorySaver)
        """
        self.langchain_client = langchain_client
        self.llm_client = llm_client
        self.history_store = history_store
        self.place_resolver = place_resolver
        self.event_edit_agent = event_edit_agent
        self.consistency_checker = consistency_checker
        self.place_search = place_search
        self.tavily_tool = tavily_tool
        self.backend_client = backend_client
        self.checkpointer = checkpointer or MemorySaver()

    def _create_agent(self, state_container: dict):
        """요청별 ReAct 에이전트 생성

        매 요청마다 새로운 도구 클로저를 생성하여
        동시 요청 간 상태 충돌을 방지합니다.

        Args:
            state_container: 요청별 상태 컨테이너

        Returns:
            컴파일된 ReAct 에이전트 그래프
        """
        tools = create_tools(
            state_container=state_container,
            place_resolver=self.place_resolver,
            event_edit_agent=self.event_edit_agent,
            consistency_checker=self.consistency_checker,
            place_search=self.place_search,
            tavily_tool=self.tavily_tool,
            backend_client=self.backend_client,
        )

        agent = create_react_agent(
            model=self.langchain_client.llm,
            tools=tools,
            checkpointer=self.checkpointer,
        )

        return agent

    @observe(name="orchestrator")
    async def run(
        self,
        session_id: str,
        user_message: str,
        current_itinerary: Optional[ItineraryResponse] = None,
        user_jwt: Optional[str] = None,
        backend_itinerary_data: Optional[dict] = None,
    ) -> dict:
        """오케스트레이터 실행 (진입점)

        Args:
            session_id: 대화 세션 ID
            user_message: 사용자 메시지
            current_itinerary: 현재 일정 데이터 (외부에서 전달)
            user_jwt: 백엔드 API 인증용 JWT
            backend_itinerary_data: 원본 백엔드 GET 응답 (dayId, activityId 매핑용)

        Returns:
            dict: 실행 결과
                - response: 최종 응답 텍스트
                - current_itinerary: (변경 시) 업데이트된 일정
        """
        # 1. 요청별 상태 컨테이너 생성
        state_container = {
            "current_itinerary": current_itinerary,
            "user_jwt": user_jwt,
            "backend_itinerary_data": backend_itinerary_data,
        }

        # 2. 요청별 에이전트 생성 (도구 클로저 분리)
        agent = self._create_agent(state_container)

        # 3. MongoDB에서 히스토리 로드 → LangChain 메시지로 변환
        history_messages = await self._load_history_as_messages(session_id)

        # 4. 시스템 프롬프트 빌드
        has_itinerary = current_itinerary is not None
        itinerary_summary = ""
        if has_itinerary:
            itinerary_summary = summarize_itinerary(current_itinerary)
        system_prompt = build_system_prompt(has_itinerary, itinerary_summary)

        # 5. 메시지 조립
        messages = [SystemMessage(content=system_prompt)]
        messages.extend(history_messages)
        messages.append(HumanMessage(content=user_message))

        # 6. Langfuse 콜백
        callbacks = []
        handler = get_langfuse_handler()
        if handler:
            callbacks.append(handler)

        config = {
            "configurable": {"thread_id": session_id},
            "tags": ["orchestrator-react"]
        }
        if callbacks:
            config["callbacks"] = callbacks

        # 7. ReAct 에이전트 실행
        try:
            logger.info(f"ReAct 에이전트 실행: {messages}")
            result = await agent.ainvoke(
                {"messages": messages},
                config=config,
            )

            # 마지막 AIMessage에서 응답 텍스트 추출
            response_text = self._extract_response(result)

        except Exception as e:
            logger.error(f"ReAct 에이전트 실행 실패: {e}")
            response_text = "죄송합니다. 요청을 처리하는 중 오류가 발생했습니다."

        # 8. 히스토리 저장 (user + assistant)
        await self._save_history(session_id, user_message, response_text)

        # 9. 결과 반환 (기존 인터페이스 호환)
        return {
            "response": response_text,
            "current_itinerary": state_container.get("current_itinerary"),
        }

    @observe(name="orchestrator-resume")
    async def resume(
        self,
        session_id: str,
        user_answer: str,
    ) -> dict:
        """중단된 오케스트레이터 재개

        interrupt()로 일시정지된 그래프를 사용자 응답으로 재개합니다.

        Args:
            session_id: 대화 세션 ID
            user_answer: 사용자의 보충 답변

        Returns:
            dict: 재개 후 실행 결과
        """
        from langgraph.types import Command

        callbacks = []
        handler = get_langfuse_handler()
        if handler:
            callbacks.append(handler)

        config = {
            "configurable": {"thread_id": session_id},
            "tags": ["orchestrator-resume"]
        }
        if callbacks:
            config["callbacks"] = callbacks

        # 빈 state_container로 에이전트 재생성 (resume은 checkpointer 상태 사용)
        state_container = {}
        agent = self._create_agent(state_container)

        try:
            result = await agent.ainvoke(
                Command(resume=user_answer),
                config=config,
            )
            response_text = self._extract_response(result)
        except Exception as e:
            logger.error(f"ReAct 에이전트 재개 실패: {e}")
            response_text = "죄송합니다. 요청을 처리하는 중 오류가 발생했습니다."

        await self._save_history(session_id, user_answer, response_text)

        return {
            "response": response_text,
            "current_itinerary": state_container.get("current_itinerary"),
        }

    # ─── 내부 헬퍼 ─────────────────────────────────────────

    async def _load_history_as_messages(self, session_id: str) -> list:
        """MongoDB 히스토리를 LangChain 메시지 리스트로 변환

        Args:
            session_id: 세션 ID

        Returns:
            list: LangChain BaseMessage 리스트
        """
        if not session_id:
            return []

        try:
            raw_messages = await self.history_store.get_messages(
                session_id=session_id,
                limit=MAX_HISTORY_TURNS * 2,
            )
        except Exception as e:
            logger.error(f"히스토리 로드 실패: {e}")
            return []

        messages = []
        for msg in raw_messages:
            role = msg.get("role", "")
            content = msg.get("content", "")
            if role == "user":
                messages.append(HumanMessage(content=content))
            elif role == "assistant":
                messages.append(AIMessage(content=content))
            # system 메시지는 무시 (시스템 프롬프트는 매번 새로 생성)

        logger.debug(f"히스토리 로드: session={session_id}, {len(messages)}개 메시지")
        return messages

    async def _save_history(
        self,
        session_id: str,
        user_message: str,
        response: str,
    ) -> None:
        """대화 히스토리를 MongoDB에 저장

        Args:
            session_id: 세션 ID
            user_message: 사용자 메시지
            response: 어시스턴트 응답
        """
        if not session_id:
            return

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

    @staticmethod
    def _extract_response(result: dict) -> str:
        """ReAct 에이전트 결과에서 최종 응답 텍스트 추출

        Args:
            result: agent.ainvoke() 결과

        Returns:
            str: 최종 응답 텍스트
        """
        messages = result.get("messages", [])

        # 뒤에서부터 마지막 AIMessage를 찾음
        for msg in reversed(messages):
            if isinstance(msg, AIMessage) and msg.content:
                # tool_calls가 있는 중간 메시지가 아닌 최종 응답만
                if not msg.tool_calls:
                    return msg.content

        return "요청을 처리했습니다."
