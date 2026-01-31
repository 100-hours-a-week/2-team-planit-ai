from typing import List, Optional
import chromadb
from chromadb.config import Settings

from app.core.Agents.Poi.VectorDB.BaseVectorSearchAgent import BaseVectorSearchAgent
from app.core.Agents.Poi.VectorDB.EmbeddingPipeline.BaseEmbeddingPipeline import BaseEmbeddingPipeline
from app.core.models.PoiAgentDataclass.poi import (
    PoiSearchResult,
    PoiData,
    PoiSource,
    DEFAULT_DISTANCE,
    DEFAULT_DOCUMENT,
    DEFAULT_METADATA
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
        persist_directory: Optional[str] = None
    ):
        super().__init__(embedding_pipeline)
        self.collection_name = collection_name
        self.persist_directory = persist_directory
        self._client = None
        self._collection = None
        self._initialized = False
    
    def _initialize(self):
        """ChromaDB 클라이언트 및 컬렉션 초기화 (지연 로딩)"""
        if self._initialized:
            return True
            
        try:
            if self.persist_directory:
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
        k: int = 10,
        city_filter: Optional[str] = None
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
        k: int = 10,
        city_filter: Optional[str] = None
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
                metadatas=[{
                    "name": poi.name,
                    "category": poi.category.value,
                    "description": poi.description,
                    "city": poi.city or "",
                    "address": poi.address or "",
                    "source": poi.source.value,
                    "source_url": poi.source_url or "",
                }]
            )
            return True
            
        except Exception as e:
            print(f"Add POI error: {e}")
            return False
    
    async def add_pois_batch(self, pois: List[PoiData]) -> int:
        """POI 데이터를 배치로 추가 (EmbeddingPipeline 사용)"""
        if not self._initialize() or not pois:
            return 0
        
        try:
            ids = [poi.id for poi in pois]
            documents = [poi.raw_text for poi in pois]
            metadatas = [
                {
                    "name": poi.name,
                    "category": poi.category.value,
                    "description": poi.description,
                    "city": poi.city or "",
                    "address": poi.address or "",
                    "source": poi.source.value,
                    "source_url": poi.source_url or "",
                }
                for poi in pois
            ]
            
            # EmbeddingPipeline으로 배치 임베딩 생성
            embeddings = await self.embedding_pipeline.embed_documents(documents)
            
            self._collection.add(
                ids=ids,
                embeddings=embeddings,
                documents=documents,
                metadatas=metadatas
            )
            return len(pois)
            
        except Exception as e:
            print(f"Batch add POI error: {e}")
            return 0
    
    async def get_collection_size(self) -> int:
        """벡터 DB의 현재 데이터 개수 반환"""
        if not self._initialize():
            return 0
        
        try:
            return self._collection.count()
        except Exception:
            return 0
