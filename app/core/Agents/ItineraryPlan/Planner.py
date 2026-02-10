"""
Planner: LangGraph를 이용한 에이전트 오케스트레이션

주요 기능:
- 모든 하위 에이전트 조율
- Task Queue 기반 연속 작업 실행
- Fallback 전략 (5회 반복 후 최선 결과 반환)
"""
import logging
from typing import List, Optional
from langgraph.graph import StateGraph, END

logger = logging.getLogger(__name__)

from app.core.LLMClient.BaseLlmClient import BaseLLMClient
from app.core.LLMClient.LangchainClient import LangchainClient
from app.core.models.PoiAgentDataclass.poi import PoiData
from app.core.models.ItineraryAgentDataclass.itinerary import (
    Itinerary,
    ItineraryPlanState,
)
from app.core.Agents.ItineraryPlan.TodoAgent import TodoAgent
from app.core.Agents.ItineraryPlan.ItineraryPlanAgent import ItineraryPlanAgent
from app.core.Agents.ItineraryPlan.DistanceCalculateAgent import DistanceCalculateAgent
from app.core.Agents.ItineraryPlan.ConstraintValidAgent import ConstraintValidAgent
from app.core.Agents.ItineraryPlan.ScheduleAgent import ScheduleAgent
from app.core.Agents.ItineraryPlan.PoiEnrichAgent import PoiEnrichAgent
from app.core.Agents.Poi.PoiGraph import PoiGraph


