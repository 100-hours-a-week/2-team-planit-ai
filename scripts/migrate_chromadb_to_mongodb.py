"""
ChromaDB -> MongoDB Vector Search 마이그레이션 스크립트

Usage:
    python scripts/migrate_chromadb_to_mongodb.py
    python scripts/migrate_chromadb_to_mongodb.py --dry-run
    python scripts/migrate_chromadb_to_mongodb.py --chromadb-path ./data/vector_db --batch-size 200
"""
import argparse
import os
import sys

import chromadb
from chromadb.config import Settings as ChromaSettings
from pymongo import MongoClient, UpdateOne
from pymongo.operations import SearchIndexModel

# 프로젝트 루트를 sys.path에 추가
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.config import settings

DEFAULT_CHROMADB_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "data", "vector_db"
)


def load_chromadb(chromadb_path: str, collection_name: str):
    """ChromaDB에서 전체 데이터 로드"""
    client = chromadb.PersistentClient(
        path=chromadb_path,
        settings=ChromaSettings(anonymized_telemetry=False),
    )
    collection = client.get_collection(name=collection_name)
    total = collection.count()
    print(f"ChromaDB: {total}개 문서 발견 (collection={collection_name})")

    if total == 0:
        return [], [], [], []

    data = collection.get(
        include=["embeddings", "documents", "metadatas"],
    )
    return data["ids"], data["embeddings"], data["documents"], data["metadatas"]


def migrate(
    chromadb_path: str,
    chromadb_collection: str,
    mongodb_uri: str,
    mongodb_db: str,
    mongodb_collection: str,
    index_name: str,
    batch_size: int,
    dry_run: bool,
):
    """메인 마이그레이션 로직"""
    # 1. ChromaDB 로드
    ids, embeddings, documents, metadatas = load_chromadb(
        chromadb_path, chromadb_collection
    )
    total = len(ids)
    if total == 0:
        print("마이그레이션할 데이터가 없습니다.")
        return

    if dry_run:
        print(f"\n[DRY RUN] {total}개 문서 마이그레이션 예정")
        print(f"  ChromaDB: {chromadb_path} / {chromadb_collection}")
        print(f"  MongoDB:  {mongodb_uri} / {mongodb_db}.{mongodb_collection}")
        print(f"\n샘플 문서 (첫 3개):")
        for i in range(min(3, total)):
            print(f"  [{i}] id={ids[i]}, name={metadatas[i].get('name', 'N/A')}")
        return

    # 2. MongoDB 연결
    client = MongoClient(mongodb_uri)
    try:
        db = client[mongodb_db]
        collection = db[mongodb_collection]
        print(f"MongoDB 연결 완료: {mongodb_db}.{mongodb_collection}")

        # 3. 배치 upsert
        success_count = 0
        fail_count = 0

        for batch_start in range(0, total, batch_size):
            batch_end = min(batch_start + batch_size, total)
            operations = []

            for i in range(batch_start, batch_end):
                doc = {
                    "embedding": embeddings[i],
                    "document": documents[i] if documents[i] else "",
                    "metadata": metadatas[i] if metadatas[i] else {},
                }
                operations.append(
                    UpdateOne(
                        {"_id": ids[i]},
                        {"$set": doc},
                        upsert=True,
                    )
                )

            try:
                result = collection.bulk_write(operations)
                batch_count = result.upserted_count + result.modified_count
                success_count += batch_count
                print(
                    f"  배치 {batch_start + 1}~{batch_end}: "
                    f"{batch_count}개 처리"
                )
            except Exception as e:
                fail_count += batch_end - batch_start
                print(f"  배치 {batch_start + 1}~{batch_end}: 오류 - {e}")

        # 4. 벡터 인덱스 생성 (확인과 생성을 분리)
        print("\n벡터 인덱스 확인 중...")
        index_exists = False
        try:
            existing_indexes = list(collection.list_search_indexes())
            index_exists = any(idx.get("name") == index_name for idx in existing_indexes)
        except Exception as e:
            print(f"  인덱스 목록 조회 실패 (인덱스 생성 시도): {e}")

        if not index_exists and embeddings:
            try:
                num_dimensions = len(embeddings[0])
                index_def = {
                    "fields": [
                        {
                            "type": "vector",
                            "path": "embedding",
                            "numDimensions": num_dimensions,
                            "similarity": "cosine",
                        },
                        {"type": "filter", "path": "metadata.city"},
                        {"type": "filter", "path": "metadata.name"},
                        {"type": "filter", "path": "metadata.google_place_id"},
                    ]
                }
                collection.create_search_index(
                    SearchIndexModel(
                        definition=index_def,
                        name=index_name,
                        type="vectorSearch",
                    )
                )
                print(f"벡터 인덱스 '{index_name}' 생성 완료 (dimensions={num_dimensions})")
            except Exception as e:
                print(f"  벡터 인덱스 생성 오류: {e}")
        elif index_exists:
            print(f"벡터 인덱스 '{index_name}' 이미 존재")

        # 5. 검증
        mongo_count = collection.count_documents({})
        print(f"\n=== 마이그레이션 결과 ===")
        print(f"  ChromaDB 원본: {total}개")
        print(f"  MongoDB 저장:  {mongo_count}개")
        print(f"  성공: {success_count}개, 실패: {fail_count}개")

        # 샘플 비교
        if total > 0:
            sample_id = ids[0]
            mongo_doc = collection.find_one({"_id": sample_id})
            if mongo_doc:
                print(f"\n  샘플 검증 (id={sample_id}):")
                print(f"    name: {mongo_doc['metadata'].get('name', 'N/A')}")
                print(f"    embedding 차원: {len(mongo_doc.get('embedding', []))}")
                print(f"    document 길이: {len(mongo_doc.get('document', ''))}")
    finally:
        client.close()


def main():
    parser = argparse.ArgumentParser(
        description="ChromaDB -> MongoDB Vector Search 마이그레이션"
    )
    parser.add_argument(
        "--chromadb-path",
        default=DEFAULT_CHROMADB_PATH,
        help=f"ChromaDB 저장 경로 (default: {DEFAULT_CHROMADB_PATH})",
    )
    parser.add_argument(
        "--chromadb-collection",
        default="poi_embeddings",
        help="ChromaDB 컬렉션 이름 (default: poi_embeddings)",
    )
    parser.add_argument(
        "--mongodb-uri",
        default=None,
        help="MongoDB URI (default: settings.mongodb_uri)",
    )
    parser.add_argument(
        "--mongodb-db",
        default=None,
        help="MongoDB DB 이름 (default: settings.mongodb_db_name)",
    )
    parser.add_argument(
        "--mongodb-collection",
        default=None,
        help="MongoDB 컬렉션 이름 (default: settings.mongodb_vector_collection)",
    )
    parser.add_argument(
        "--index-name",
        default=None,
        help="벡터 인덱스 이름 (default: settings.mongodb_vector_index)",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=100,
        help="배치 크기 (default: 100)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="실제 쓰기 없이 미리보기",
    )

    args = parser.parse_args()

    migrate(
        chromadb_path=args.chromadb_path,
        chromadb_collection=args.chromadb_collection,
        mongodb_uri=args.mongodb_uri or settings.mongodb_uri,
        mongodb_db=args.mongodb_db or settings.mongodb_db_name,
        mongodb_collection=args.mongodb_collection or settings.mongodb_vector_collection,
        index_name=args.index_name or settings.mongodb_vector_index,
        batch_size=args.batch_size,
        dry_run=args.dry_run,
    )


if __name__ == "__main__":
    main()
