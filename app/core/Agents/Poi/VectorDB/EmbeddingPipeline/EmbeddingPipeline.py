from typing import List
from sentence_transformers import SentenceTransformer

from app.core.Agents.Poi.VectorDB.EmbeddingPipeline.BaseEmbeddingPipeline import BaseEmbeddingPipeline


class EmbeddingPipeline(BaseEmbeddingPipeline):
    """
    sentence-transformers 기반 임베딩 파이프라인
    
    자연어 텍스트를 임베딩 벡터로 변환합니다.
    """
    
    def __init__(self, model_name: str = "all-MiniLM-L6-v2"):
        """
        Args:
            model_name: sentence-transformers 모델 이름
        """
        self._model = SentenceTransformer(model_name)
    
    def get_model(self):
        """임베딩 모델 반환"""
        return self._model
    
    async def embed_query(self, query: str) -> List[float]:
        """쿼리 텍스트를 임베딩 벡터로 변환"""
        return self._model.encode(query).tolist()
    

    async def embed_documents(self, documents: List[str]) -> List[List[float]]:
        """문서 텍스트 리스트를 임베딩 벡터 리스트로 변환"""
        return self._model.encode(documents).tolist()
    

    async def embed_documents_batch(
        self, 
        documents: List[str], 
        batch_size: int = 100
    ) -> List[List[float]]:
        """
        대량의 문서를 배치 단위로 나누어 임베딩 변환
        
        메모리 효율적인 처리가 필요할 때 사용합니다.
        
        Args:
            documents: 변환할 문서 텍스트 리스트
            batch_size: 한 번에 처리할 문서 수 (기본값: 100)
            
        Returns:
            임베딩 벡터 리스트
        """
        if not documents:
            return []
        
        all_embeddings = []
        for i in range(0, len(documents), batch_size):
            batch = documents[i:i + batch_size]
            batch_embeddings = self._model.encode(batch).tolist()
            all_embeddings.extend(batch_embeddings)
        
        return all_embeddings

