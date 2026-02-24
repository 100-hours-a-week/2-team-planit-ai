"""
TypeEmbeddingStore 및 TypeBasedRecommender 단위 테스트

테스트 항목:
1. TypeEmbeddingStore: 인덱스 구축, 타입 검색, POI ID 조회, 단일 POI 추가
2. TypeBasedRecommender: 키워드→타입→POI 파이프라인, 중복 제거
"""

import asyncio
import json
import pytest
import pytest_asyncio
import uuid
from unittest.mock import MagicMock
from typing import List

from app.core.Agents.Poi.VectorDB.TypeEmbeddingStore import (
    TypeEmbeddingStore,
    TypeMatch,
    EXCLUDED_TYPES,
)
from app.core.Agents.Poi.TypeBasedRecommender import (
    TypeBasedRecommender,
)
from app.core.models.PoiAgentDataclass.poi import (
    PoiData,
    PoiCategory,
    PoiSource,
    PoiSearchResult,
)


# ======================================================================
# Fixtures
# ======================================================================


def _make_poi(
    poi_id: str, name: str, types: List[str], city: str = "도쿄"
) -> PoiData:
    """테스트용 PoiData 생성 헬퍼"""
    return PoiData(
        id=poi_id,
        name=name,
        category=PoiCategory.ATTRACTION,
        description=f"{name} 설명",
        city=city,
        source=PoiSource.WEB_SEARCH,
        raw_text=f"{name} raw text",
        types=types,
        primary_type=types[0] if types else None,
    )


@pytest.fixture
def sample_pois() -> List[PoiData]:
    """테스트용 POI 데이터"""
    return [
        _make_poi("poi_1", "스시 오마카세", ["restaurant", "japanese_restaurant", "food"]),
        _make_poi("poi_2", "라멘 이치란", ["restaurant", "ramen_restaurant", "food"]),
        _make_poi("poi_3", "도쿄 국립박물관", ["museum", "tourist_attraction"]),
        _make_poi("poi_4", "우에노 공원", ["park", "tourist_attraction"]),
        _make_poi("poi_5", "시부야 카페", ["cafe", "coffee_shop"]),
        _make_poi("poi_6", "아사쿠사 사원", ["place_of_worship", "tourist_attraction"]),
    ]


@pytest.fixture
def mock_embedding_pipeline():
    """모의 임베딩 파이프라인"""
    pipeline = MagicMock()

    async def mock_embed(texts, task_type=None):
        """텍스트마다 고유한 임베딩 벡터 생성"""
        embeddings = []
        for text in texts:
            hash_val = hash(text) % 1000
            base = [hash_val / 1000.0] * 384
            embeddings.append(base)
        return embeddings

    async def mock_embed_query(query):
        result = await mock_embed([query])
        return result[0]

    pipeline.embed = mock_embed
    pipeline.embed_query = mock_embed_query
    return pipeline


def _make_fresh_store(mock_embedding_pipeline) -> TypeEmbeddingStore:
    """매 테스트마다 고유 컬렉션을 사용하는 새 TypeEmbeddingStore"""
    unique_name = f"test_type_{uuid.uuid4().hex[:8]}"
    return TypeEmbeddingStore(
        embedding_pipeline=mock_embedding_pipeline,
        collection_name=unique_name,
        use_persistent=False,
    )


# ======================================================================
# TypeEmbeddingStore 테스트
# ======================================================================


