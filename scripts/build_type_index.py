"""
TypeEmbeddingStore 인덱스 구축 스크립트

기존 VectorDB(poi_embeddings)의 모든 POI 데이터를 읽어
type_embeddings 컬렉션에 타입별 인덱스를 구축합니다.

사용법:
    python scripts/build_type_index.py
    python scripts/build_type_index.py --rebuild
"""

import asyncio
import argparse
import json
import sys
import os
from typing import List

# 프로젝트 루트를 PYTHONPATH에 추가
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import chromadb
from chromadb.config import Settings

from app.core.Agents.Poi.VectorDB.VectorSearchAgent import (
    VectorSearchAgent,
    DEFAULT_PERSIST_DIR,
)
from app.core.Agents.Poi.VectorDB.EmbeddingPipeline.EmbeddingPipeline import EmbeddingPipeline
from app.core.Agents.Poi.VectorDB.TypeEmbeddingStore import TypeEmbeddingStore
from app.core.models.PoiAgentDataclass.poi import (
    PoiData,
    PoiCategory,
    PoiSource,
    OpeningHours,
)


async def build_type_index(rebuild: bool = False):
    """기존 poi_embeddings → type_embeddings 인덱스 구축"""

    print("=" * 70)
    print("  📦 TypeEmbeddingStore 인덱스 구축")
    print("=" * 70)
    print(f"VectorDB 경로: {DEFAULT_PERSIST_DIR}")
    print()

    # 1. ChromaDB에서 기존 POI 데이터 전체 로드
    client = chromadb.PersistentClient(
        path=DEFAULT_PERSIST_DIR,
        settings=Settings(anonymized_telemetry=False),
    )

    try:
        poi_collection = client.get_collection("poi_embeddings")
    except Exception as e:
        print(f"❌ poi_embeddings 컬렉션을 찾을 수 없습니다: {e}")
        return

    total_count = poi_collection.count()
    print(f"기존 POI 수: {total_count}개")

    if total_count == 0:
        print("⚠️  POI 데이터가 없습니다.")
        return

    # 2. 기존 type_embeddings 컬렉션 확인/삭제
    if rebuild:
        try:
            client.delete_collection("type_embeddings")
            print("🗑️  기존 type_embeddings 컬렉션 삭제 완료")
        except Exception:
            pass

    # 3. 전체 POI 데이터를 PoiData로 변환
    print("📥 POI 데이터 로딩 중...")
    BATCH_SIZE = 500
    pois: List[PoiData] = []

    for offset in range(0, total_count, BATCH_SIZE):
        result = poi_collection.get(
            offset=offset,
            limit=BATCH_SIZE,
            include=["metadatas", "documents"],
        )

        for doc_id, metadata, document in zip(
            result["ids"], result["metadatas"], result["documents"]
        ):
            poi = VectorSearchAgent._reconstruct_poi_data(doc_id, metadata, document)
            pois.append(poi)

    print(f"POI 로딩 완료: {len(pois)}개")

    # 4. TypeEmbeddingStore에 인덱스 구축
    embedding_pipeline = EmbeddingPipeline()
    type_store = TypeEmbeddingStore(
        embedding_pipeline=embedding_pipeline,
        persist_directory=DEFAULT_PERSIST_DIR,
    )

    print("🔨 타입 인덱스 구축 중...")
    type_count = await type_store.build_index_from_pois(pois)

    print()
    print("=" * 70)
    print(f"✅ 인덱스 구축 완료: {type_count}개 타입 등록")
    print("=" * 70)

    # 5. 구축 결과 요약
    all_types = await type_store.get_all_types()
    print(f"\n등록된 타입 목록 ({len(all_types)}개):")
    for t in sorted(all_types):
        poi_ids = await type_store.get_poi_ids_by_type(t)
        print(f"  {t:40s}  POI: {len(poi_ids):4d}개")


def main():
    parser = argparse.ArgumentParser(
        description="TypeEmbeddingStore 인덱스 구축",
    )
    parser.add_argument(
        "--rebuild", action="store_true",
        help="기존 type_embeddings 컬렉션을 삭제하고 새로 구축",
    )

    args = parser.parse_args()
    asyncio.run(build_type_index(rebuild=args.rebuild))


if __name__ == "__main__":
    main()
