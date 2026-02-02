"""
의존성 팩토리: FastAPI Depends()에서 사용할 서비스 객체 생성

NOTE: 매 요청마다 객체를 생성하는 구조. 이후 싱글턴/앱 시작 시 초기화로 최적화 가능.
"""
from app.core.config import settings
from app.core.LLMClient.VllmClient import VllmClient
from app.core.LLMClient.LangchainClient import LangchainClient
from app.core.Agents.Persona.TravelPersonaAgent import TravelPersonaAgent
from app.core.Agents.Poi.PoiGraph import PoiGraph
from app.core.Agents.ItineraryPlan.Planner import Planner
from app.service.Ininerary.gen_init_Ininerary import GenInitItineraryService

from app.core.Prompt.PersonaAgentPrompt import PERSONA_SYSTEM_PROMPT, PERSONA_GENTERATE_PROMPT


def get_gen_itinerary_service() -> GenInitItineraryService:
    llm_client = VllmClient()
    langchain_client = LangchainClient()

    persona_agent = TravelPersonaAgent(
        llm_client=llm_client,
        persona_prompt=PERSONA_GENTERATE_PROMPT,
        system_prompt=PERSONA_SYSTEM_PROMPT,
    )

    poi_graph = PoiGraph(
        llm_client=llm_client,
        rerank_top_n=5,
        keyword_k=3,
        embedding_k=5,
        web_search_k=3,
        final_poi_count=15,
    )

    planner = Planner(
        llm_client=llm_client,
        langchain_client=langchain_client,
        poi_graph=poi_graph,
        google_maps_api_key=settings.google_maps_api_key,
    )

    return GenInitItineraryService(
        travel_persona_agent=persona_agent,
        poi_graph=poi_graph,
        planner=planner,
    )
