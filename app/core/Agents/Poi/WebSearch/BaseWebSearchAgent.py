from abc import ABC, abstractmethod
from typing import List
from app.core.models.PoiAgentDataclass.poi import PoiSearchResult


class BaseWebSearchAgent(ABC):
    """웹 검색 에이전트의 추상 기본 클래스"""
    
    @abstractmethod
    async def search(self, query: str, num_results: int = 10) -> List[PoiSearchResult]:
        """
        웹 검색 실행
        
        Args:
            query: 검색 쿼리
            num_results: 반환할 결과 수
            
        Returns:
            검색 결과 리스트
        """
        pass
    
    @abstractmethod
    async def search_multiple(
        self, 
        queries: List[str], 
        num_results_per_query: int = 5
    ) -> List[PoiSearchResult]:
        """
        여러 쿼리로 검색 후 결과 병합
        
        Args:
            queries: 검색 쿼리 리스트
            num_results_per_query: 쿼리당 결과 수
            
        Returns:
            병합된 검색 결과 리스트
        """
        pass
