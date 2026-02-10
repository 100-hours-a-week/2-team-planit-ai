import pytest
from app.core.Agents.Poi.VectorDB.EmbeddingPipeline.EmbeddingPipeline import EmbeddingPipeline
from app.core.Agents.Poi.VectorDB.EmbeddingPipeline.BaseEmbeddingPipeline import (
    BaseEmbeddingPipeline,
    EmbeddingTaskType,
)
from app.core.models.PoiAgentDataclass.poi import PoiData, PoiCategory, PoiSource


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
        documents = [
            PoiData(id=f"doc-{i}", name=f"문서 {i}", category=PoiCategory.RESTAURANT,
                    description=f"설명 {i}", source=PoiSource.WEB_SEARCH, raw_text=f"문서 {i}")
            for i in range(1, 4)
        ]
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
        documents = [
            PoiData(id=f"doc-{i}", name=f"문서 {i}", category=PoiCategory.RESTAURANT,
                    description=f"설명 {i}", source=PoiSource.WEB_SEARCH, raw_text=f"문서 {i}")
            for i in range(100)
        ]

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
        documents = [
            PoiData(id=f"doc-{i}", name=f"테스트 문서 {i}", category=PoiCategory.RESTAURANT,
                    description=f"설명 {i}", source=PoiSource.WEB_SEARCH,
                    raw_text=f"테스트 문서 {i}. 이것은 테스트용 텍스트입니다.")
            for i in range(250)
        ]

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


# =============================================================================
# embed() 메서드 및 EmbeddingTaskType 테스트
# =============================================================================
class TestEmbedMethodUnit:
    """embed() 통합 메서드 및 task_type 분기 테스트"""

    @pytest.mark.unit
    def test_embedding_task_type_values(self):
        """EmbeddingTaskType enum 값 확인"""
        assert EmbeddingTaskType.QUERY == "query"
        assert EmbeddingTaskType.DOCUMENT == "document"

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_embed_query_type(self):
        """embed()에 QUERY 타입으로 호출"""
        pipeline = EmbeddingPipeline()
        result = await pipeline.embed(["테스트 쿼리"], EmbeddingTaskType.QUERY)

        assert isinstance(result, list)
        assert len(result) == 1
        assert len(result[0]) > 0

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_embed_document_type(self):
        """embed()에 DOCUMENT 타입으로 호출"""
        pipeline = EmbeddingPipeline()
        result = await pipeline.embed(["문서 텍스트"], EmbeddingTaskType.DOCUMENT)

        assert isinstance(result, list)
        assert len(result) == 1
        assert len(result[0]) > 0

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_embed_empty_list(self):
        """빈 텍스트 리스트 처리"""
        pipeline = EmbeddingPipeline()
        result = await pipeline.embed([], EmbeddingTaskType.QUERY)

        assert result == []

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_embed_default_task_type(self):
        """task_type 기본값이 QUERY인지 확인"""
        pipeline = EmbeddingPipeline()
        result_default = await pipeline.embed(["테스트"])
        result_query = await pipeline.embed(["테스트"], EmbeddingTaskType.QUERY)

        assert result_default == result_query

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_task_prefixes_applied(self):
        """task_prefixes가 텍스트에 적용되는지 확인"""
        pipeline_no_prefix = EmbeddingPipeline()
        pipeline_with_prefix = EmbeddingPipeline(
            task_prefixes={"query": "query: ", "document": "passage: "}
        )

        # prefix가 있으면 다른 임베딩이 생성되어야 함
        result_no = await pipeline_no_prefix.embed(["테스트"], EmbeddingTaskType.QUERY)
        result_with = await pipeline_with_prefix.embed(["테스트"], EmbeddingTaskType.QUERY)

        # 같은 텍스트지만 prefix 유무로 임베딩이 달라야 함
        assert result_no != result_with

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_no_prefix_when_empty_dict(self):
        """task_prefixes가 빈 dict일 때 prefix 없이 동작"""
        pipeline_default = EmbeddingPipeline()
        pipeline_empty = EmbeddingPipeline(task_prefixes={})

        result_default = await pipeline_default.embed(["테스트"], EmbeddingTaskType.QUERY)
        result_empty = await pipeline_empty.embed(["테스트"], EmbeddingTaskType.QUERY)

        assert result_default == result_empty

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_embed_multiple_texts(self):
        """여러 텍스트 동시 임베딩"""
        pipeline = EmbeddingPipeline()
        texts = ["텍스트 1", "텍스트 2", "텍스트 3"]
        result = await pipeline.embed(texts, EmbeddingTaskType.DOCUMENT)

        assert len(result) == 3
        for emb in result:
            assert isinstance(emb, list)
            assert len(emb) > 0

