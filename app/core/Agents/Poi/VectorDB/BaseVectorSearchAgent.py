from abc import ABC, abstractmethod
from typing import List, Optional
from app.core.models.PoiAgentDataclass.poi import PoiSearchResult, PoiData
from app.core.Agents.Poi.VectorDB.EmbeddingPipeline.BaseEmbeddingPipeline import BaseEmbeddingPipeline

class BaseVectorSearchAgent(ABC):
    """벡터 검색 에이전트의 추상 기본 클래스 (Two-tower POI Tower)"""
    
    def __init__(self, embedding_pipeline: BaseEmbeddingPipeline):
        self.embedding_pipeline = embedding_pipeline

    @abstractmethod
    async def search(
        self, 
        query_embedding: List[float], 
        k: int = 10
    ) -> List[PoiSearchResult]:
        """
        벡터 유사도 검색 (만약 된다면 별도의 추천에 특화된 임베딩 모델을 사용 예정)
        
        Args:
            query_embedding: 쿼리 임베딩 벡터
            k: 반환할 결과 수
            
        Returns:
            유사도 높은 POI 검색 결과 리스트
        """
        pass
    
    @abstractmethod
    async def search_by_text(
        self, 
        query: str, 
        k: int = 10,
        city_filter: Optional[str] = None
    ) -> List[PoiSearchResult]:
        """
        텍스트 쿼리로 검색 (내부에서 임베딩 변환)
        
        Args:
            query: 검색 텍스트
            k: 반환할 결과 수
            city_filter: 도시 필터 (해당 도시의 POI만 검색)
            
        Returns:
            유사도 높은 POI 검색 결과 리스트
        """
        pass
    
    @abstractmethod
    async def add_poi(self, poi: PoiData) -> bool:
        """
        POI 데이터를 벡터 DB에 추가
        
        Args:
            poi: 추가할 POI 데이터
            
        Returns:
            성공 여부
        """
        pass
    
    @abstractmethod
    async def add_pois_batch(self, pois: List[PoiData]) -> int:
        """
        POI 데이터를 배치로 추가
        
        Args:
            pois: 추가할 POI 데이터 리스트
            
        Returns:
            성공적으로 추가된 개수
        """
        pass
    
    @abstractmethod
    async def get_collection_size(self) -> int:
        """
        벡터 DB의 현재 데이터 개수 반환
        """
        pass
