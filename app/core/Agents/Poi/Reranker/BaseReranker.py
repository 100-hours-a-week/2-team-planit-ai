from abc import ABC, abstractmethod
from typing import List
from app.core.models.PoiAgentDataclass.poi import PoiSearchResult


class BaseReranker(ABC):
    """검색 결과 리랭킹 에이전트의 추상 기본 클래스"""
    
    @abstractmethod
    async def rerank(
        self, 
        results: List[PoiSearchResult], 
        persona_summary: str
    ) -> List[PoiSearchResult]:
        """
        검색 결과를 페르소나 기반으로 리랭킹
        
        Args:
            results: 검색 결과 리스트
            persona_summary: 여행자 페르소나 요약
            
        Returns:
            리랭킹된 검색 결과 리스트
        """
        pass
    
    @abstractmethod
    async def rerank_batch(
        self, 
        web_results: List[PoiSearchResult],
        embedding_results: List[PoiSearchResult],
        persona_summary: str
    ) -> tuple[List[PoiSearchResult], List[PoiSearchResult]]:
        """
        웹 검색 결과와 임베딩 검색 결과를 동시에 리랭킹
        
        Args:
            web_results: 웹 검색 결과 리스트
            embedding_results: 임베딩 검색 결과 리스트
            persona_summary: 여행자 페르소나 요약
            
        Returns:
            (리랭킹된 웹 결과, 리랭킹된 임베딩 결과) 튜플
        """
        pass
