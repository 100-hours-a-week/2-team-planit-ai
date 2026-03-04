"""
의존성 팩토리: FastAPI Depends()에서 사용할 서비스 객체 생성

모든 의존성을 모듈 레벨 싱글턴으로 관리하여
동시 요청 시 불필요한 객체 재생성을 방지합니다.
"""
from app.core.config import settings
from app.core.LLMClient.VllmClient import VllmClient
from app.core.LLMClient.LangchainClient import LangchainClient
from app.core.Agents.Persona.TravelPersonaAgent import TravelPersonaAgent
from app.core.Agents.Poi.PoiGraph import PoiGraph
from app.core.Agents.ItineraryPlan.Planner import Planner
from app.service.Ininerary.gen_init_Ininerary import GenInitItineraryService
from app.core.Agents.Poi.VectorDB.EmbeddingPipeline.EmbeddingPipeline import EmbeddingPipeline
from app.core.Agents.Poi.VectorDB.EmbeddingPipeline.PersonaEmbeddingPipeline import PersonaEmbeddingPipeline
from app.core.Agents.Poi.VectorDB.VectorSearchAgent import VectorSearchAgent

from app.core.Prompt.PersonaAgentPrompt import PERSONA_SYSTEM_PROMPT, PERSONA_GENTERATE_PROMPT

# 챗봇 관련 import
from app.core.BackendClient import BackendClient
from app.core.Agents.Chat.ScheduleChange.PlaceResolver import PlaceResolver
from app.core.Agents.Chat.ScheduleChange.EventEditAgent import EventEditAgent
from app.core.Agents.Chat.ScheduleChange.ConsistencyChecker import ConsistencyChecker
from app.core.Agents.Chat.InfoAgent.PlaceSearchAgent import PlaceSearchAgent
from app.core.Agents.Chat.InfoAgent.TavilySearchTool import TavilySearchTool
from app.core.Agents.Chat.History.MongoHistoryStore import MongoHistoryStore
from app.core.Agents.Chat.Orchestrator import Orchestrator
from app.service.Chatbot.ChatbotService import ChatbotService

# ── 모듈 레벨 싱글턴: 모든 요청이 동일한 객체를 공유 ──
_embedding_pipeline = EmbeddingPipeline()
_vector_search_agent = VectorSearchAgent(
    embedding_pipeline=_embedding_pipeline,
)
_llm_client = VllmClient()
_langchain_client = LangchainClient(
    base_url=settings.vllm_base_url,
)
_persona_agent = TravelPersonaAgent(
    llm_client=_llm_client,
    persona_prompt=PERSONA_GENTERATE_PROMPT,
    system_prompt=PERSONA_SYSTEM_PROMPT,
)
_poi_graph = PoiGraph(
    llm_client=_llm_client,
    rerank_min_score=0.5,
    keyword_k=3,
    embedding_k=5,
    web_search_k=3,
    final_poi_count=15,
    vector_search_agent=_vector_search_agent,
)
_planner = Planner(
    llm_client=_llm_client,
    langchain_client=_langchain_client,
    poi_graph=_poi_graph,
    google_maps_api_key=settings.google_maps_api_key,
)
_gen_itinerary_service = GenInitItineraryService(
    travel_persona_agent=_persona_agent,
    poi_graph=_poi_graph,
    planner=_planner,
)

# ── 챗봇 관련 싱글턴 ──
_backend_client = BackendClient()
_place_resolver = PlaceResolver(
    vector_search_agent=_vector_search_agent,
)
_history_store = MongoHistoryStore()
_tavily_tool = TavilySearchTool()
_event_edit_agent = EventEditAgent(llm_client=_llm_client)
_consistency_checker = ConsistencyChecker(
    total_budget=1_000_000,
    travel_start_date="2026-01-01",
    travel_end_date="2026-01-05",
)
_place_search = PlaceSearchAgent(
    vector_search=_vector_search_agent,
    tavily_tool=_tavily_tool,
)
_orchestrator = Orchestrator(
    langchain_client=_langchain_client,
    llm_client=_llm_client,
    history_store=_history_store,
    place_resolver=_place_resolver,
    event_edit_agent=_event_edit_agent,
    consistency_checker=_consistency_checker,
    place_search=_place_search,
    tavily_tool=_tavily_tool,
    backend_client=_backend_client,
)
_chatbot_service = ChatbotService(
    orchestrator=_orchestrator,
    backend_client=_backend_client,
)


def get_gen_itinerary_service() -> GenInitItineraryService:
    return _gen_itinerary_service


def get_chatbot_service() -> ChatbotService:
    return _chatbot_service