class TestTypeEmbeddingStore:
    """TypeEmbeddingStore 단위 테스트"""

    @pytest.mark.asyncio
    async def test_build_index_basic(self, sample_pois, mock_embedding_pipeline):
        """기본 인덱스 구축 테스트"""
        store = _make_fresh_store(mock_embedding_pipeline)
        count = await store.build_index_from_pois(sample_pois)

        assert count > 0
        size = await store.get_collection_size()
        assert size == count

    @pytest.mark.asyncio
    async def test_build_index_excludes_types(self, mock_embedding_pipeline):
        """EXCLUDED_TYPES가 필터링되는지 확인"""
        store = _make_fresh_store(mock_embedding_pipeline)
        pois = [
            _make_poi("p1", "역", ["train_station", "transit_station"]),
            _make_poi("p2", "식당", ["restaurant"]),
        ]
        await store.build_index_from_pois(pois)

        all_types = await store.get_all_types()
        assert "train_station" not in all_types
        assert "transit_station" not in all_types
        assert "restaurant" in all_types

    @pytest.mark.asyncio
    async def test_build_index_poi_ids_in_metadata(self, sample_pois, mock_embedding_pipeline):
        """타입별 POI ID가 메타데이터에 올바르게 저장되는지 확인"""
        store = _make_fresh_store(mock_embedding_pipeline)
        await store.build_index_from_pois(sample_pois)

        poi_ids = await store.get_poi_ids_by_type("restaurant")
        assert "poi_1" in poi_ids
        assert "poi_2" in poi_ids
        assert len(poi_ids) == 2

    @pytest.mark.asyncio
    async def test_build_index_tourist_attraction(self, sample_pois, mock_embedding_pipeline):
        """tourist_attraction 타입의 POI가 올바르게 집계되는지 확인"""
        store = _make_fresh_store(mock_embedding_pipeline)
        await store.build_index_from_pois(sample_pois)

        poi_ids = await store.get_poi_ids_by_type("tourist_attraction")
        assert "poi_3" in poi_ids
        assert "poi_4" in poi_ids
        assert "poi_6" in poi_ids
        assert len(poi_ids) == 3

    @pytest.mark.asyncio
    async def test_search_types_returns_results(self, sample_pois, mock_embedding_pipeline):
        """타입 검색이 결과를 반환하는지 확인"""
        store = _make_fresh_store(mock_embedding_pipeline)
        await store.build_index_from_pois(sample_pois)

        results = await store.search_types("restaurant", k=3)
        assert len(results) > 0
        assert all(isinstance(r, TypeMatch) for r in results)
        assert all(r.score >= 0 for r in results)

    @pytest.mark.asyncio
    async def test_search_types_empty_collection(self, mock_embedding_pipeline):
        """빈 컬렉션에서 검색 시 빈 리스트 반환"""
        store = _make_fresh_store(mock_embedding_pipeline)
        results = await store.search_types("restaurant")
        assert results == []

    @pytest.mark.asyncio
    async def test_add_poi_new_type(self, sample_pois, mock_embedding_pipeline):
        """기존 인덱스에 새 타입을 가진 POI 추가"""
        store = _make_fresh_store(mock_embedding_pipeline)
        await store.build_index_from_pois(sample_pois)

        new_poi = _make_poi("poi_new", "스키장", ["ski_resort", "sports_activity_location"])
        success = await store.add_poi(new_poi)
        assert success

        all_types = await store.get_all_types()
        assert "ski_resort" in all_types

        poi_ids = await store.get_poi_ids_by_type("ski_resort")
        assert "poi_new" in poi_ids

    @pytest.mark.asyncio
    async def test_add_poi_existing_type(self, sample_pois, mock_embedding_pipeline):
        """기존 타입에 새 POI 추가 시 poi_ids가 업데이트되는지 확인"""
        store = _make_fresh_store(mock_embedding_pipeline)
        await store.build_index_from_pois(sample_pois)

        new_poi = _make_poi("poi_new_rest", "새 식당", ["restaurant"])
        await store.add_poi(new_poi)

        poi_ids = await store.get_poi_ids_by_type("restaurant")
        assert "poi_new_rest" in poi_ids
        assert "poi_1" in poi_ids
        assert "poi_2" in poi_ids

    @pytest.mark.asyncio
    async def test_get_poi_ids_nonexistent_type(self, sample_pois, mock_embedding_pipeline):
        """존재하지 않는 타입 조회 시 빈 리스트 반환"""
        store = _make_fresh_store(mock_embedding_pipeline)
        await store.build_index_from_pois(sample_pois)
        poi_ids = await store.get_poi_ids_by_type("nonexistent_type")
        assert poi_ids == []

    @pytest.mark.asyncio
    async def test_get_all_types(self, sample_pois, mock_embedding_pipeline):
        """등록된 모든 타입 조회"""
        store = _make_fresh_store(mock_embedding_pipeline)
        await store.build_index_from_pois(sample_pois)
        all_types = await store.get_all_types()

        expected_types = set()
        for poi in sample_pois:
            for t in poi.types:
                if t not in EXCLUDED_TYPES:
                    expected_types.add(t)
        assert set(all_types) == expected_types


# ======================================================================
# TypeBasedRecommender 테스트
# ======================================================================


def _build_mock_vector_search(sample_pois: List[PoiData]):
    """모의 VectorSearchAgent 생성"""
    from app.core.Agents.Poi.VectorDB.VectorSearchAgent import VectorSearchAgent

    mock_vs = MagicMock()
    mock_vs._initialized = True
    mock_vs._init_lock = asyncio.Lock()

    async def mock_init():
        return True
    mock_vs._initialize = mock_init

    poi_map = {poi.id: poi for poi in sample_pois}

    def mock_collection_get(ids=None, include=None):
        found_ids = []
        found_metadatas = []
        found_documents = []
        for pid in (ids or []):
            if pid in poi_map:
                poi = poi_map[pid]
                found_ids.append(pid)
                found_metadatas.append({
                    "name": poi.name,
                    "category": poi.category.value,
                    "description": poi.description or "",
                    "city": poi.city or "",
                    "address": "",
                    "source": poi.source.value,
                    "source_url": "",
                    "google_place_id": "",
                    "latitude": "",
                    "longitude": "",
                    "google_maps_uri": "",
                    "types": json.dumps(poi.types),
                    "primary_type": poi.primary_type or "",
                    "google_rating": "",
                    "user_rating_count": "",
                    "price_level": "",
                    "price_range": "",
                    "website_uri": "",
                    "phone_number": "",
                    "opening_hours": "",
                })
                found_documents.append(poi.raw_text)
        return {
            "ids": found_ids,
            "metadatas": found_metadatas,
            "documents": found_documents,
        }

    mock_collection = MagicMock()
    mock_collection.get = mock_collection_get
    mock_vs._collection = mock_collection
    mock_vs._reconstruct_poi_data = VectorSearchAgent._reconstruct_poi_data

    return mock_vs


