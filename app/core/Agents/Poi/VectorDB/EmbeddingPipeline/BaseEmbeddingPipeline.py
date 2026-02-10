from abc import ABC, abstractmethod
from enum import Enum
from typing import List

from app.core.models.PoiAgentDataclass.poi import PoiData


class EmbeddingTaskType(str, Enum):
    """임베딩 태스크 타입 (query vs document 구분)"""
    QUERY = "query"
    DOCUMENT = "document"


class BaseEmbeddingPipeline(ABC):
    """자연어 → 임베딩 벡터 변환 담당"""

    @abstractmethod
    async def embed(
        self, texts: List[str], task_type: EmbeddingTaskType = EmbeddingTaskType.QUERY
    ) -> List[List[float]]:
        """
        태스크 타입에 따라 적절한 임베딩을 생성하는 통합 메서드

        Args:
            texts: 임베딩할 텍스트 리스트
            task_type: QUERY 또는 DOCUMENT

        Returns:
            임베딩 벡터 리스트
        """
        pass

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
    async def embed_documents(self, documents: List[PoiData]) -> List[List[float]]:
        """
        PoiData 리스트를 임베딩 벡터 리스트로 변환

        Args:
            documents: PoiData 리스트 (raw_text 필드를 사용)

        Returns:
            임베딩 벡터 리스트
        """
        pass

    async def embed_documents_batch(
        self,
        documents: List[PoiData],
        batch_size: int = 100
    ) -> List[List[float]]:
        """
        대량의 PoiData를 배치 단위로 나누어 임베딩 변환

        Args:
            documents: 변환할 PoiData 리스트 (raw_text 필드를 사용)
            batch_size: 한 번에 처리할 문서 수

        Returns:
            임베딩 벡터 리스트
        """
        pass