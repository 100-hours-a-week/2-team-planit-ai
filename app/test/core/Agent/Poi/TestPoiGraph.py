import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from app.core.Agents.Poi.PoiGraph import PoiGraph
from app.core.models.PoiAgentDataclass.poi import (
    PoiAgentState, 
    PoiSearchResult, 
    PoiInfo, 
    PoiData,
    PoiSource, 
    PoiCategory
)


def create_default_state(**overrides) -> PoiAgentState:
    """기본 PoiAgentState 생성 헬퍼"""
    default = {
        "travel_destination": "서울",
        "persona_summary": "혼자 여행하는 20대",
        "start_date": "2025-01-01",
        "end_date": "2025-01-03",
        "keywords": [],
        "web_results": [],
        "embedding_results": [],
        "reranked_web_results": [],
        "reranked_embedding_results": [],
        "merged_results": [],
        "poi_data_map": {},
        "final_poi_data": [],
        "final_pois": [],
        "final_poi_count": 20
    }
    default.update(overrides)
    return default


# =============================================================================
# 단위 테스트: 모든 의존성 Mock 사용
# =============================================================================
class TestPoiGraphUnit:
    """PoiGraph 단위 테스트 (모든 의존성 Mock)"""
    
    @pytest.fixture
    def mock_llm_client(self):
        """Mock LLM Client"""
        client = MagicMock()
        client.call_llm = AsyncMock(return_value="<keywords><keyword>서울 맛집</keyword></keywords>")
        return client
    
    @pytest.fixture
    def poi_graph(self, mock_llm_client):
        """PoiGraph 인스턴스 생성 (모든 의존성 Mock)"""
        with patch('app.core.Agents.Poi.PoiGraph.WebSearchAgent') as MockWeb, \
             patch('app.core.Agents.Poi.PoiGraph.VectorSearchAgent') as MockVector, \
             patch('app.core.Agents.Poi.PoiGraph.GoogleMapsPoiMapper') as MockMapper:
            
            MockWeb.return_value.search_multiple = AsyncMock(return_value=[])
            MockVector.return_value.search_by_text = AsyncMock(return_value=[])
            MockVector.return_value.search_by_text_with_data = AsyncMock(return_value=[])
            MockVector.return_value.add_pois_batch = AsyncMock(return_value=0)
            MockMapper.return_value.map_poi = AsyncMock(return_value=None)
            
            graph = PoiGraph(
                llm_client=mock_llm_client,
                rerank_min_score=0.5,
                keyword_k=5,
                embedding_k=10,
                web_search_k=5,
                final_poi_count=20
            )
            return graph
    
    @pytest.mark.unit
    def test_initialization(self, poi_graph):
        """초기화 테스트"""
        assert poi_graph.keyword_extractor is not None
        assert poi_graph.result_merger is not None
        assert poi_graph.info_summarizer is not None
        assert poi_graph.reranker is not None
        assert poi_graph.graph is not None
        assert poi_graph.keyword_k == 5
        assert poi_graph.web_search_k == 5
        assert poi_graph.embedding_k == 10
        assert poi_graph.final_poi_count == 20
    
    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_extract_keywords_node(self, poi_graph, mock_llm_client):
        """_extract_keywords 노드 테스트"""
        mock_llm_client.call_llm.return_value = """
        <keywords>
        <keyword>서울 혼밥 맛집</keyword>
        <keyword>서울 로컬 맛집</keyword>
        </keywords>
        """
        
        state = create_default_state()
        
        result = await poi_graph._extract_keywords(state)
        
        assert "keywords" in result
        assert len(result["keywords"]) > 0
    
    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_web_search_node(self, poi_graph):
        """_web_search 노드 테스트"""
        state = create_default_state(
            keywords=["서울 맛집", "서울 명소"]
        )
        
        # WebSearchAgent.search_multiple Mock 설정
        mock_results = [
            PoiSearchResult(title="맛집1", snippet="맛있어요", source=PoiSource.WEB_SEARCH),
            PoiSearchResult(title="명소1", snippet="좋아요", source=PoiSource.WEB_SEARCH)
        ]
        poi_graph.web_search.search_multiple = AsyncMock(return_value=mock_results)
        
        result = await poi_graph._web_search(state)
        
        assert "web_results" in result
        assert len(result["web_results"]) == 2
        poi_graph.web_search.search_multiple.assert_called_once()

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_vector_db_first_search_node(self, poi_graph):
        """_vector_db_first_search 노드 테스트 - 관련도 >= 0.9 필터링"""
        state = create_default_state(
            keywords=["서울 맛집"]
        )

        # VectorSearchAgent.search_by_text_with_data Mock 설정
        mock_poi_data_high = PoiData(
            id="poi-1",
            name="맛집1",
            category=PoiCategory.RESTAURANT,
            description="맛있는 곳",
            source=PoiSource.EMBEDDING_DB,
            raw_text="맛집1 설명"
        )
        mock_search_result_high = PoiSearchResult(
            poi_id="poi-1",
            title="맛집1",
            snippet="맛있어요",
            source=PoiSource.EMBEDDING_DB,
            relevance_score=0.95
        )
        mock_poi_data_low = PoiData(
            id="poi-2",
            name="맛집2",
            category=PoiCategory.RESTAURANT,
            description="보통인 곳",
            source=PoiSource.EMBEDDING_DB,
            raw_text="맛집2 설명"
        )
        mock_search_result_low = PoiSearchResult(
            poi_id="poi-2",
            title="맛집2",
            snippet="보통이에요",
            source=PoiSource.EMBEDDING_DB,
            relevance_score=0.7
        )
        poi_graph.vector_search.search_by_text_with_data = AsyncMock(
            return_value=[
                (mock_search_result_high, mock_poi_data_high),
                (mock_search_result_low, mock_poi_data_low)
            ]
        )

        result = await poi_graph._vector_db_first_search(state)

        assert "embedding_results" in result
        assert "poi_data_map" in result
        # 관련도 0.9 미만인 poi-2는 필터링됨
        assert len(result["embedding_results"]) == 1
        assert result["embedding_results"][0].poi_id == "poi-1"
        poi_graph.vector_search.search_by_text_with_data.assert_called()

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_process_and_rerank_web_node_empty(self, poi_graph):
        """_process_and_rerank_web 노드 테스트 - 빈 입력"""
        state = create_default_state(
            web_results=[]
        )
        
        result = await poi_graph._process_and_rerank_web(state)
        
        assert result["reranked_web_results"] == []
        assert result["poi_data_map"] == {}

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_rerank_embedding_node(self, poi_graph):
        """_rerank_embedding 노드 테스트"""
        state = create_default_state(
            embedding_results=[
                PoiSearchResult(
                    poi_id="poi-1",
                    title="맛집1",
                    snippet="맛있어요",
                    source=PoiSource.EMBEDDING_DB,
                    relevance_score=0.8
                )
            ]
        )
        
        # Reranker.rerank Mock 설정
        mock_reranked = [
            PoiSearchResult(
                poi_id="poi-1",
                title="맛집1",
                snippet="맛있어요",
                source=PoiSource.EMBEDDING_DB,
                relevance_score=0.9
            )
        ]
        poi_graph.reranker.rerank = AsyncMock(return_value=mock_reranked)
        
        result = await poi_graph._rerank_embedding(state)
        
        assert "reranked_embedding_results" in result
        assert len(result["reranked_embedding_results"]) == 1
        assert result["reranked_embedding_results"][0].relevance_score == 0.9

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_merge_results_node(self, poi_graph):
        """_merge_results 노드 테스트"""
        mock_poi_data = PoiData(
            id="poi-1",
            name="테스트 장소",
            category=PoiCategory.RESTAURANT,
            description="맛있는 곳",
            source=PoiSource.WEB_SEARCH,
            raw_text="테스트 장소 설명"
        )
        
        state = create_default_state(
            reranked_web_results=[
                PoiSearchResult(
                    poi_id="poi-1",
                    title="웹 결과",
                    snippet="웹 검색",
                    source=PoiSource.WEB_SEARCH,
                    relevance_score=0.9
                )
            ],
            reranked_embedding_results=[
                PoiSearchResult(
                    poi_id="poi-2",
                    title="임베딩 결과",
                    snippet="임베딩 검색",
                    source=PoiSource.EMBEDDING_DB,
                    relevance_score=0.8
                )
            ],
            poi_data_map={"poi-1": mock_poi_data}
        )
        
        result = await poi_graph._merge_results(state)
        
        assert "merged_results" in result
        assert "final_poi_data" in result
        assert len(result["merged_results"]) == 2
        # poi_data_map에 있는 것만 final_poi_data에 포함
        assert len(result["final_poi_data"]) == 1


