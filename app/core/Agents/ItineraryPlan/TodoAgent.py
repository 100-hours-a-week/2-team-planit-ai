"""
TodoAgent: Task Queue 기반 오케스트레이터

주요 기능:
- 상태 분석 후 실행할 태스크 목록(Task Queue) 생성
- Rule-based 로직으로 LLM 호출 없이 빠른 결정
"""
from typing import List, Optional

from app.core.models.ItineraryAgentDataclass.itinerary import ItineraryPlanState


class TodoAgent:
    """Task Queue 기반 하위 에이전트 오케스트레이터"""
    
    # 에이전트 이름 상수
    DISTANCE_CALCULATE = "DistanceCalculateAgent"
    CONSTRAINT_VALID = "ConstraintValidAgent"
    SCHEDULE = "ScheduleAgent"
    ITINERARY_PLAN = "ItineraryPlanAgent"
    POI_ENRICH = "PoiEnrichAgent"
    INFO_SEARCH = "InfoSearchAgent"
    
    def plan_tasks(self, state: ItineraryPlanState) -> List[str]:
        """
        현재 상태를 분석하여 실행할 Task Queue 생성
        
        Args:
            state: 현재 LangGraph 상태
            
        Returns:
            실행할 에이전트 이름 리스트 (FIFO 순서)
        """
        task_queue = []
        
        # 1. 피드백이 있으면 일정 재생성은 LangGraph 라우팅에서 처리
        #    (_route_result -> "needs_revision" -> generate_itinerary)
        if state.get("validation_feedback") or state.get("schedule_feedback"):
            pass  # generate_itinerary 노드에서 이미 재생성됨
        
        # 2. POI 변경이 있으면 거리 계산 필요
        if state.get("is_poi_changed", True):
            task_queue.append(self.DISTANCE_CALCULATE)
        
        # 3. 제약 조건 검증
        task_queue.append(self.CONSTRAINT_VALID)
        
        # 4. 일정 균형 조정
        task_queue.append(self.SCHEDULE)
        
        return task_queue
    
    def get_next_task(self, state: ItineraryPlanState) -> Optional[str]:
        """
        큐에서 다음 태스크 가져오기
        
        Args:
            state: 현재 LangGraph 상태
            
        Returns:
            다음 실행할 에이전트 이름, 큐가 비어있으면 None
        """
        task_queue = state.get("task_queue", [])
        if task_queue:
            return task_queue[0]
        return None
    
    def pop_task(self, state: ItineraryPlanState) -> Optional[str]:
        """
        큐에서 태스크를 꺼내서 반환 (상태 변경 필요)
        
        Args:
            state: 현재 LangGraph 상태
            
        Returns:
            꺼낸 태스크 이름, 큐가 비어있으면 None
        """
        task_queue = state.get("task_queue", [])
        if task_queue:
            return task_queue.pop(0)
        return None
    
    def is_complete(self, state: ItineraryPlanState) -> bool:
        """
        모든 태스크가 완료되었는지 확인
        
        Args:
            state: 현재 LangGraph 상태
            
        Returns:
            완료 여부
        """
        task_queue = state.get("task_queue", [])
        return len(task_queue) == 0
    
    def check_poi_changed(
        self, 
        current_poi_ids: List[str], 
        previous_poi_ids: List[str]
    ) -> bool:
        """
        POI 목록 변경 여부 확인
        
        Args:
            current_poi_ids: 현재 POI ID 리스트
            previous_poi_ids: 이전 POI ID 리스트
            
        Returns:
            변경 여부
        """
        if len(current_poi_ids) != len(previous_poi_ids):
            return True
        return set(current_poi_ids) != set(previous_poi_ids)
