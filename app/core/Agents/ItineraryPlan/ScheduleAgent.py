"""
ScheduleAgent: 일정 균형 조정

주요 기능:
- 하루 POI 과다 시 다음 날로 이전 제안
- 일정 삭제 제안
"""
from typing import List, Optional

from app.core.models.ItineraryAgentDataclass.itinerary import Itinerary


class ScheduleAgent:
    """일정 균형 조정 에이전트"""
    
    # 기본 설정: 하루 최적 POI 개수
    DEFAULT_OPTIMAL_POI_COUNT = 4
    DEFAULT_MAX_POI_COUNT = 6
    
    def __init__(
        self, 
        optimal_poi_count: int = DEFAULT_OPTIMAL_POI_COUNT,
        max_poi_count: int = DEFAULT_MAX_POI_COUNT
    ):
        """
        Args:
            optimal_poi_count: 하루 최적 POI 개수
            max_poi_count: 하루 최대 POI 개수
        """
        self.optimal_poi_count = optimal_poi_count
        self.max_poi_count = max_poi_count
    
    def analyze(
        self, 
        itineraries: List[Itinerary]
    ) -> Optional[str]:
        """
        일정 균형 분석 및 조정 방안 제안
        
        Args:
            itineraries: 분석할 일정 리스트
            
        Returns:
            조정 필요 시 피드백 문자열, 통과 시 None
        """
        if not itineraries:
            return None
        
        feedbacks = []
        
        # 1. POI 과다 날짜 확인
        overloaded_days = self._find_overloaded_days(itineraries)
        if overloaded_days:
            feedbacks.append(self._suggest_redistribution(overloaded_days, itineraries))
        
        # 2. POI 부족 날짜 확인 (빈 날짜)
        underloaded_days = self._find_underloaded_days(itineraries)
        if underloaded_days:
            feedbacks.append(self._suggest_filling(underloaded_days))
        
        if feedbacks:
            return "\n".join(feedbacks)
        return None
    
    def _find_overloaded_days(
        self, 
        itineraries: List[Itinerary]
    ) -> List[Itinerary]:
        """POI가 과다한 날짜 찾기"""
        return [it for it in itineraries if len(it.pois) > self.max_poi_count]
    
    def _find_underloaded_days(
        self, 
        itineraries: List[Itinerary]
    ) -> List[Itinerary]:
        """POI가 부족한 날짜 찾기"""
        return [it for it in itineraries if len(it.pois) == 0]
    
    def _suggest_redistribution(
        self, 
        overloaded_days: List[Itinerary],
        all_itineraries: List[Itinerary]
    ) -> str:
        """과부하 날짜 재분배 제안"""
        suggestions = []
        
        for itinerary in overloaded_days:
            excess = len(itinerary.pois) - self.optimal_poi_count
            poi_names = [poi.name for poi in itinerary.pois[-excess:]]
            
            # 여유 있는 날짜 찾기
            available_days = [
                it.date for it in all_itineraries 
                if len(it.pois) < self.optimal_poi_count and it.date != itinerary.date
            ]
            
            if available_days:
                suggestion = (
                    f"{itinerary.date}: POI {len(itinerary.pois)}개로 과다합니다. "
                    f"'{', '.join(poi_names[:3])}' 등을 {available_days[0]}로 이동하세요."
                )
            else:
                suggestion = (
                    f"{itinerary.date}: POI {len(itinerary.pois)}개로 과다합니다. "
                    f"'{', '.join(poi_names[:3])}' 등을 삭제하거나 다른 날로 이동하세요."
                )
            suggestions.append(suggestion)
        
        return "[일정 과다] " + " ".join(suggestions)
    
    def _suggest_filling(
        self, 
        underloaded_days: List[Itinerary]
    ) -> str:
        """빈 날짜 채우기 제안"""
        empty_dates = [it.date for it in underloaded_days]
        return (
            f"[빈 일정] {', '.join(empty_dates)} 날짜에 일정이 없습니다. "
            f"다른 날의 POI를 이동하거나 새로운 POI를 추가해주세요."
        )
