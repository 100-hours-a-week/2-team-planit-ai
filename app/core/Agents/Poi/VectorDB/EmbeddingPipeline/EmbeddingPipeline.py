from typing import Dict, List, Optional
from sentence_transformers import SentenceTransformer

from app.core.Agents.Poi.VectorDB.EmbeddingPipeline.BaseEmbeddingPipeline import (
    BaseEmbeddingPipeline,
    EmbeddingTaskType,
)
from app.core.models.PoiAgentDataclass.poi import PoiData


class EmbeddingPipeline(BaseEmbeddingPipeline):
    """
    sentence-transformers 기반 임베딩 파이프라인

    자연어 텍스트를 임베딩 벡터로 변환합니다.
    task_prefixes를 통해 모델별 query/document prefix를 설정할 수 있습니다.
    """

    def __init__(
        self,
        model_name: str = "jhgan/ko-sroberta-multitask",
        task_prefixes: Optional[Dict[str, str]] = None,
    ):
        """
        Args:
            model_name: sentence-transformers 모델 이름
            task_prefixes: 태스크 타입별 prefix 매핑
                           예: {"query": "query: ", "document": "passage: "}
        """
        self._model = SentenceTransformer(model_name)
        self._task_prefixes: Dict[str, str] = task_prefixes or {}

    def get_model(self):
        """임베딩 모델 반환"""
        return self._model

    async def embed(
        self, texts: List[str], task_type: EmbeddingTaskType = EmbeddingTaskType.QUERY
    ) -> List[List[float]]:
        """
        태스크 타입에 따라 적절한 임베딩을 생성

        Args:
            texts: 임베딩할 텍스트 리스트
            task_type: QUERY 또는 DOCUMENT

        Returns:
            임베딩 벡터 리스트
        """
        if self._model is None:
            self.load_model()
        return self._model.encode(texts).tolist()

    async def embed_query(self, query: str) -> List[float]:
        """
        쿼리 텍스트를 임베딩 벡터로 변환

        Args:
            query: 쿼리 텍스트

        Returns:
            임베딩 벡터
        """
        results = await self.embed([query], EmbeddingTaskType.QUERY)
        return results[0]

    async def embed_documents(self, documents: List[PoiData]) -> List[List[float]]:
        """
        PoiData 리스트를 임베딩 벡터 리스트로 변환

        Args:
            documents: PoiData 객체 리스트

        Returns:
            임베딩 벡터 리스트
        """
        texts = [self.structured_summary_formatter(poiData) for poiData in documents]
        return await self.embed(texts, EmbeddingTaskType.DOCUMENT)

    async def embed_documents_batch(
        self,
        documents: List[PoiData],
        batch_size: int = 32,
    ) -> List[List[float]]:
        """
        대용량 PoiData를 배치 처리하여 임베딩

        Args:
            documents: PoiData 객체 리스트
            batch_size: 배치 크기

        Returns:
            임베딩 벡터 리스트
        """
        if not documents:
            return []

        all_embeddings = []
        for i in range(0, len(documents), batch_size):
            batch = documents[i:i + batch_size]
            texts = [self.structured_summary_formatter(poiData) for poiData in batch]
            batch_embeddings = await self.embed(texts, EmbeddingTaskType.DOCUMENT)
            all_embeddings.extend(batch_embeddings)

        return all_embeddings

    def structured_summary_formatter(self, poiData: PoiData) -> str:
        """
        Structured format using PoiData fields.
        Output: "restaurant | 평점 4.5 | MODERATE | 에디토리얼: ... | 리뷰: ..."
        """
        parts = []

        # 카테고리/타입
        parts.append(poiData.primary_type or poiData.category.value)

        # 평점
        if poiData.google_rating:
            rating_str = f"평점 {poiData.google_rating}"
            if poiData.user_rating_count:
                rating_str += f"({poiData.user_rating_count}명)"
            parts.append(rating_str)

        # 가격
        if poiData.price_range:
            parts.append(poiData.price_range)
        elif poiData.price_level:
            parts.append(poiData.price_level)

        # Editorial Summary
        if poiData.editorial_summary:
            parts.append(f"소개: {poiData.editorial_summary}")

        # Generative Summary
        if poiData.generative_summary:
            parts.append(f"AI요약: {poiData.generative_summary}")

        # Review Summary
        if poiData.review_summary:
            parts.append(f"리뷰: {poiData.review_summary}")

        return " | ".join(parts)
