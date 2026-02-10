import pytest
from unittest.mock import MagicMock, AsyncMock
from app.core.Agents.Poi.VectorDB.VectorSearchAgent import VectorSearchAgent
from app.core.Agents.Poi.VectorDB.EmbeddingPipeline.EmbeddingPipeline import EmbeddingPipeline
from app.core.models.PoiAgentDataclass.poi import PoiData, PoiSource, PoiCategory, PoiSearchResult


# =============================================================================
# Mock EmbeddingPipeline
# =============================================================================
class MockEmbeddingPipeline():
    """테스트용 Mock EmbeddingPipeline"""
    
    async def embed_query(self, query: str):
        return [0.1] * 384  # 384차원 임베딩 벡터
    
    async def embed_documents(self, documents):
        return [[0.1] * 384 for _ in documents]


# =============================================================================
# 단위 테스트: 모든 의존성 Mock 사용
# =============================================================================
class TestVectorSearchAgentUnit:
    """VectorSearchAgent 단위 테스트 (Mock ChromaDB 사용)"""
    
    @pytest.fixture
    def mock_embedding_pipeline(self):
        """Mock EmbeddingPipeline"""
        return MockEmbeddingPipeline()
    
    @pytest.fixture
    def mock_collection(self):
        """Mock ChromaDB Collection"""
        collection = MagicMock()
        collection.count.return_value = 5
        # ChromaDB query 반환 형식 시뮬레이션
        collection.query.return_value = {
            "ids": [["poi-123", "poi-456"]],
            "documents": [["서울의 유명한 맛집입니다.", "조용한 분위기의 카페입니다."]],
            "metadatas": [[
                {
                    "name": "명동교자", 
                    "category": "restaurant", 
                    "source_url": "https://myeongdong.com",
                    "city": "Seoul"
                },
                {
                    "name": "블루보틀", 
                    "category": "cafe", 
                    "source_url": "https://bluebottle.com",
                    "city": "Seoul"
                }
            ]],
            "distances": [[0.15, 0.4]] # Cosine distance
        }
        return collection
    
    @pytest.mark.unit
    def test_initialization(self, mock_embedding_pipeline):
        """초기화 테스트"""
        agent = VectorSearchAgent(
            embedding_pipeline=mock_embedding_pipeline,
            collection_name="test_collection"
        )
        
        assert agent.collection_name == "test_collection"
        assert agent._initialized == False
        assert agent._client is None
        assert agent.embedding_pipeline == mock_embedding_pipeline
    
    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_search_by_text_logic_with_mock(self, mock_embedding_pipeline, mock_collection):
        """Mock을 사용하여 search_by_text의 내부 정합성 및 점수 계산 로직 테스트"""
        agent = VectorSearchAgent(embedding_pipeline=mock_embedding_pipeline)
        agent._initialized = True
        agent._collection = mock_collection
        
        # 쿼리 실행
        results = await agent.search_by_text("맛집 추천", k=2, city_filter="서울")
        
        # 검증: 결과 개수
        assert len(results) == 2
        
        # 첫 번째 결과 검증 (유사도 점수 계산 로직 확인)
        # distance 0.15 -> similarity = 1 - 0.15 = 0.85
        assert results[0].poi_id == "poi-123"
        assert results[0].title == "명동교자"
        assert results[0].snippet == "서울의 유명한 맛집입니다."
        assert results[0].relevance_score == pytest.approx(0.85)
        assert results[0].source == PoiSource.EMBEDDING_DB
        
        # 두 번째 결과 검증
        # distance 0.4 -> similarity = 1 - 0.4 = 0.6
        assert results[1].poi_id == "poi-456"
        assert results[1].title == "블루보틀"
        assert results[1].snippet == "조용한 분위기의 카페입니다."
        assert results[1].relevance_score == pytest.approx(0.6)
    
    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_search_returns_embedding_db_source(self, mock_embedding_pipeline, mock_collection):
        """검색 결과 source가 EMBEDDING_DB인지 확인"""
        agent = VectorSearchAgent(embedding_pipeline=mock_embedding_pipeline)
        agent._initialized = True
        agent._collection = mock_collection
        
        results = await agent.search_by_text("맛집", k=5, city_filter="서울")
        
        for result in results:
            assert result.source == PoiSource.EMBEDDING_DB
    
    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_add_poi_calls_collection(self, mock_embedding_pipeline, mock_collection):
        """add_poi 호출 시 실제 collection.add가 호출되는지 확인"""
        agent = VectorSearchAgent(embedding_pipeline=mock_embedding_pipeline)
        agent._initialized = True
        agent._collection = mock_collection
        
        poi = PoiData(
            id="test-1",
            name="테스트 장소",
            category=PoiCategory.RESTAURANT,
            description="설명",
            source=PoiSource.WEB_SEARCH,
            raw_text="전체 텍스트"
        )
        
        success = await agent.add_poi(poi)
        
        assert success is True
        assert mock_collection.add.called
        # 호출 인자 검증
        args, kwargs = mock_collection.add.call_args
        assert kwargs['ids'] == ["test-1"]
        assert kwargs['documents'] == ["전체 텍스트"]
        assert kwargs['metadatas'] == [{
            "name": "테스트 장소",
            "category": "restaurant",
            "description": "설명",
            "city": "",
            "address": "",
            "source": "web_search",
            "source_url": "",
            # Google Maps 필드
            "google_place_id": "",
            "latitude": "",
            "longitude": "",
            "google_maps_uri": "",
            "types": "[]",
            "primary_type": "",
            # 상세 정보
            "google_rating": "",
            "user_rating_count": "",
            "price_level": "",
            "price_range": "",
            "website_uri": "",
            "phone_number": "",
            # 영업시간
            "opening_hours": "",
        }]

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_add_pois_batch_empty(self, mock_embedding_pipeline):
        """빈 리스트 추가 시 조기 리턴 확인"""
        agent = VectorSearchAgent(embedding_pipeline=mock_embedding_pipeline)
        count = await agent.add_pois_batch([])
        assert count == 0

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_add_pois_batch_dedup_within_batch(self, mock_embedding_pipeline, mock_collection):
        """배치 내 중복 ID가 제거되고 첫 번째 항목만 유지되는지 확인"""
        agent = VectorSearchAgent(embedding_pipeline=mock_embedding_pipeline)
        agent._initialized = True
        agent._collection = mock_collection

        # collection.get()이 빈 결과를 반환 (기존 데이터 없음)
        mock_collection.get.return_value = {"ids": []}

        poi_a = PoiData(
            id="dup-1", name="장소A", category=PoiCategory.RESTAURANT,
            description="A", source=PoiSource.WEB_SEARCH, raw_text="텍스트A"
        )
        poi_b = PoiData(
            id="dup-1", name="장소B", category=PoiCategory.CAFE,
            description="B", source=PoiSource.WEB_SEARCH, raw_text="텍스트B"
        )
        poi_c = PoiData(
            id="unique-1", name="장소C", category=PoiCategory.RESTAURANT,
            description="C", source=PoiSource.WEB_SEARCH, raw_text="텍스트C"
        )

        count = await agent.add_pois_batch([poi_a, poi_b, poi_c])

        assert count == 2  # dup-1 하나 + unique-1 하나
        _, kwargs = mock_collection.add.call_args
        assert kwargs["ids"] == ["dup-1", "unique-1"]
        # 첫 번째 항목(poi_a)이 유지되었는지 확인
        assert kwargs["documents"] == ["텍스트A", "텍스트C"]

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_add_pois_batch_dedup_existing_ids(self, mock_embedding_pipeline, mock_collection):
        """컬렉션에 이미 존재하는 ID가 필터링되는지 확인"""
        agent = VectorSearchAgent(embedding_pipeline=mock_embedding_pipeline)
        agent._initialized = True
        agent._collection = mock_collection

        # "existing-1"이 이미 컬렉션에 존재한다고 시뮬레이션
        mock_collection.get.return_value = {"ids": ["existing-1"]}

        poi_existing = PoiData(
            id="existing-1", name="기존 장소", category=PoiCategory.RESTAURANT,
            description="기존", source=PoiSource.WEB_SEARCH, raw_text="기존 텍스트"
        )
        poi_new = PoiData(
            id="new-1", name="새 장소", category=PoiCategory.CAFE,
            description="새로운", source=PoiSource.WEB_SEARCH, raw_text="새 텍스트"
        )

        count = await agent.add_pois_batch([poi_existing, poi_new])

        assert count == 1  # new-1만 추가
        _, kwargs = mock_collection.add.call_args
        assert kwargs["ids"] == ["new-1"]
        assert kwargs["documents"] == ["새 텍스트"]

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_add_pois_batch_all_duplicates_returns_zero(self, mock_embedding_pipeline, mock_collection):
        """모든 항목이 중복이면 0을 반환하고 collection.add가 호출되지 않는지 확인"""
        agent = VectorSearchAgent(embedding_pipeline=mock_embedding_pipeline)
        agent._initialized = True
        agent._collection = mock_collection

        mock_collection.get.return_value = {"ids": ["dup-1", "dup-2"]}

        pois = [
            PoiData(id="dup-1", name="장소1", category=PoiCategory.RESTAURANT,
                    description="1", source=PoiSource.WEB_SEARCH, raw_text="텍스트1"),
            PoiData(id="dup-2", name="장소2", category=PoiCategory.CAFE,
                    description="2", source=PoiSource.WEB_SEARCH, raw_text="텍스트2"),
        ]

        count = await agent.add_pois_batch(pois)

        assert count == 0
        mock_collection.add.assert_not_called()


