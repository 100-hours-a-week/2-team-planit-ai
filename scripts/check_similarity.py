"""
벡터 DB의 모든 데이터에 대해 입력 텍스트와의 유사도를 확인하는 스크립트

collection.get()으로 전체 데이터를 가져온 뒤 직접 유사도를 계산하여
HNSW 근사 검색에 의한 누락 없이 정확한 전체 비교를 수행합니다.

사용법:
    python scripts/check_similarity.py "입력 텍스트"
    python scripts/check_similarity.py "입력 텍스트" --city "오사카"
    python scripts/check_similarity.py "입력 텍스트" --top 20
    python scripts/check_similarity.py "입력 텍스트" --metric euclidean
"""
import asyncio
import argparse
import sys
import os
import math
from typing import Callable, List, Tuple

# 프로젝트 루트를 PYTHONPATH에 추가
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import chromadb
from chromadb.config import Settings

from app.core.Agents.Poi.VectorDB.VectorSearchAgent import (
    VectorSearchAgent,
    DEFAULT_PERSIST_DIR,
)
from app.core.Agents.Poi.VectorDB.EmbeddingPipeline.EmbeddingPipeline import EmbeddingPipeline


# ============================================================
# 유사도 계산 함수 (교체 가능)
# 입력: (vec_a, vec_b) -> float (높을수록 유사)
# ============================================================

def cosine_similarity(a: List[float], b: List[float]) -> float:
    """코사인 유사도 (ChromaDB 기본 메트릭과 동일)"""
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(x * x for x in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


def dot_product_similarity(a: List[float], b: List[float]) -> float:
    """내적(dot product) 유사도"""
    return sum(x * y for x, y in zip(a, b))


def euclidean_similarity(a: List[float], b: List[float]) -> float:
    """유클리드 거리 기반 유사도 (거리를 0~1 점수로 변환)"""
    dist = math.sqrt(sum((x - y) ** 2 for x, y in zip(a, b)))
    return 1.0 / (1.0 + dist)


# 메트릭 이름 → 함수 매핑
SIMILARITY_METRICS: dict[str, Callable] = {
    "cosine": cosine_similarity,
    "dot": dot_product_similarity,
    "euclidean": euclidean_similarity,
}


async def check_similarity(
    query_text: str,
    city_filter: str | None = None,
    top_k: int | None = None,
    metric_name: str = "cosine",
):
    """벡터 DB 전체 데이터를 가져와 직접 유사도를 계산하여 출력"""

    similarity_fn = SIMILARITY_METRICS.get(metric_name)
    if similarity_fn is None:
        print(f"❌ 알 수 없는 메트릭: {metric_name}")
        print(f"   사용 가능: {', '.join(SIMILARITY_METRICS.keys())}")
        return

    # 1. 임베딩 파이프라인 초기화 & 쿼리 임베딩 생성
    embedding_pipeline = EmbeddingPipeline()
    query_embedding = await embedding_pipeline.embed_query(query_text)

    # 2. ChromaDB에서 전체 데이터 직접 가져오기 (HNSW 우회)
    client = chromadb.PersistentClient(
        path=DEFAULT_PERSIST_DIR,
        settings=Settings(anonymized_telemetry=False),
    )
    collection = client.get_collection("poi_embeddings")
    total_count = collection.count()

    if total_count == 0:
        print("⚠️  벡터 DB에 저장된 데이터가 없습니다.")
        return

    # 전체 데이터 조회 (임베딩 포함)
    data = collection.get(include=["embeddings", "metadatas", "documents"])

    print(f"📦 벡터 DB 총 데이터 수: {total_count}개")
    print(f"🔍 검색 쿼리: \"{query_text}\"")
    print(f"📐 유사도 메트릭: {metric_name}")
    if city_filter:
        print(f"🏙️  도시 필터: {city_filter}")
    print()

    # 3. 전체 데이터에 대해 유사도 직접 계산
    scored_items: List[Tuple[float, int]] = []  # (score, index)

    for i, doc_id in enumerate(data["ids"]):
        metadata = data["metadatas"][i]
        embedding = data["embeddings"][i]

        # 도시 필터 적용
        if city_filter and metadata.get("city", "") != city_filter:
            continue

        if embedding is None:
            continue

        score = similarity_fn(query_embedding, embedding)
        scored_items.append((score, i))

    # 유사도 순 정렬
    scored_items.sort(key=lambda x: x[0], reverse=True)

    # top_k 적용
    if top_k:
        scored_items = scored_items[:top_k]

    if not scored_items:
        print("⚠️  검색 결과가 없습니다.")
        return

    # 4. 결과 출력
    separator = "=" * 100
    print(separator)
    print(f"{'순위':>4}  {'유사도':>8}  {'카테고리':<12}  {'이름':<30}  {'도시':<10}  {'설명'}")
    print(separator)

    for rank, (score, idx) in enumerate(scored_items, 1):
        metadata = data["metadatas"][idx]
        name = (metadata.get("name", "(이름 없음)") or "(이름 없음)")[:28]
        category = (metadata.get("category", "-") or "-")[:10]
        city = (metadata.get("city", "-") or "-")[:8]
        desc_raw = metadata.get("description", "-") or "-"
        desc = (desc_raw[:40] + "...") if len(desc_raw) > 40 else desc_raw

        if score >= 0.7:
            indicator = "🟢"
        elif score >= 0.5:
            indicator = "🟡"
        elif score >= 0.3:
            indicator = "🟠"
        else:
            indicator = "🔴"

        print(f"{rank:>4}  {indicator} {score:>6.4f}  {category:<12}  {name:<30}  {city:<10}  {desc}")

    print(separator)

    # 5. 통계 요약
    scores = [s for s, _ in scored_items]
    avg_score = sum(scores) / len(scores) if scores else 0
    high_count = sum(1 for s in scores if s >= 0.7)
    mid_count = sum(1 for s in scores if 0.5 <= s < 0.7)
    low_count = sum(1 for s in scores if s < 0.5)

    filtered_total = len(scored_items) if not top_k else f"{len(scored_items)} (전체 중 top {top_k})"
    print(f"\n📊 요약 ({filtered_total} / DB 전체 {total_count}개)")
    print(f"   평균 유사도: {avg_score:.4f}")
    print(f"   🟢 높음 (≥0.7): {high_count}개")
    print(f"   🟡 보통 (0.5~0.7): {mid_count}개")
    print(f"   🔴 낮음 (<0.5): {low_count}개")


def main():
    parser = argparse.ArgumentParser(description="벡터 DB 유사도 검색 도구")
    parser.add_argument("query", type=str, help="유사도를 계산할 입력 텍스트")
    parser.add_argument("--city", type=str, default=None, help="도시 필터 (예: 오사카)")
    parser.add_argument("--top", type=int, default=None, help="상위 N개 결과 출력 (기본: 전체)")
    parser.add_argument(
        "--metric",
        type=str,
        default="cosine",
        choices=list(SIMILARITY_METRICS.keys()),
        help="유사도 계산 방식 (기본: cosine)",
    )

    args = parser.parse_args()
    asyncio.run(check_similarity(args.query, args.city, args.top, args.metric))


if __name__ == "__main__":
    main()
