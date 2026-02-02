import logging

from app.core.Agents.Poi.PoiGraph import PoiGraph
from app.core.Agents.ItineraryPlan.Planner import Planner
from app.core.Agents.Persona.TravelPersonaAgent import TravelPersonaAgent
from app.schemas.persona import ItineraryRequest
from app.schemas.Itinerary import ItineraryResponse, gen_itinerary

logger = logging.getLogger(__name__)


class GenInitItineraryService:
    def __init__(
        self,
        travel_persona_agent: TravelPersonaAgent,
        poi_graph: PoiGraph,
        planner: Planner,
    ):
        self. travel_persona_agent = travel_persona_agent
        self.poi_graph = poi_graph
        self.planner = planner

    async def gen_init_itinerary(self, request: ItineraryRequest) -> ItineraryResponse:
        """초기 일정 생성 파이프라인: 페르소나 → POI → 일정"""

        # 1. 페르소나 생성
        logger.info("Step 1: 페르소나 생성 시작")
        persona_summary = await self.travel_persona_agent.run(
            itinerary_request=request,
            qa_history=[],
        )
        logger.info(f"Step 1 완료: persona_summary 길이={len(persona_summary)}")

        # 2. POI 리스트 생성
        logger.info("Step 2: POI 리스트 생성 시작")
        poi_list, _ = await self.poi_graph.run(
            persona_summary=persona_summary,
            travel_destination=request.travelCity,
            start_date=request.arrivalDate,
            end_date=request.departureDate,
        )
        logger.info(f"Step 2 완료: POI {len(poi_list)}개")

        # 3. 일정 생성
        logger.info("Step 3: 일정 생성 시작")
        itineraries = await self.planner.run(
            pois=poi_list[:10],
            travel_destination=request.travelCity,
            travel_start_date=request.arrivalDate,
            travel_end_date=request.departureDate,
            total_budget=request.totalBudget,
            persona_summary=persona_summary,
        )
        logger.info(f"Step 3 완료: 일정 {len(itineraries)}일")

        # 4. 응답 변환
        return gen_itinerary(trip_id=request.tripId, itineraries=itineraries)