# =============================================================================
# 통합 테스트: 모든 의존성 실제 사용 (Memory Mode)
# =============================================================================
class TestVectorSearchAgentIntegration:
    """VectorSearchAgent 통합 테스트"""
    
    @pytest.fixture
    async def agent(self):
        """VectorSearchAgent 인스턴스 (매 테스트마다 고유한 컬렉션 생성하여 격리)"""
        import uuid
        from app.core.Agents.Poi.VectorDB.EmbeddingPipeline.EmbeddingPipeline import EmbeddingPipeline
        pipeline = EmbeddingPipeline()
        # 고유한 컬렉션 이름을 생성하여 테스트 간 데이터 간접 방지
        unique_name = f"test_coll_{uuid.uuid4().hex[:8]}"
        agent = VectorSearchAgent(
            embedding_pipeline=pipeline,
            collection_name=unique_name
        )
        return agent
    
    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_full_flow(self, agent):
        """POI 추가 및 검색 전체 플로우 테스트"""
        
        # 1. 초기 상태 확인 (새로 생성된 고유 컬렉션이므로 0이어야 함)
        initial_size = await agent.get_collection_size()
        assert initial_size == 0
        
        # 2. 데이터 추가
        poi = PoiData(
            id="integration-test-1",
            name="성수동 맛집",
            category=PoiCategory.RESTAURANT,
            description="성수동에 위치한 퓨전 레스토랑입니다.",
            source=PoiSource.WEB_SEARCH,
            raw_text="성수동 맛집입니다. 퓨전 요리를 제공합니다.",
            city="Seoul"
        )
        
        success = await agent.add_poi(poi)
        assert success is True
        
        # 3. 크기 증가 확인
        new_size = await agent.get_collection_size()
        assert new_size == 1
        
        # 4. 검색 확인
        results = await agent.search_by_text("성수동", k=1)
        
        assert len(results) > 0
        assert results[0].poi_id == "integration-test-1"
        assert results[0].source == PoiSource.EMBEDDING_DB

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_search_not_found_in_empty_collection(self, agent):
        """빈 컬렉션에서 검색 시 빈 결과 반환 확인"""
        results = await agent.search_by_text("서울 맛집", k=5)
        assert len(results) == 0

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_city_filtering(self, agent):
        """도시 필터링이 정상적으로 동작하는지 확인 (3개 도시, 데이터 개수 1/2/3)"""
        
        # 1. 3개 도시에 대한 데이터 준비
        city_counts = {
            "Seoul": 1,
            "Tokyo": 2,
            "Paris": 3
        }
        
        all_pois = []
        for city, count in city_counts.items():
            for i in range(count):
                all_pois.append(PoiData(
                    id=f"poi-{city}-{i}",
                    name=f"{city} 장소 {i}",
                    category=PoiCategory.RESTAURANT,
                    description=f"{city}에 있는 장소입니다.",
                    source=PoiSource.WEB_SEARCH,
                    raw_text=f"{city}의 멋진 장소 {i}번입니다.",
                    city=city
                ))
        
        # 2. 데이터 배치 추가
        added_count = await agent.add_pois_batch(all_pois)
        assert added_count == sum(city_counts.values()) # 1 + 2 + 3 = 6
        
        # 3. 2개의 데이터가 있는 도시(Tokyo) 필터링 조회
        # k를 충분히 크게 설정하여 필터링된 모든 결과가 나오도록 함
        results = await agent.search_by_text("장소", k=10, city_filter="Tokyo")
        
        # 4. 검증: 정확히 2개의 결과가 반환되어야 함
        assert len(results) == 2
        for result in results:
            # 반환된 결과가 Tokyo 데이터인지 보조 확인 (title 등의 검증은 필요에 따라 추가)
            assert "Tokyo" in result.title or "Tokyo" in result.snippet or any(
                p.city == "Tokyo" for p in all_pois if p.id == result.poi_id
            )
        
        # 5. 다른 도시(Paris)도 확인 (3개)
        results_paris = await agent.search_by_text("장소", k=10, city_filter="Paris")
        assert len(results_paris) == 3

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_add_pois_batch_dedup_integration(self, agent):
        """중복 ID 처리 통합 테스트: 배치 내 중복 + 기존 데이터 중복 모두 필터링"""

        # 1. 초기 데이터 추가
        initial_poi = PoiData(
            id="poi-dedup-1", name="초기 장소", category=PoiCategory.RESTAURANT,
            description="초기 데이터", source=PoiSource.WEB_SEARCH,
            raw_text="초기 장소 텍스트", city="Seoul"
        )
        added = await agent.add_pois_batch([initial_poi])
        assert added == 1

        # 2. 중복이 포함된 배치 추가 시도
        #    - poi-dedup-1: 컬렉션에 이미 존재 (필터링 대상)
        #    - poi-dedup-2: 배치 내 2번 등장 (첫 번째만 유지)
        #    - poi-dedup-3: 신규 데이터
        batch = [
            PoiData(id="poi-dedup-1", name="중복 장소", category=PoiCategory.RESTAURANT,
                    description="중복", source=PoiSource.WEB_SEARCH,
                    raw_text="중복 텍스트", city="Seoul"),
            PoiData(id="poi-dedup-2", name="장소2 첫번째", category=PoiCategory.CAFE,
                    description="첫번째", source=PoiSource.WEB_SEARCH,
                    raw_text="장소2 첫번째 텍스트", city="Seoul"),
            PoiData(id="poi-dedup-2", name="장소2 두번째", category=PoiCategory.CAFE,
                    description="두번째", source=PoiSource.WEB_SEARCH,
                    raw_text="장소2 두번째 텍스트", city="Seoul"),
            PoiData(id="poi-dedup-3", name="신규 장소", category=PoiCategory.RESTAURANT,
                    description="신규", source=PoiSource.WEB_SEARCH,
                    raw_text="신규 장소 텍스트", city="Seoul"),
        ]

        added = await agent.add_pois_batch(batch)
        assert added == 2  # poi-dedup-2, poi-dedup-3만 추가

        # 3. 총 데이터 수 확인: 초기 1 + 신규 2 = 3
        total = await agent.get_collection_size()
        assert total == 3
