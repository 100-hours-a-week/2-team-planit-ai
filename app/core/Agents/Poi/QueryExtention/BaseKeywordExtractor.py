from abc import ABC, abstractmethod
from typing import List


class BaseKeywordExtractor(ABC):
    """키워드 추출 에이전트의 추상 기본 클래스"""
    
    @abstractmethod
    async def extract_keywords(self, persona_summary: str) -> List[str]:
        """
        페르소나에서 여행 키워드 추출
        
        Args:
            persona_summary: 여행자 페르소나 요약
            
        Returns:
            추출된 검색 키워드 리스트
        """
        pass