class Planner:
    """LangGraph 기반 여행 일정 플래너"""
    
    MAX_ITERATIONS = 5
    
    def __init__(
        self,
        llm_client: BaseLLMClient,
        langchain_client: LangchainClient,
        poi_graph: Optional[PoiGraph] = None,
        google_maps_api_key: Optional[str] = None,
        transfer_cache_db_path: Optional[str] = None
    ):
        """
        Args:
            llm_client: LLM 클라이언트 (다른 에이전트용)
            langchain_client: LangChain 클라이언트 (ItineraryPlanAgent용)
            poi_graph: POI 검색 그래프 (None이면 생성 안 함)
            google_maps_api_key: Google Maps API 키
            transfer_cache_db_path: Transfer 캐시 SQLite DB 경로 (None이면 기본 경로)
        """
        # 에이전트 초기화
        self.todo_agent = TodoAgent()
        self.itinerary_plan_agent = ItineraryPlanAgent(langchain_client)
        self.distance_calculate_agent = DistanceCalculateAgent(google_maps_api_key, db_path=transfer_cache_db_path)
        self.constraint_valid_agent = ConstraintValidAgent()
        self.schedule_agent = ScheduleAgent()
        
        # POI 보충 에이전트 (poi_graph가 있을 때만)
        self.poi_enrich_agent = PoiEnrichAgent(poi_graph) if poi_graph else None
        
        # 그래프 빌드
        self.graph = self._build_graph()
    
    def _build_graph(self) -> StateGraph:
        """LangGraph 워크플로우 빌드"""
        workflow = StateGraph(ItineraryPlanState)
        
        # 노드 추가
        workflow.add_node("check_poi_sufficiency", self._check_poi_sufficiency)
        workflow.add_node("enrich_poi", self._enrich_poi)
        workflow.add_node("generate_itinerary", self._generate_itinerary)
        workflow.add_node("plan_tasks", self._plan_tasks)
        workflow.add_node("execute_task", self._execute_task)
        workflow.add_node("check_result", self._check_result)
        
        workflow.set_entry_point("generate_itinerary")
        workflow.add_edge("generate_itinerary", END)
        

        # # 엔트리 포인트
        # workflow.set_entry_point("check_poi_sufficiency")
        
        # # 엣지 연결
        # workflow.add_conditional_edges(
        #     "check_poi_sufficiency",
        #     self._route_poi_check,
        #     {
        #         "enrich": "enrich_poi",
        #         "sufficient": "generate_itinerary"
        #     }
        # )
        # workflow.add_edge("enrich_poi", "check_poi_sufficiency")
        # workflow.add_edge("generate_itinerary", "plan_tasks")
        # workflow.add_conditional_edges(
        #     "plan_tasks",
        #     self._route_task_queue,
        #     {
        #         "has_task": "execute_task",
        #         "empty": "check_result"
        #     }
        # )
        # workflow.add_conditional_edges(
        #     "execute_task",
        #     self._route_task_queue,
        #     {
        #         "has_task": "execute_task",
        #         "empty": "check_result"
        #     }
        # )
        # workflow.add_conditional_edges(
        #     "check_result",
        #     self._route_result,
        #     {
        #         "needs_revision": "generate_itinerary",
        #         "complete": END
        #     }
        # )
        
        return workflow.compile()
    
    # ===== 노드 구현 =====
    
    MAX_POI_ENRICH_ATTEMPTS = 3

    async def _check_poi_sufficiency(self, state: ItineraryPlanState) -> dict:
        """POI 충분성 확인 (최대 시도 횟수 제한)"""
        pois = state.get("pois", [])
        attempts = state.get("poi_enrich_attempts", 0)

        # 최대 시도 횟수 도달 시 충분한 것으로 간주
        if attempts >= self.MAX_POI_ENRICH_ATTEMPTS:
            logger.info("POI 보충 최대 시도 횟수(%d) 도달, 충분한 것으로 간주", self.MAX_POI_ENRICH_ATTEMPTS)
            return {"is_poi_sufficient": True}

        is_sufficient = len(pois) >= 5 if not self.poi_enrich_agent else self.poi_enrich_agent.is_poi_sufficient(pois)
        logger.info("POI 충분성 확인: POI 수=%d, 충분=%s, 시도 횟수=%d", len(pois), is_sufficient, attempts)
        return {"is_poi_sufficient": is_sufficient}
    
    async def _enrich_poi(self, state: ItineraryPlanState) -> dict:
        """POI 보충 (시도 횟수 증가)"""
        attempts = state.get("poi_enrich_attempts", 0) + 1

        if not self.poi_enrich_agent:
            logger.info("POI 보충 에이전트 없음, 보충 건너뜀 (시도 %d)", attempts)
            return {"poi_enrich_attempts": attempts}

        pois = state.get("pois", [])
        logger.info("POI 보충 시작: 보충 전 POI 수=%d, 시도 %d/%d", len(pois), attempts, self.MAX_POI_ENRICH_ATTEMPTS)

        persona_summary = state.get("persona_summary", "")
        travel_destination = state.get("travel_destination", "")

        enriched_pois = await self.poi_enrich_agent.enrich(
            current_pois=pois,
            persona_summary=persona_summary,
            travel_destination=travel_destination
        )
        logger.info("POI 보충 완료: 보충 후 POI 수=%d", len(enriched_pois))
        return {"pois": enriched_pois, "poi_enrich_attempts": attempts}
    
    async def _generate_itinerary(self, state: ItineraryPlanState) -> dict:
        """일정 생성"""
        # 이전 POI ID 저장 (변경 감지용)
        current_poi_ids = [poi.id for it in state.get("itineraries", []) for poi in it.pois] if state.get("itineraries") else []

        # 반복 횟수 증가
        iteration_count = state.get("iteration_count", 0) + 1

        # 피드백 합치기
        feedback = None
        if state.get("validation_feedback") or state.get("schedule_feedback"):
            feedbacks = []
            if state.get("validation_feedback"):
                feedbacks.append(state["validation_feedback"])
            if state.get("schedule_feedback"):
                feedbacks.append(state["schedule_feedback"])
            feedback = "\n".join(feedbacks)

        logger.info("일정 생성 시작: 반복 %d/%d, 피드백 유무=%s", iteration_count, self.MAX_ITERATIONS, feedback is not None)
        # 일정 생성
        itineraries = await self.itinerary_plan_agent.generate(
            pois=state.get("pois", []),
            travel_destination=state.get("travel_destination", ""),
            travel_start_date=state.get("travel_start_date", ""),
            travel_end_date=state.get("travel_end_date", ""),
            travel_start_time=state.get("travel_start_time", ""),
            travel_end_time=state.get("travel_end_time", ""),
            persona_summary=state.get("persona_summary", ""),
            feedback=feedback
        )

        logger.info("일정 생성 완료: 생성된 일정 수=%d", len(itineraries))

        # 새 POI ID 목록
        new_poi_ids = [poi.id for it in itineraries for poi in it.pois]
        is_poi_changed = self.todo_agent.check_poi_changed(new_poi_ids, current_poi_ids)

        return {
            "itineraries": itineraries,
            "iteration_count": iteration_count,
            "previous_poi_ids": current_poi_ids,
            "is_poi_changed": is_poi_changed,
            "validation_feedback": None,  # 피드백 초기화
            "schedule_feedback": None
        }
    
    async def _plan_tasks(self, state: ItineraryPlanState) -> dict:
        """Task Queue 생성"""
        task_queue = self.todo_agent.plan_tasks(state)
        logger.info("Task Queue 생성: %s", task_queue)
        return {"task_queue": task_queue}
    
    async def _execute_task(self, state: ItineraryPlanState) -> dict:
        """Task Queue에서 태스크 실행"""
        task_queue = state.get("task_queue", [])
        if not task_queue:
            return {}

        current_task = task_queue[0]
        remaining_queue = task_queue[1:]
        logger.info("태스크 실행: %s (남은 태스크 수=%d)", current_task, len(remaining_queue))

        result = {"task_queue": remaining_queue, "current_task": current_task}

        if current_task == TodoAgent.DISTANCE_CALCULATE:
            # 거리 계산 — 새 Itinerary 객체를 생성하여 상태에 반영
            updated_itineraries = []
            for itinerary in state.get("itineraries", []):
                if itinerary.pois:
                    transfers = await self.distance_calculate_agent.calculate_batch(itinerary.pois)
                    total_transfer_time = sum(t.duration_minutes for t in transfers)
                    if itinerary.schedule:
                        total_poi_time = sum(s.duration_minutes for s in itinerary.schedule)
                    else:
                        total_poi_time = len(itinerary.pois) * 60
                    total_duration = total_transfer_time + total_poi_time
                    updated_itineraries.append(itinerary.model_copy(update={
                        "transfers": transfers,
                        "total_duration_minutes": total_duration,
                    }))
                else:
                    updated_itineraries.append(itinerary)
            result["itineraries"] = updated_itineraries
            total_transfer = sum(it.total_duration_minutes for it in updated_itineraries)
            logger.info("거리 계산 완료: itinerary 수=%d, 총 소요 시간=%d분", len(updated_itineraries), total_transfer)

        elif current_task == TodoAgent.CONSTRAINT_VALID:
            # 제약 조건 검증
            feedback = self.constraint_valid_agent.validate(
                itineraries=state.get("itineraries", []),
                total_budget=state.get("total_budget", 0),
                travel_start_date=state.get("travel_start_date", ""),
                travel_end_date=state.get("travel_end_date", "")
            )
            result["validation_feedback"] = feedback
            logger.info("제약 조건 검증 완료: 피드백 유무=%s", feedback is not None)

            # best_itineraries 업데이트 (Fallback용)
            if not feedback or (state.get("best_itineraries") is None):
                result["best_itineraries"] = state.get("itineraries", [])

        elif current_task == TodoAgent.SCHEDULE:
            # 일정 균형 조정
            feedback = self.schedule_agent.analyze(state.get("itineraries", []))
            result["schedule_feedback"] = feedback
            logger.info("일정 분석 완료: 피드백 유무=%s", feedback is not None)

        return result
    
    async def _check_result(self, state: ItineraryPlanState) -> dict:
        """결과 확인"""
        itineraries = state.get("itineraries", [])
        logger.info("결과 확인: 일정 수=%d, validation_feedback=%s, schedule_feedback=%s",
                     len(itineraries),
                     state.get("validation_feedback") is not None,
                     state.get("schedule_feedback") is not None)
        # Fallback을 위해 상태 유지
        return {}

    # ===== 라우팅 함수 =====

    def _route_poi_check(self, state: ItineraryPlanState) -> str:
        """POI 충분성에 따른 라우팅"""
        if state.get("is_poi_sufficient", True):
            logger.debug("POI 라우팅: sufficient")
            return "sufficient"
        logger.debug("POI 라우팅: enrich")
        return "enrich"

    def _route_task_queue(self, state: ItineraryPlanState) -> str:
        """Task Queue 상태에 따른 라우팅"""
        task_queue = state.get("task_queue", [])
        if task_queue:
            logger.debug("Task Queue 라우팅: has_task (남은 태스크=%d)", len(task_queue))
            return "has_task"
        logger.debug("Task Queue 라우팅: empty")
        return "empty"

    def _route_result(self, state: ItineraryPlanState) -> str:
        """결과에 따른 라우팅"""
        iteration_count = state.get("iteration_count", 0)

        # 최대 반복 횟수 도달 시 완료
        if iteration_count >= self.MAX_ITERATIONS:
            logger.debug("결과 라우팅: complete (최대 반복 횟수 %d 도달)", iteration_count)
            return "complete"

        # 피드백이 있으면 수정 필요
        if state.get("validation_feedback") or state.get("schedule_feedback"):
            logger.debug("결과 라우팅: needs_revision (반복 %d/%d)", iteration_count, self.MAX_ITERATIONS)
            return "needs_revision"

        logger.debug("결과 라우팅: complete (피드백 없음, 반복 %d)", iteration_count)
        return "complete"
    
    # ===== 메인 실행 함수 =====
    
    async def run(
        self,
        pois: List[PoiData],
        travel_destination: str,
        travel_start_date: str,
        travel_end_date: str,
        total_budget: int,
        persona_summary: str
    ) -> List[Itinerary]:
        """
        여행 일정 생성 실행
        
        Args:
            pois: POI 리스트
            travel_destination: 여행지
            travel_start_date: 여행 시작일 (YYYY-MM-DD)
            travel_end_date: 여행 종료일 (YYYY-MM-DD)
            total_budget: 총 예산
            persona_summary: 사용자 페르소나
            
        Returns:
            최종 일정 리스트
        """
        logger.info("여행 일정 생성 시작: 여행지=%s, 기간=%s~%s, 예산=%d, POI 수=%d",
                     travel_destination, travel_start_date, travel_end_date, total_budget, len(pois))

        initial_state: ItineraryPlanState = {
            "pois": pois,
            "travel_destination": travel_destination,
            "travel_start_date": travel_start_date,
            "travel_end_date": travel_end_date,
            "total_budget": total_budget,
            "persona_summary": persona_summary,
            "itineraries": [],
            "validation_feedback": None,
            "schedule_feedback": None,
            "is_poi_sufficient": True,
            "poi_enrich_attempts": 0,
            "iteration_count": 0,
            "previous_poi_ids": [],
            "is_poi_changed": True,
            "best_itineraries": None,
            "task_queue": [],
            "current_task": None
        }

        try:
            result = await self.graph.ainvoke(initial_state)
        except Exception as e:
            logger.error("여행 일정 생성 중 오류 발생: %s", e, exc_info=True)
            raise

        # 최종 결과 반환 (피드백이 있으면 best_itineraries 반환)
        use_fallback = bool(result.get("validation_feedback") or result.get("schedule_feedback"))
        if use_fallback:
            final = result.get("best_itineraries", result.get("itineraries", []))
        else:
            final = result.get("itineraries", [])

        logger.info("여행 일정 생성 완료: 최종 일정 수=%d, fallback 사용=%s, 총 반복=%d",
                     len(final), use_fallback, result.get("iteration_count", 0))
        return final
