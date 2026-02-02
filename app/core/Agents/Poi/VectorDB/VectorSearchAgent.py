from typing import Dict, List, Optional, Tuple
import json
import os
from pathlib import Path
import chromadb
from chromadb.config import Settings

from app.core.Agents.Poi.VectorDB.BaseVectorSearchAgent import BaseVectorSearchAgent
from app.core.Agents.Poi.VectorDB.EmbeddingPipeline.BaseEmbeddingPipeline import BaseEmbeddingPipeline
from app.core.models.PoiAgentDataclass.poi import (
    PoiSearchResult,
    PoiData,
    PoiCategory,
    PoiSource,
    OpeningHours,
)

# 기본 저장 경로 (프로젝트 루트/app/data/vector_db)
DEFAULT_PERSIST_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))),
    "data", "vector_db"
)


class VectorSearchAgent(BaseVectorSearchAgent):
    """
    ChromaDB 기반 벡터 검색 에이전트 구현
    
    EmbeddingPipeline을 포함하여 텍스트 임베딩 변환 및 저장/검색을 담당합니다.
    """
    
    def __init__(
        self,
        embedding_pipeline: BaseEmbeddingPipeline,
        collection_name: str = "poi_embeddings",
        persist_directory: Optional[str] = None,
        use_persistent: bool = True
    ):
        super().__init__(embedding_pipeline)
        self.collection_name = collection_name
        # 기본 저장 경로 설정 (use_persistent=False이면 인메모리)
        if use_persistent:
            self.persist_directory = persist_directory or DEFAULT_PERSIST_DIR
        else:
            self.persist_directory = None
        self._client = None
        self._collection = None
        self._initialized = False
    
    def _initialize(self):
        """ChromaDB 클라이언트 및 컬렉션 초기화 (지연 로딩)"""
        if self._initialized:
            return True
            
        try:
            if self.persist_directory:
                # 디렉토리 자동 생성
                Path(self.persist_directory).mkdir(parents=True, exist_ok=True)
                self._client = chromadb.PersistentClient(
                    path=self.persist_directory,
                    settings=Settings(anonymized_telemetry=False)
                )
            else:
                self._client = chromadb.Client(
                    settings=Settings(anonymized_telemetry=False)
                )
            
            self._collection = self._client.get_or_create_collection(
                name=self.collection_name,
                metadata={"hnsw:space": "cosine"}
            )
            self._initialized = True
            return True

        except Exception as e:
            print(f"ChromaDB initialization error: {e}")
            return False
    
    async def search(
        self, 
        query_embedding: List[float], 
        k: int,
        city_filter: str
    ) -> List[PoiSearchResult]:
        """임베딩 벡터로 유사도 검색"""
        if not self._initialize():
            return []
        
        try:
            # 도시 필터가 있으면 where 절 구성
            where_filter = None
            if city_filter:
                where_filter = {"city": {"$eq": city_filter}}
            
            results = self._collection.query(
                query_embeddings=[query_embedding],
                n_results=k,
                where=where_filter,
                include=["documents", "metadatas", "distances"]
            )
            
            search_results = []
            for i, doc_id in enumerate(results.get("ids", [[]])[0]):
                metadata = results.get("metadatas", [[]])[0][i] if results.get("metadatas") else {}
                document = results.get("documents", [[]])[0][i] if results.get("documents") else ""
                distance = results.get("distances", [[]])[0][i] if results.get("distances") else 1.0
                
                # cosine distance를 similarity score로 변환
                similarity = 1 - distance
                
                result = PoiSearchResult(
                    poi_id=doc_id,
                    title=metadata.get("name", ""),
                    snippet=document[:500] if document else "",
                    url=metadata.get("source_url"),
                    source=PoiSource.EMBEDDING_DB,
                    relevance_score=similarity
                )
                search_results.append(result)
            
            return search_results
            
        except Exception as e:
            print(f"Vector search error: {e}")
            return []
    
    async def search_by_text(
        self, 
        query: str, 
        k: int,
        city_filter: str
    ) -> List[PoiSearchResult]:
        """텍스트 쿼리로 검색 (EmbeddingPipeline 사용)
        
        Args:
            query: 검색 텍스트
            k: 반환할 결과 수
            city_filter: 도시 필터 (해당 도시의 POI만 검색)
        """
        if not self._initialize():
            return []
        
        try:
            # 컬렉션이 비어있으면 빈 결과 반환
            if self._collection.count() == 0:
                return []
            
            # EmbeddingPipeline으로 쿼리 임베딩 생성
            query_embedding = await self.embedding_pipeline.embed_query(query)
            
            return await self.search(query_embedding, k, city_filter)
            
        except Exception as e:
            print(f"Vector text search error: {e}")
            return []
    
    @staticmethod
    def _build_metadata(poi: PoiData) -> dict:
        """PoiData에서 ChromaDB metadata dict 생성 (전체 필드 포함)"""
        metadata = {
            "name": poi.name,
            "category": poi.category.value,
            "description": poi.description,
            "city": poi.city or "",
            "address": poi.address or "",
            "source": poi.source.value,
            "source_url": poi.source_url or "",
            # Google Maps 필드
            "google_place_id": poi.google_place_id or "",
            "latitude": poi.latitude if poi.latitude is not None else "",
            "longitude": poi.longitude if poi.longitude is not None else "",
            "google_maps_uri": poi.google_maps_uri or "",
            "types": json.dumps(poi.types) if poi.types else "[]",
            "primary_type": poi.primary_type or "",
            # 상세 정보
            "google_rating": poi.google_rating if poi.google_rating is not None else "",
            "user_rating_count": poi.user_rating_count if poi.user_rating_count is not None else "",
            "price_level": poi.price_level or "",
            "price_range": poi.price_range or "",
            "website_uri": poi.website_uri or "",
            "phone_number": poi.phone_number or "",
            # 영업시간 (JSON 직렬화)
            "opening_hours": poi.opening_hours.model_dump_json() if poi.opening_hours else "",
        }
        return metadata

    @staticmethod
    def _reconstruct_poi_data(doc_id: str, metadata: dict, document: str) -> PoiData:
        """ChromaDB metadata에서 PoiData를 재구성"""
        # types 파싱
        types_raw = metadata.get("types", "[]")
        try:
            types = json.loads(types_raw) if types_raw else []
        except (json.JSONDecodeError, TypeError):
            types = []

        # opening_hours 파싱
        opening_hours = None
        oh_raw = metadata.get("opening_hours", "")
        if oh_raw:
            try:
                opening_hours = OpeningHours.model_validate_json(oh_raw)
            except Exception:
                opening_hours = None

        return PoiData(
            id=doc_id,
            name=metadata.get("name", ""),
            category=PoiCategory(metadata.get("category", "other")),
            description=metadata.get("description", ""),
            city=metadata.get("city") or None,
            address=metadata.get("address") or None,
            source=PoiSource(metadata.get("source", "web_search")),
            source_url=metadata.get("source_url") or None,
            raw_text=document or "",
            google_place_id=metadata.get("google_place_id") or None,
            latitude=float(metadata["latitude"]) if metadata.get("latitude") not in ("", None) else None,
            longitude=float(metadata["longitude"]) if metadata.get("longitude") not in ("", None) else None,
            google_maps_uri=metadata.get("google_maps_uri") or None,
            types=types,
            primary_type=metadata.get("primary_type") or None,
            google_rating=float(metadata["google_rating"]) if metadata.get("google_rating") not in ("", None) else None,
            user_rating_count=int(metadata["user_rating_count"]) if metadata.get("user_rating_count") not in ("", None) else None,
            price_level=metadata.get("price_level") or None,
            price_range=metadata.get("price_range") or None,
            website_uri=metadata.get("website_uri") or None,
            phone_number=metadata.get("phone_number") or None,
            opening_hours=opening_hours,
        )

    async def add_poi(self, poi: PoiData) -> bool:
        """POI 데이터를 벡터 DB에 추가 (EmbeddingPipeline 사용)"""
        if not self._initialize():
            return False

        try:
            # EmbeddingPipeline으로 임베딩 생성
            embeddings = await self.embedding_pipeline.embed_documents([poi.raw_text])

            self._collection.add(
                ids=[poi.id],
                embeddings=embeddings,
                documents=[poi.raw_text],
                metadatas=[self._build_metadata(poi)]
            )
            return True

        except Exception as e:
            print(f"Add POI error: {e}")
            return False

    async def add_pois_batch(self, pois: List[PoiData]) -> int:
        """POI 데이터를 배치로 추가 (EmbeddingPipeline 사용)

        배치 내 중복 ID와 컬렉션에 이미 존재하는 ID를 자동으로 필터링합니다.
        """
        if not self._initialize() or not pois:
            return 0

        try:
            # 1. 배치 내 중복 ID 제거 (첫 번째 항목 유지)
            seen_ids: set = set()
            unique_pois: List[PoiData] = []
            for poi in pois:
                if poi.id not in seen_ids:
                    seen_ids.add(poi.id)
                    unique_pois.append(poi)

            # 2. 컬렉션에 이미 존재하는 ID 필터링
            candidate_ids = [poi.id for poi in unique_pois]
            existing = self._collection.get(ids=candidate_ids)
            existing_ids = set(existing["ids"]) if existing and existing.get("ids") else set()
            new_pois = [poi for poi in unique_pois if poi.id not in existing_ids]

            if not new_pois:
                return 0

            ids = [poi.id for poi in new_pois]
            documents = [poi.raw_text for poi in new_pois]
            metadatas = [self._build_metadata(poi) for poi in new_pois]

            # EmbeddingPipeline으로 배치 임베딩 생성
            embeddings = await self.embedding_pipeline.embed_documents(documents)

            self._collection.add(
                ids=ids,
                embeddings=embeddings,
                documents=documents,
                metadatas=metadatas
            )
            return len(new_pois)

        except Exception as e:
            print(f"Batch add POI error: {e}")
            return 0
    
    async def search_with_data(
        self,
        query_embedding: List[float],
        k: int,
        city_filter: str
    ) -> List[Tuple[PoiSearchResult, PoiData]]:
        """임베딩 벡터로 유사도 검색 + PoiData 복원"""
        if not self._initialize():
            return []

        try:
            where_filter = None
            if city_filter:
                where_filter = {"city": {"$eq": city_filter}}

            results = self._collection.query(
                query_embeddings=[query_embedding],
                n_results=k,
                where=where_filter,
                include=["documents", "metadatas", "distances"]
            )

            paired_results = []
            for i, doc_id in enumerate(results.get("ids", [[]])[0]):
                metadata = results.get("metadatas", [[]])[0][i] if results.get("metadatas") else {}
                document = results.get("documents", [[]])[0][i] if results.get("documents") else ""
                distance = results.get("distances", [[]])[0][i] if results.get("distances") else 1.0

                similarity = 1 - distance

                search_result = PoiSearchResult(
                    poi_id=doc_id,
                    title=metadata.get("name", ""),
                    snippet=document[:500] if document else "",
                    url=metadata.get("source_url") or None,
                    source=PoiSource.EMBEDDING_DB,
                    relevance_score=similarity
                )

                poi_data = self._reconstruct_poi_data(doc_id, metadata, document)
                paired_results.append((search_result, poi_data))

            return paired_results

        except Exception as e:
            print(f"Vector search_with_data error: {e}")
            return []

    async def search_by_text_with_data(
        self,
        query: str,
        k: int,
        city_filter: str
    ) -> List[Tuple[PoiSearchResult, PoiData]]:
        """텍스트 쿼리로 검색 + PoiData 복원

        Args:
            query: 검색 텍스트
            k: 반환할 결과 수
            city_filter: 도시 필터
        """
        if not self._initialize():
            return []

        try:
            if self._collection.count() == 0:
                print("VectorDB에 저장된 POI가 없습니다.")
                return []

            query_embedding = await self.embedding_pipeline.embed_query(query)
            return await self.search_with_data(query_embedding, k, city_filter)

        except Exception as e:
            print(f"Vector text search_with_data error: {e}")
            return []

    async def get_collection_size(self) -> int:
        """벡터 DB의 현재 데이터 개수 반환"""
        if not self._initialize():
            return 0
        
        try:
            return self._collection.count()
        except Exception:
            return 0
