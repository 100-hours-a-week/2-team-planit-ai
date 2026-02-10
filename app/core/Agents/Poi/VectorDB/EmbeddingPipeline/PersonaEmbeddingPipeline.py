from typing import Dict, List, Optional
from sentence_transformers import SentenceTransformer

from app.core.Agents.Poi.VectorDB.EmbeddingPipeline.BaseEmbeddingPipeline import (
    BaseEmbeddingPipeline,
    EmbeddingTaskType,
)
from app.core.models.PoiAgentDataclass.poi import PoiData


class PersonaEmbeddingPipeline(BaseEmbeddingPipeline):
    """
    페르소나 직접 임베딩 파이프라인 (Airbnb EBR 스타일)

    - 쿼리: 페르소나 전체 텍스트를 직접 임베딩 (키워드 추출 불필요)
    - 문서: POI 정보를 풍부하게 결합하여 임베딩 (카테고리, 가격, 평점 포함)
    """

    def __init__(
        self,
        model_name: str = "all-MiniLM-L6-v2",
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
        if not texts:
            return []
        prefix = self._task_prefixes.get(task_type.value, "")
        if prefix:
            texts = [f"{prefix}{t}" for t in texts]
        return self._model.encode(texts).tolist()

    # ─────────────────────────────────────────────────────────────
    # 쿼리 임베딩 (페르소나 직접 사용)
    # ─────────────────────────────────────────────────────────────

    def build_persona_query(self, persona: str, destination: str) -> str:
        """페르소나를 VectorDB 쿼리용 텍스트로 변환"""
        return f"여행지 {destination}에서 {persona}"

    async def embed_persona(self, persona: str, destination: str) -> List[float]:
        """
        페르소나 + 여행지를 결합하여 임베딩 생성

        Args:
            persona: 사용자 페르소나 요약
            destination: 여행 목적지

        Returns:
            페르소나 임베딩 벡터
        """
        query_text = self.build_persona_query(persona, destination)
        return await self.embed_query(query_text)

    # ─────────────────────────────────────────────────────────────
    # POI 임베딩 (풍부한 정보 포함)
    # ─────────────────────────────────────────────────────────────

    def build_poi_embedding_text(self, poi: PoiData) -> str:
        """
        POI 임베딩용 텍스트 생성 (페르소나와 매칭 최적화)

        카테고리, 가격, 평점 등을 포함하여 검색 정확도 향상
        """
        parts = [poi.name, poi.category.value]

        if poi.description:
            parts.append(poi.description)

        # 가격 정보
        if poi.price_level:
            price_map = {
                "PRICE_LEVEL_INEXPENSIVE": "저렴한",
                "PRICE_LEVEL_MODERATE": "적당한 가격의",
                "PRICE_LEVEL_EXPENSIVE": "고급",
                "PRICE_LEVEL_VERY_EXPENSIVE": "최고급",
            }
            parts.append(price_map.get(poi.price_level, ""))

        # 평점 정보
        if poi.google_rating and poi.google_rating >= 4.5:
            parts.append("인기 있는")

        # 위치 정보
        if poi.city:
            parts.append(f"{poi.city} 위치")

        return " ".join(filter(None, parts))

    async def embed_documents(self, documents: List[PoiData]) -> List[List[float]]:
        """PoiData 리스트를 풍부한 텍스트로 변환하여 임베딩"""
        texts = [self.build_poi_embedding_text(poi) for poi in documents]
        return await self.embed(texts, EmbeddingTaskType.DOCUMENT)

    async def embed_documents_batch(
        self, documents: List[PoiData], batch_size: int = 100
    ) -> List[List[float]]:
        """대량의 PoiData를 배치 단위로 나누어 임베딩 변환"""
        if not documents:
            return []

        all_embeddings = []
        for i in range(0, len(documents), batch_size):
            batch = documents[i:i + batch_size]
            texts = [self.build_poi_embedding_text(poi) for poi in batch]
            batch_embeddings = await self.embed(texts, EmbeddingTaskType.DOCUMENT)
            all_embeddings.extend(batch_embeddings)

        return all_embeddings