# =============================================================================
# 통합 테스트: 모든 의존성 실제 사용
# =============================================================================
class TestPoiGraphIntegration:
    """PoiGraph 전체 통합 테스트 (모든 의존성 실제 사용)"""
    
    @pytest.fixture
    def real_graph(self):
        """실제 LLM, WebSearch, VectorDB를 사용하는 PoiGraph"""
        try:
            from app.core.LLMClient.OpenAiApiClient import OpenAiApiClient

            llm = OpenAiApiClient()
            return PoiGraph(
                llm_client=llm,
                rerank_min_score=0.5,
                keyword_k=3,
                embedding_k=5,
                web_search_k=3,
                final_poi_count=10
            )
        except Exception as e:
            pytest.skip(f"PoiGraph 초기화 실패: {e}")
    
    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_extract_keywords_with_real_llm(self, real_graph):
        """실제 LLM으로 키워드 추출 테스트"""
        state = create_default_state(
            persona_summary="혼자 여행하는 20대, 맛집 탐방을 좋아함"
        )
        
        result = await real_graph._extract_keywords(state)
        
        print(f"추출된 키워드: {result.get('keywords', [])}")
        
        assert "keywords" in result
        assert len(result["keywords"]) >= 0
    
    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_run_method(self, real_graph):
        """run() 메서드 테스트"""
        if not real_graph.web_search.extractor:
            pytest.skip("Extractor 없음")
        
        result, state = await real_graph.run(
            persona_summary="혼자 여행하는 20대, 카페 좋아함",
            travel_destination="서울",
            start_date="2025-01-01",
            end_date="2025-01-03"
        )
        
        print(f"run() 결과: {len(result)}개의 POI")
        
        assert isinstance(result, list)
        if result:
            assert isinstance(result[0], PoiData)
