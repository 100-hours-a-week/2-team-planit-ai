"""
InfoAgent: 정보 소개 브랜치 오케스트레이터 (LangGraph)

사용자 의도에 따라 추천/정보전달 브랜치를 조율합니다:
- INFO_RECOMMEND → PlaceSearchAgent → RecommendAgent (장소 추천)
- INFO_DELIVERY → InfoDeliveryAgent (일반 정보 검색 + 충분성 루프)
"""
import logging
from typing import Optional

from langgraph.graph import END, StateGraph

from app.core.Agents.Chat.ChatState import ChatState, UserIntent
from app.core.Agents.Chat.InfoAgent.InfoDeliveryAgent import InfoDeliveryAgent
from app.core.Agents.Chat.InfoAgent.PlaceSearchAgent import PlaceSearchAgent
from app.core.Agents.Chat.InfoAgent.RecommendAgent import RecommendAgent
from app.core.Agents.Chat.InfoAgent.TavilySearchTool import TavilySearchTool
from app.core.Agents.Poi.PoiAliasCache import PoiAliasCache
from app.core.Agents.Poi.PoiMapper.GoogleMapsPoiMapper import GoogleMapsPoiMapper
from app.core.Agents.Poi.VectorDB.VectorSearchAgent import VectorSearchAgent
from app.core.LLMClient.BaseLlmClient import BaseLLMClient
from app.core.langfuse_setup import get_langfuse_handler

logger = logging.getLogger(__name__)


class InfoAgent:
    """정보 소개 브랜치 오케스트레이터

    LangGraph StateGraph로 아래 흐름을 관리합니다:
    route → recommend / deliver → response

    Flow:
    1. route_intent: 사용자 의도에 따라 브랜치 선택
       - INFO_RECOMMEND → recommend (장소 추천)
       - INFO_DELIVERY → deliver (일반 정보)
    2. recommend: PlaceSearchAgent + RecommendAgent
    3. deliver: InfoDeliveryAgent (충분성 루프 포함)
    """

    def __init__(
        self,
        llm_client: BaseLLMClient,
        vector_search: Optional[VectorSearchAgent] = None,
        alias_cache: Optional[PoiAliasCache] = None,
        google_mapper: Optional[GoogleMapsPoiMapper] = None,
        tavily_tool: Optional[TavilySearchTool] = None,
    ):
        """
        Args:
            llm_client: LLM 클라이언트
            vector_search: VectorDB 검색 에이전트 (None이면 벡터 검색 비활성화)
            alias_cache: SQLite 별칭 캐시
            google_mapper: Google Maps 매퍼
            tavily_tool: Tavily 검색 도구 (공유 인스턴스)
        """
        self.llm_client = llm_client

        # 공유 도구
        _tavily = tavily_tool or TavilySearchTool()
        _alias_cache = alias_cache or PoiAliasCache()
        _google_mapper = google_mapper or GoogleMapsPoiMapper()

        # PlaceSearchAgent 조립
        place_search = PlaceSearchAgent(
            alias_cache=_alias_cache,
            vector_search=vector_search,
            google_mapper=_google_mapper,
            tavily_tool=_tavily,
        )

        # 하위 에이전트
        self.recommend_agent = RecommendAgent(
            llm_client=llm_client,
            place_search=place_search,
        )
        self.delivery_agent = InfoDeliveryAgent(
            llm_client=llm_client,
            tavily_tool=_tavily,
        )

        self.graph = self._build_graph()

    def _build_graph(self) -> StateGraph:
        """LangGraph 워크플로우 빌드"""
        graph = StateGraph(ChatState)

        # 노드 추가
        graph.add_node("recommend", self._recommend)
        graph.add_node("deliver", self._deliver)

        # 엔트리: 의도에 따라 분기
        graph.set_conditional_entry_point(
            self._route_intent,
            {
                "recommend": "recommend",
                "deliver": "deliver",
                "end": END,
            },
        )

        # 각 브랜치 → 종료
        graph.add_edge("recommend", END)
        graph.add_edge("deliver", END)

        return graph.compile()

    # ─── 노드 구현 ───────────────────────────────────────

    async def _recommend(self, state: ChatState) -> dict:
        """장소 추천 노드"""
        return await self.recommend_agent.recommend(state)

    async def _deliver(self, state: ChatState) -> dict:
        """정보 전달 노드"""
        return await self.delivery_agent.deliver(state)

    # ─── 라우팅 함수 ─────────────────────────────────────

    def _route_intent(self, state: ChatState) -> str:
        """사용자 의도에 따른 브랜치 라우팅"""
        intent = state.get("user_intent", "")

        if intent == UserIntent.INFO_RECOMMEND:
            return "recommend"
        elif intent == UserIntent.INFO_DELIVERY:
            return "deliver"
        else:
            logger.warning(f"InfoAgent에 전달된 예상 외 intent: {intent}")
            return "deliver"

    # ─── 실행 ────────────────────────────────────────────

    async def run(self, state: ChatState) -> ChatState:
        """정보 소개 워크플로우 실행

        Args:
            state: 현재 대화 상태

        Returns:
            ChatState: 업데이트된 대화 상태
        """
        callbacks = []
        handler = get_langfuse_handler(tags=["info-agent"])
        if handler:
            callbacks.append(handler)

        result = await self.graph.ainvoke(
            state,
            config={"callbacks": callbacks} if callbacks else None,
        )
        return result
