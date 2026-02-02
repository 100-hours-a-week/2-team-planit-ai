"""
ConstraintValidAgent: 정적 제약 조건 검증

주요 기능:
- 예산 초과 여부 검증
- 일일 시간 초과 여부 검증
- 구체적인 수정 피드백 반환
"""
from typing import List, Optional

from app.core.models.ItineraryAgentDataclass.itinerary import Itinerary


class ConstraintValidAgent:
    """예산/시간 제약 조건 검증 에이전트"""
    
    # 기본 설정: 하루 최대 활동 시간 (분)
    DEFAULT_MAX_DAILY_MINUTES = 12 * 60  # 12시간
    
    def __init__(
        self, 
        max_daily_minutes: int = DEFAULT_MAX_DAILY_MINUTES
    ):
        """
        Args:
            max_daily_minutes: 하루 최대 활동 시간 (분)
        """
        self.max_daily_minutes = max_daily_minutes
    
    def validate(
        self, 
        itineraries: List[Itinerary], 
        total_budget: int,
        travel_start_date: str,
        travel_end_date: str
    ) -> Optional[str]:
        """
        일정의 제약 조건 검증
        
        Args:
            itineraries: 검증할 일정 리스트
            total_budget: 총 예산
            travel_start_date: 여행 시작일
            travel_end_date: 여행 종료일
            
        Returns:
            수정 필요 시 피드백 문자열, 통과 시 None
        """
        feedbacks = []
        
        # 1. 예산 검증
        budget_feedback = self._validate_budget(itineraries, total_budget)
        if budget_feedback:
            feedbacks.append(budget_feedback)
        
        # 2. 시간 검증
        time_feedback = self._validate_daily_time(itineraries)
        if time_feedback:
            feedbacks.append(time_feedback)
        
        # 3. 날짜 범위 검증
        date_feedback = self._validate_date_range(itineraries, travel_start_date, travel_end_date)
        if date_feedback:
            feedbacks.append(date_feedback)
        
        if feedbacks:
            return "\n".join(feedbacks)
        return None
    
    def _validate_budget(
        self, 
        itineraries: List[Itinerary], 
        total_budget: int
    ) -> Optional[str]:
        """예산 검증 (POI의 price_level 기반 추정)"""
        # 간단한 예산 추정: POI 개수 * 평균 비용
        # 실제로는 각 POI의 price_level을 기반으로 계산해야 함
        total_pois = sum(len(it.pois) for it in itineraries)
        
        # 가정: 각 POI 방문에 평균 30,000원 소요
        estimated_cost = total_pois * 30000
        
        if estimated_cost > total_budget:
            over_amount = estimated_cost - total_budget
            reduction_needed = (over_amount // 30000) + 1
            return (
                f"[예산 초과] 예상 비용 {estimated_cost:,}원이 예산 {total_budget:,}원을 초과합니다. "
                f"약 {reduction_needed}개의 POI를 줄이거나 저렴한 장소로 교체해주세요."
            )
        return None
    
    def _validate_daily_time(
        self,
        itineraries: List[Itinerary]
    ) -> Optional[str]:
        """일일 시간 검증"""
        over_days = []

        for itinerary in itineraries:
            if itinerary.schedule:
                total = self._calc_schedule_duration(itinerary)
            else:
                total = itinerary.total_duration_minutes

            if total > self.max_daily_minutes:
                over_hours = total // 60
                max_hours = self.max_daily_minutes // 60
                over_days.append(
                    f"{itinerary.date}: {over_hours}시간 (최대 {max_hours}시간 권장)"
                )

        if over_days:
            days_str = ", ".join(over_days)
            return (
                f"[시간 초과] 다음 날짜의 일정이 너무 깁니다: {days_str}. "
                f"일부 POI를 다른 날로 이동하거나 제거해주세요."
            )
        return None

    @staticmethod
    def _calc_schedule_duration(itinerary: Itinerary) -> int:
        """schedule 기반 총 소요 시간 계산 (첫 POI 시작 ~ 마지막 POI 종료)"""
        if not itinerary.schedule:
            return 0

        first = itinerary.schedule[0]
        last = itinerary.schedule[-1]

        first_h, first_m = map(int, first.start_time.split(":"))
        last_h, last_m = map(int, last.start_time.split(":"))

        start_minutes = first_h * 60 + first_m
        end_minutes = last_h * 60 + last_m + last.duration_minutes

        return end_minutes - start_minutes
    
    def _validate_date_range(
        self,
        itineraries: List[Itinerary],
        travel_start_date: str,
        travel_end_date: str
    ) -> Optional[str]:
        """날짜 범위 검증"""
        if not itineraries:
            return "[일정 없음] 일정이 생성되지 않았습니다."
        
        dates = [it.date for it in itineraries]
        min_date = min(dates)
        max_date = max(dates)
        
        feedbacks = []
        if min_date < travel_start_date:
            feedbacks.append(f"일정 시작일({min_date})이 여행 시작일({travel_start_date})보다 앞섭니다.")
        if max_date > travel_end_date:
            feedbacks.append(f"일정 종료일({max_date})이 여행 종료일({travel_end_date})보다 늦습니다.")
        
        if feedbacks:
            return "[날짜 범위 오류] " + " ".join(feedbacks)
        return None
