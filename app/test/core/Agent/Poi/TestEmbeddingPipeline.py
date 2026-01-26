import pytest
from app.core.Agents.Poi.VectorDB.EmbeddingPipeline.EmbeddingPipeline import EmbeddingPipeline
from app.core.Agents.Poi.VectorDB.EmbeddingPipeline.BaseEmbeddingPipeline import BaseEmbeddingPipeline


# =============================================================================
# 단위 테스트
# =============================================================================
class TestEmbeddingPipelineUnit:
    """EmbeddingPipeline 단위 테스트"""
    
    @pytest.mark.unit
    def test_inheritance(self):
        """BaseEmbeddingPipeline 상속 확인"""
        pipeline = EmbeddingPipeline()
        assert isinstance(pipeline, BaseEmbeddingPipeline)
    
    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_embed_query_returns_list(self):
        """embed_query가 리스트를 반환하는지 확인"""
        pipeline = EmbeddingPipeline()
        result = await pipeline.embed_query("테스트 쿼리")
        
        assert isinstance(result, list)
        assert len(result) > 0
        assert all(isinstance(x, float) for x in result)
    
    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_embed_documents_returns_list_of_lists(self):
        """embed_documents가 리스트의 리스트를 반환하는지 확인"""
        pipeline = EmbeddingPipeline()
        documents = ["문서 1", "문서 2", "문서 3"]
        result = await pipeline.embed_documents(documents)
        
        assert isinstance(result, list)
        assert len(result) == 3
        for embedding in result:
            assert isinstance(embedding, list)
            assert len(embedding) > 0
    
    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_embed_query_dimension_consistency(self):
        """쿼리 임베딩 차원 일관성 확인"""
        pipeline = EmbeddingPipeline()
        result1 = await pipeline.embed_query("테스트 1")
        result2 = await pipeline.embed_query("테스트 2")
        
        assert len(result1) == len(result2)
    
    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_embed_documents_empty_list(self):
        """빈 리스트 처리 확인"""
        pipeline = EmbeddingPipeline()
        result = await pipeline.embed_documents([])
        
        assert isinstance(result, list)
        assert len(result) == 0


# =============================================================================
# 통합 테스트: 실제 sentence-transformers 모델 사용
# =============================================================================
class TestEmbeddingPipelineIntegration:
    """EmbeddingPipeline 통합 테스트 (실제 모델 사용)"""
    
    @pytest.fixture
    def pipeline(self):
        """EmbeddingPipeline 인스턴스 생성"""
        return EmbeddingPipeline()
    
    @pytest.mark.integration
    def test_get_model(self, pipeline):
        """모델 반환 확인"""
        model = pipeline.get_model()
        assert model is not None
    
    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_embed_query_semantic_similarity(self, pipeline):
        """의미적으로 유사한 쿼리가 유사한 임베딩을 생성하는지 확인"""
        import numpy as np
        
        query1 = "맛있는 음식점 추천해주세요"
        query2 = "좋은 레스토랑 알려주세요"
        query3 = "날씨가 좋습니다"
        
        emb1 = await pipeline.embed_query(query1)
        emb2 = await pipeline.embed_query(query2)
        emb3 = await pipeline.embed_query(query3)
        
        # 코사인 유사도 계산
        def cosine_similarity(a, b):
            a, b = np.array(a), np.array(b)
            return np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b))
        
        sim_12 = cosine_similarity(emb1, emb2)  # 유사한 의미
        sim_13 = cosine_similarity(emb1, emb3)  # 다른 의미
        
        # 유사한 의미의 쿼리가 더 높은 유사도를 가져야 함
        assert sim_12 > sim_13
    
    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_embed_documents_batch_consistency(self, pipeline):
        """배치 임베딩과 일반 임베딩 결과 일관성 확인"""
        documents = [f"문서 {i}" for i in range(100)]
        
        # 일반 임베딩
        normal_result = await pipeline.embed_documents(documents)
        
        # 배치 임베딩 (작은 배치 크기)
        batch_result = await pipeline.embed_documents_batch(documents, batch_size=3)
        
        assert len(normal_result) == len(batch_result)
        
        # 각 문서의 임베딩 차원이 동일한지 확인
        for i in range(len(documents)):
            assert len(normal_result[i]) == len(batch_result[i])
    
    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_embed_documents_batch_large_dataset(self, pipeline):
        """대량 문서 배치 처리 테스트"""
        documents = [f"테스트 문서 {i}. 이것은 테스트용 텍스트입니다." for i in range(250)]
        
        result = await pipeline.embed_documents_batch(documents, batch_size=50)
        
        assert len(result) == 250
        assert all(len(emb) > 0 for emb in result)
    
    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_embed_documents_batch_empty(self, pipeline):
        """빈 문서 배치 처리 테스트"""
        result = await pipeline.embed_documents_batch([], batch_size=10)
        
        assert result == []
    
    @pytest.mark.integration
    def test_embedding_dimension(self, pipeline):
        """임베딩 차원 확인 (MiniLM 모델 기준 384차원)"""
        import asyncio
        result = asyncio.get_event_loop().run_until_complete(
            pipeline.embed_query("테스트")
        )
        
        # all-MiniLM-L6-v2 모델은 384차원
        assert len(result) == 384

