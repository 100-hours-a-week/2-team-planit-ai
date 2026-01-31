from abc import ABC, abstractmethod
from typing import List


class BaseEmbeddingPipeline(ABC):
    """자연어 → 임베딩 벡터 변환 담당"""
    
    @abstractmethod
    async def embed_query(self, query: str) -> List[float]:
        """
        쿼리 텍스트를 임베딩 벡터로 변환
        
        Args:
            query: 검색 쿼리 텍스트
            
        Returns:
            임베딩 벡터
        """
        pass
    
    @abstractmethod
    async def embed_documents(self, documents: List[str]) -> List[List[float]]:
        """
        문서 텍스트 리스트를 임베딩 벡터 리스트로 변환
        
        Args:
            documents: 문서 텍스트 리스트
            
        Returns:
            임베딩 벡터 리스트
        """
        pass
    
    @abstractmethod
    async def embed_documents_batch(
        self, 
        documents: List[str], 
        batch_size: int = 100
    ) -> List[List[float]]:
        """
        대량의 문서를 배치 단위로 나누어 임베딩 변환
        
        Args:
            documents: 변환할 문서 텍스트 리스트
            batch_size: 한 번에 처리할 문서 수
            
        Returns:
            임베딩 벡터 리스트
        """
        pass
