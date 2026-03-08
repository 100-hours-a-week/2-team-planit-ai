from typing import Dict, List, Optional, Tuple
import asyncio
import json
import logging
import traceback
from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase
from pymongo import UpdateOne
from pymongo.operations import SearchIndexModel

from app.core.Agents.Poi.VectorDB.BaseVectorSearchAgent import BaseVectorSearchAgent
from app.core.Agents.Poi.VectorDB.EmbeddingPipeline.BaseEmbeddingPipeline import BaseEmbeddingPipeline
from app.core.models.PoiAgentDataclass.poi import (
    PoiSearchResult,
    PoiData,
    PoiCategory,
    PoiSource,
    OpeningHours,
)

logger = logging.getLogger(__name__)


class MongoVectorSearchAgent(BaseVectorSearchAgent):
    """
    MongoDB Vector Search 기반 벡터 검색 에이전트 구현

    $vectorSearch aggregation pipeline을 사용하여 코사인 유사도 검색을 수행합니다.
    motor(async MongoDB 드라이버)를 사용하며, 인덱스 자동 생성을 지원합니다.
    """

    def __init__(
        self,
        embedding_pipeline: BaseEmbeddingPipeline,
        mongodb_uri: str,
        db_name: str,
        collection_name: str = "poi_embeddings",
        index_name: str = "poi_vector_index",
    ):
        super().__init__(embedding_pipeline)
        self._uri = mongodb_uri
        self._db_name = db_name
        self._collection_name = collection_name
        self._index_name = index_name
        self._client: Optional[AsyncIOMotorClient] = None
        self._db: Optional[AsyncIOMotorDatabase] = None
        self._collection = None
        self._initialized = False
        self._init_lock = asyncio.Lock()
        self._embedding_dimensions: Optional[int] = None

    # ──────────────────────────────────────────────
    # 초기화
    # ──────────────────────────────────────────────

    async def _detect_embedding_dimensions(self) -> int:
        """EmbeddingPipeline에서 임베딩 차원 수를 자동 감지"""
        sample = await self.embedding_pipeline.embed_query("test")
        return len(sample)

    async def _ensure_vector_index(self, collection):
        """벡터 검색 인덱스 존재 확인, 없으면 생성"""
        # 1단계: 기존 인덱스 확인
        try:
            indexes = await collection.list_search_indexes().to_list()
            logger.info(f"이미 생성된 벡터 인덱스: {indexes}")
            for idx in indexes:
                if idx.get("name") == self._index_name:
                    logger.info(f"벡터 인덱스 '{self._index_name}' 이미 존재")
                    return
        except Exception as e:
            logger.warning(f"벡터 인덱스 목록 조회 실패 (인덱스 생성 시도): {e}")

        # 2단계: 인덱스 생성
        try:
            if self._embedding_dimensions is None:
                self._embedding_dimensions = await self._detect_embedding_dimensions()

            index_definition = {
                "fields": [
                    {
                        "type": "vector",
                        "path": "embedding",
                        "numDimensions": self._embedding_dimensions,
                        "similarity": "cosine",
                    },
                    {"type": "filter", "path": "metadata.city"},
                    {"type": "filter", "path": "metadata.name"},
                    {"type": "filter", "path": "metadata.google_place_id"},
                ]
            }

            result = await collection.create_search_index(
                SearchIndexModel(
                    definition=index_definition,
                    name=self._index_name,
                    type="vectorSearch",
                )
            )
            logger.info(
                f"벡터 인덱스 '{self._index_name}' 생성 완료: {result} "
                f"(dimensions={self._embedding_dimensions})"
            )
        except Exception as e:
            logger.error(f"벡터 인덱스 생성 오류: {e}")
            logger.error(traceback.format_exc())

    async def _initialize(self):
        """MongoDB 클라이언트 및 컬렉션 초기화 (지연 로딩, lock으로 보호)"""
        if self._initialized:
            return True

        async with self._init_lock:
            if self._initialized:
                return True
            try:
                self._client = AsyncIOMotorClient(self._uri)
                self._db = self._client[self._db_name]
                self._collection = self._db[self._collection_name]

                await self._ensure_vector_index(self._collection)

                self._initialized = True
                return True
            except Exception as e:
                logger.error(f"MongoDB 초기화 오류: {e}")
                return False

    # ──────────────────────────────────────────────
    # 헬퍼 메서드
    # ──────────────────────────────────────────────

    @staticmethod
    def prepare_document_text(poi: PoiData) -> str:
        """POI 데이터를 저장용 텍스트로 가공. 필요 시 수정."""
        return poi.raw_text

    @staticmethod
    def _build_metadata(poi: PoiData) -> dict:
        """PoiData에서 MongoDB metadata dict 생성"""
        metadata = {
            "name": poi.name,
            "category": poi.category.value,
            "description": poi.description,
            "city": poi.city or "",
            "address": poi.address or "",
            "source": poi.source.value,
            "source_url": poi.source_url or "",
            "google_place_id": poi.google_place_id or "",
            "latitude": poi.latitude if poi.latitude is not None else None,
            "longitude": poi.longitude if poi.longitude is not None else None,
            "google_maps_uri": poi.google_maps_uri or "",
            "types": json.dumps(poi.types) if poi.types else "[]",
            "primary_type": poi.primary_type or "",
            "google_rating": poi.google_rating if poi.google_rating is not None else None,
            "user_rating_count": poi.user_rating_count if poi.user_rating_count is not None else None,
            "price_level": poi.price_level or "",
            "price_range": poi.price_range or "",
            "website_uri": poi.website_uri or "",
            "phone_number": poi.phone_number or "",
            "opening_hours": poi.opening_hours.model_dump_json() if poi.opening_hours else "",
        }
        return metadata

    @staticmethod
    def _reconstruct_poi_data(doc: dict) -> PoiData:
        """MongoDB document에서 PoiData를 재구성"""
        metadata = doc.get("metadata", {})
        document_text = doc.get("document", "")

        types_raw = metadata.get("types", "[]")
        try:
            types = json.loads(types_raw) if types_raw else []
        except (json.JSONDecodeError, TypeError):
            types = []

        opening_hours = None
        oh_raw = metadata.get("opening_hours", "")
        if oh_raw:
            try:
                opening_hours = OpeningHours.model_validate_json(oh_raw)
            except Exception:
                opening_hours = None

        return PoiData(
            id=str(doc["_id"]),
            name=metadata.get("name", ""),
            category=PoiCategory(metadata.get("category", "other")),
            description=metadata.get("description", ""),
            city=metadata.get("city") or None,
            address=metadata.get("address") or None,
            source=PoiSource(metadata.get("source", "web_search")),
            source_url=metadata.get("source_url") or None,
            raw_text=document_text or "",
            google_place_id=metadata.get("google_place_id") or None,
            latitude=float(metadata["latitude"]) if metadata.get("latitude") is not None else None,
            longitude=float(metadata["longitude"]) if metadata.get("longitude") is not None else None,
            google_maps_uri=metadata.get("google_maps_uri") or None,
            types=types,
            primary_type=metadata.get("primary_type") or None,
            google_rating=float(metadata["google_rating"]) if metadata.get("google_rating") is not None else None,
            user_rating_count=int(metadata["user_rating_count"]) if metadata.get("user_rating_count") is not None else None,
            price_level=metadata.get("price_level") or None,
            price_range=metadata.get("price_range") or None,
            website_uri=metadata.get("website_uri") or None,
            phone_number=metadata.get("phone_number") or None,
            opening_hours=opening_hours,
        )

    # ──────────────────────────────────────────────
    # 검색 메서드
    # ──────────────────────────────────────────────

    async def search(
        self,
        query_embedding: List[float],
        k: int = 10,
        city_filter: Optional[str] = None,
    ) -> List[PoiSearchResult]:
        """임베딩 벡터로 유사도 검색"""
        if not await self._initialize():
            return []

        try:
            vector_search_stage = {
                "$vectorSearch": {
                    "index": self._index_name,
                    "path": "embedding",
                    "queryVector": query_embedding,
                    "numCandidates": k * 10,
                    "limit": k,
                }
            }

            if city_filter:
                vector_search_stage["$vectorSearch"]["filter"] = {
                    "metadata.city": {"$eq": city_filter}
                }

            pipeline = [
                vector_search_stage,
                {
                    "$project": {
                        "_id": 1,
                        "document": 1,
                        "metadata": 1,
                        "score": {"$meta": "vectorSearchScore"},
                    }
                },
            ]

            results = await self._collection.aggregate(pipeline).to_list(length=k)

            search_results = []
            for doc in results:
                metadata = doc.get("metadata", {})
                document_text = doc.get("document", "")
                similarity = doc.get("score", 0.0)

                result = PoiSearchResult(
                    poi_id=str(doc["_id"]),
                    title=metadata.get("name", ""),
                    snippet=document_text[:500] if document_text else "",
                    url=metadata.get("source_url") or None,
                    source=PoiSource.EMBEDDING_DB,
                    relevance_score=similarity,
                )
                search_results.append(result)

            return search_results

        except Exception as e:
            logger.error(f"MongoDB vector search 오류: {e}")
            return []

    async def search_by_text(
        self,
        query: str,
        k: int = 10,
        city_filter: Optional[str] = None,
    ) -> List[PoiSearchResult]:
        """텍스트 쿼리로 검색 (EmbeddingPipeline 사용)"""
        if not await self._initialize():
            return []

        try:
            count = await self._collection.count_documents({})
            if count == 0:
                return []

            query_embedding = await self.embedding_pipeline.embed_query(query)
            return await self.search(query_embedding, k, city_filter)

        except Exception as e:
            logger.error(f"MongoDB vector text search 오류: {e}")
            return []

    async def search_with_data(
        self,
        query_embedding: List[float],
        k: int = 10,
        city_filter: Optional[str] = None,
    ) -> List[Tuple[PoiSearchResult, PoiData]]:
        """임베딩 벡터로 유사도 검색 + PoiData 복원"""
        if not await self._initialize():
            return []

        try:
            vector_search_stage = {
                "$vectorSearch": {
                    "index": self._index_name,
                    "path": "embedding",
                    "queryVector": query_embedding,
                    "numCandidates": k * 10,
                    "limit": k,
                }
            }

            if city_filter:
                vector_search_stage["$vectorSearch"]["filter"] = {
                    "metadata.city": {"$eq": city_filter}
                }

            pipeline = [
                vector_search_stage,
                {
                    "$project": {
                        "_id": 1,
                        "document": 1,
                        "metadata": 1,
                        "score": {"$meta": "vectorSearchScore"},
                    }
                },
            ]

            results = await self._collection.aggregate(pipeline).to_list(length=k)

            paired_results = []
            for doc in results:
                metadata = doc.get("metadata", {})
                document_text = doc.get("document", "")
                similarity = doc.get("score", 0.0)

                search_result = PoiSearchResult(
                    poi_id=str(doc["_id"]),
                    title=metadata.get("name", ""),
                    snippet=document_text[:500] if document_text else "",
                    url=metadata.get("source_url") or None,
                    source=PoiSource.EMBEDDING_DB,
                    relevance_score=similarity,
                )

                poi_data = self._reconstruct_poi_data(doc)
                paired_results.append((search_result, poi_data))

            return paired_results

        except Exception as e:
            logger.error(f"MongoDB vector search_with_data 오류: {e}")
            return []

    async def search_by_text_with_data(
        self,
        query: str,
        k: int = 10,
        city_filter: Optional[str] = None,
    ) -> List[Tuple[PoiSearchResult, PoiData]]:
        """텍스트 쿼리로 검색 + PoiData 복원"""
        if not await self._initialize():
            return []

        try:
            count = await self._collection.count_documents({})
            if count == 0:
                logger.info("MongoDB VectorDB에 저장된 POI가 없습니다.")
                return []

            query_embedding = await self.embedding_pipeline.embed_query(query)
            return await self.search_with_data(query_embedding, k, city_filter)

        except Exception as e:
            logger.error(f"MongoDB vector text search_with_data 오류: {e}")
            return []

    # ──────────────────────────────────────────────
    # 쓰기 메서드
    # ──────────────────────────────────────────────

    async def add_poi(self, poi: PoiData) -> bool:
        """POI 데이터를 MongoDB에 추가 (upsert)"""
        if not await self._initialize():
            return False

        try:
            embeddings = await self.embedding_pipeline.embed_documents([poi])
            metadata = self._build_metadata(poi)
            document_text = self.prepare_document_text(poi)

            await self._collection.update_one(
                {"_id": poi.id},
                {
                    "$set": {
                        "embedding": embeddings[0],
                        "document": document_text,
                        "metadata": metadata,
                    }
                },
                upsert=True,
            )
            return True

        except Exception as e:
            logger.error(f"MongoDB add POI 오류: {e}")
            return False

    async def add_pois_batch(self, pois: List[PoiData]) -> int:
        """POI 데이터를 배치로 추가 (upsert)"""
        if not await self._initialize() or not pois:
            return 0

        try:
            # 배치 내 중복 ID 제거
            seen_ids: set = set()
            unique_pois: List[PoiData] = []
            for poi in pois:
                if poi.id not in seen_ids:
                    seen_ids.add(poi.id)
                    unique_pois.append(poi)

            embeddings = await self.embedding_pipeline.embed_documents(unique_pois)

            operations = []
            for poi, embedding in zip(unique_pois, embeddings):
                metadata = self._build_metadata(poi)
                document_text = self.prepare_document_text(poi)
                operations.append(
                    UpdateOne(
                        {"_id": poi.id},
                        {
                            "$set": {
                                "embedding": embedding,
                                "document": document_text,
                                "metadata": metadata,
                            }
                        },
                        upsert=True,
                    )
                )

            if operations:
                result = await self._collection.bulk_write(operations)
                added = result.upserted_count + result.modified_count
                logger.info(f"MongoDB 배치 추가 완료: {added}개")
                return added

            return 0

        except Exception as e:
            logger.error(f"MongoDB batch add POI 오류: {e}")
            return 0

    # ──────────────────────────────────────────────
    # 조회 메서드
    # ──────────────────────────────────────────────

    async def find_by_name(
        self,
        name: str,
        city_filter: Optional[str] = None,
    ) -> Optional[PoiData]:
        """이름으로 POI 검색"""
        if not await self._initialize() or not name:
            return None

        try:
            query = {"metadata.name": {"$eq": name}}
            if city_filter:
                query["metadata.city"] = {"$eq": city_filter}

            doc = await self._collection.find_one(query)
            if doc:
                return self._reconstruct_poi_data(doc)
            return None

        except Exception as e:
            logger.error(f"MongoDB find_by_name 오류 ({name}): {e}")
            return None

    async def find_by_google_place_id(
        self,
        google_place_id: str,
        city_filter: Optional[str] = None,
    ) -> Optional[PoiData]:
        """Google Place ID로 POI 검색"""
        if not await self._initialize() or not google_place_id:
            return None

        try:
            query = {"metadata.google_place_id": {"$eq": google_place_id}}
            if city_filter:
                query["metadata.city"] = {"$eq": city_filter}

            doc = await self._collection.find_one(query)
            if doc:
                return self._reconstruct_poi_data(doc)
            return None

        except Exception as e:
            logger.error(f"MongoDB find_by_google_place_id 오류 ({google_place_id}): {e}")
            return None

    async def get_collection_size(self) -> int:
        """컬렉션 내 문서 수 반환"""
        if not await self._initialize():
            return 0

        try:
            return await self._collection.count_documents({})
        except Exception:
            return 0