class TestTypeBasedRecommender:
    """TypeBasedRecommender 단위 테스트"""

    @pytest.mark.asyncio
    async def test_recommend_basic(self, sample_pois, mock_embedding_pipeline):
        """기본 추천 테스트: 결과 반환됨"""
        store = _make_fresh_store(mock_embedding_pipeline)
        await store.build_index_from_pois(sample_pois)
        mock_vs = _build_mock_vector_search(sample_pois)

        recommender = TypeBasedRecommender(
            type_store=store,
            vector_search=mock_vs,
            embedding_pipeline=mock_embedding_pipeline,
        )
        results, poi_data_map = await recommender.recommend(
            keywords=["restaurant"],
            city="도쿄",
        )
        assert len(results) > 0
        assert len(poi_data_map) > 0

    @pytest.mark.asyncio
    async def test_recommend_empty_keywords(self, sample_pois, mock_embedding_pipeline):
        """빈 키워드 → 빈 결과"""
        store = _make_fresh_store(mock_embedding_pipeline)
        mock_vs = _build_mock_vector_search(sample_pois)

        recommender = TypeBasedRecommender(
            type_store=store,
            vector_search=mock_vs,
            embedding_pipeline=mock_embedding_pipeline,
        )
        results, poi_data_map = await recommender.recommend(
            keywords=[],
            city="도쿄",
        )
        assert results == []
        assert poi_data_map == {}

    @pytest.mark.asyncio
    async def test_recommend_deduplication(self, sample_pois, mock_embedding_pipeline):
        """여러 키워드에서 동일 POI가 중복되지 않는지 확인"""
        store = _make_fresh_store(mock_embedding_pipeline)
        await store.build_index_from_pois(sample_pois)
        mock_vs = _build_mock_vector_search(sample_pois)

        recommender = TypeBasedRecommender(
            type_store=store,
            vector_search=mock_vs,
            embedding_pipeline=mock_embedding_pipeline,
        )
        results, poi_data_map = await recommender.recommend(
            keywords=["tourist_attraction", "museum"],
            city="도쿄",
            k_types_per_keyword=5,
        )

        # POI ID 중복 확인
        poi_ids = [r.poi_id for r in results]
        assert len(poi_ids) == len(set(poi_ids)), "중복된 POI가 있습니다"

    @pytest.mark.asyncio
    async def test_recommend_results_sorted(self, sample_pois, mock_embedding_pipeline):
        """결과가 점수 내림차순으로 정렬되는지 확인"""
        store = _make_fresh_store(mock_embedding_pipeline)
        await store.build_index_from_pois(sample_pois)
        mock_vs = _build_mock_vector_search(sample_pois)

        recommender = TypeBasedRecommender(
            type_store=store,
            vector_search=mock_vs,
            embedding_pipeline=mock_embedding_pipeline,
        )
        results, _ = await recommender.recommend(
            keywords=["restaurant", "park"],
            city="도쿄",
        )
        if len(results) > 1:
            for i in range(len(results) - 1):
                assert results[i].relevance_score >= results[i + 1].relevance_score

    @pytest.mark.asyncio
    async def test_recommend_min_type_score(self, sample_pois, mock_embedding_pipeline):
        """min_type_score 필터링 확인"""
        store = _make_fresh_store(mock_embedding_pipeline)
        await store.build_index_from_pois(sample_pois)
        mock_vs = _build_mock_vector_search(sample_pois)

        recommender = TypeBasedRecommender(
            type_store=store,
            vector_search=mock_vs,
            embedding_pipeline=mock_embedding_pipeline,
        )
        results_high, _ = await recommender.recommend(
            keywords=["restaurant"],
            city="도쿄",
            min_type_score=0.99,
        )
        results_low, _ = await recommender.recommend(
            keywords=["restaurant"],
            city="도쿄",
            min_type_score=0.0,
        )
        assert len(results_high) <= len(results_low)
