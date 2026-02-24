"""
타입 기반 유사도 확인 스크립트

TypeEmbeddingStore를 사용하여 키워드 리스트로 유사 타입을 검색하고,
해당 타입에 연결된 POI를 전체 조회하는 스크립트입니다.

사용법:
    python scripts/check_type_similarity.py "맛집" "역사 유적지" "공원"
    python scripts/check_type_similarity.py "맛집" --top-types 5 --city "도쿄"
    python scripts/check_type_similarity.py "museum" "park" --metric cosine
"""

import asyncio
import argparse
import json
import math
import sys
import os
from collections import defaultdict
from typing import Callable, Dict, List, Set, Tuple

# 프로젝트 루트를 PYTHONPATH에 추가
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import chromadb
from chromadb.config import Settings

from app.core.Agents.Poi.VectorDB.VectorSearchAgent import (
    VectorSearchAgent,
    DEFAULT_PERSIST_DIR,
)
from app.core.Agents.Poi.VectorDB.EmbeddingPipeline.EmbeddingPipeline import EmbeddingPipeline
from app.core.Agents.Poi.VectorDB.TypeEmbeddingStore import (
    TypeEmbeddingStore,
    EXCLUDED_TYPES,
)


# ============================================================
# 유사도 계산 함수
# ============================================================

def cosine_similarity(a: List[float], b: List[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(x * x for x in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


def dot_product_similarity(a: List[float], b: List[float]) -> float:
    return sum(x * y for x, y in zip(a, b))


def euclidean_similarity(a: List[float], b: List[float]) -> float:
    dist = math.sqrt(sum((x - y) ** 2 for x, y in zip(a, b)))
    return 1.0 / (1.0 + dist)


SIMILARITY_METRICS: dict[str, Callable] = {
    "cosine": cosine_similarity,
    "dot": dot_product_similarity,
    "euclidean": euclidean_similarity,
}


def _score_indicator(score: float) -> str:
    if score >= 0.7:
        return "🟢"
    elif score >= 0.5:
        return "🟡"
    elif score >= 0.3:
        return "🟠"
    else:
        return "🔴"


async def check_type_similarity(
    keywords: List[str],
    city_filter: str | None = None,
    top_types: int = 5,
    top_pois: int | None = None,
    metric_name: str = "cosine",
):
    """
    키워드 리스트로 유사 타입을 검색하고, 연결된 POI의 유사도를 확인합니다.

    흐름:
    1. TypeEmbeddingStore에서 키워드별 유사 타입 검색
    2. 타입별 POI ID 수집 (중복 제거)
    3. POI VectorDB에서 전체 데이터 가져와서 직접 유사도 계산
    4. 결과 출력
    """
    similarity_fn = SIMILARITY_METRICS.get(metric_name)
    if similarity_fn is None:
        print(f"❌ 알 수 없는 메트릭: {metric_name}")
        print(f"   사용 가능: {', '.join(SIMILARITY_METRICS.keys())}")
        return

    # 1. 임베딩 파이프라인 초기화
    embedding_pipeline = EmbeddingPipeline()

    # 2. TypeEmbeddingStore 초기화
    type_store = TypeEmbeddingStore(
        embedding_pipeline=embedding_pipeline,
        persist_directory=DEFAULT_PERSIST_DIR,
    )
    await type_store._initialize()
    type_count = await type_store.get_collection_size()

    if type_count == 0:
        print("⚠️  TypeEmbeddingStore에 데이터가 없습니다.")
        print("   먼저 인덱스를 구축하세요.")
        return

    print(f"📦 TypeEmbeddingStore: {type_count}개 타입 등록")
    print(f"🔍 입력 키워드: {keywords}")
    print(f"📐 유사도 메트릭: {metric_name}")
    if city_filter:
        print(f"🏙️  도시 필터: {city_filter}")
    print()

    # ── 3. 키워드별 유사 타입 검색 ──
    separator = "=" * 100
    all_type_matches: Dict[str, float] = {}  # type_name → best score
    all_poi_ids: Dict[str, float] = {}  # poi_id → best type score

    for keyword in keywords:
        matches = await type_store.search_types(keyword, k=top_types)

        print(f"🔎 키워드: \"{keyword}\" → {len(matches)}개 타입 매칭")
        print("-" * 80)
        print(f"  {'타입':30s}  {'유사도':>8s}  {'POI 수':>8s}")
        print("-" * 80)

        for match in matches:
            indicator = _score_indicator(match.score)
            print(
                f"  {match.type_name:30s}  {indicator} {match.score:>6.4f}  "
                f"{len(match.poi_ids):>6d}개"
            )

            # 중복 타입 처리: 최고 스코어 유지
            existing = all_type_matches.get(match.type_name, 0.0)
            if match.score > existing:
                all_type_matches[match.type_name] = match.score

            # POI ID 수집
            for poi_id in match.poi_ids:
                existing_score = all_poi_ids.get(poi_id, 0.0)
                if match.score > existing_score:
                    all_poi_ids[poi_id] = match.score
        print()

    if not all_poi_ids:
        print("⚠️  매칭된 POI가 없습니다.")
        return

    # ── 4. 키워드 통합 요약 ──
    print(separator)
    print(f"📊 통합 타입 매칭 결과 (중복 제거)")
    print(separator)
    print(f"  총 매칭 타입: {len(all_type_matches)}개")
    print(f"  총 매칭 POI (ID 기준): {len(all_poi_ids)}개")
    print()

    print(f"  {'타입':30s}  {'최고 유사도':>10s}")
    print("-" * 50)
    for type_name, score in sorted(all_type_matches.items(), key=lambda x: -x[1]):
        indicator = _score_indicator(score)
        print(f"  {type_name:30s}  {indicator} {score:>7.4f}")
    print()

    # ── 5. POI VectorDB에서 직접 유사도 계산 ──
    # 키워드 결합 텍스트로 쿼리 임베딩 생성
    combined_query = ", ".join(keywords)
    query_embedding = await embedding_pipeline.embed_query(combined_query)

    # ChromaDB에서 전체 POI 데이터 로드
    client = chromadb.PersistentClient(
        path=DEFAULT_PERSIST_DIR,
        settings=Settings(anonymized_telemetry=False),
    )
    poi_collection = client.get_collection("poi_embeddings")

    # 매칭된 POI만 조회 (ID 기반)
    poi_id_list = list(all_poi_ids.keys())

    # 배치로 조회
    BATCH_SIZE = 100
    scored_items: List[Tuple[float, float, str, dict, str]] = []
    # (poi_sim, type_score, poi_id, metadata, document)

    for i in range(0, len(poi_id_list), BATCH_SIZE):
        batch_ids = poi_id_list[i : i + BATCH_SIZE]
        try:
            result = poi_collection.get(
                ids=batch_ids,
                include=["embeddings", "metadatas", "documents"],
            )
        except Exception:
            continue

        for j, poi_id in enumerate(result["ids"]):
            metadata = result["metadatas"][j]

            # 도시 필터
            if city_filter and metadata.get("city", "") != city_filter:
                continue

            embedding = result["embeddings"][j]
            if embedding is None:
                continue

            poi_sim = similarity_fn(query_embedding, embedding)
            type_score = all_poi_ids.get(poi_id, 0.0)
            document = result["documents"][j] if result["documents"] else ""

            scored_items.append((poi_sim, type_score, poi_id, metadata, document))

    # 유사도 순 정렬
    scored_items.sort(key=lambda x: x[0], reverse=True)

    if top_pois:
        scored_items = scored_items[:top_pois]

    if not scored_items:
        print("⚠️  검색 결과가 없습니다.")
        return

    # ── 6. 결과 출력 ──
    print(separator)
    print(f"{'순위':>4}  {'POI유사':>8}  {'타입유사':>8}  "
          f"{'카테고리':<12}  {'이름':<28}  {'도시':<8}  {'타입':<30}  {'설명'}")
    print(separator)

    for rank, (poi_sim, type_score, poi_id, metadata, document) in enumerate(scored_items, 1):
        name = (metadata.get("name", "(이름 없음)") or "(이름 없음)")[:26]
        category = (metadata.get("category", "-") or "-")[:10]
        city = (metadata.get("city", "-") or "-")[:6]

        # 타입 표시
        types_raw = metadata.get("types", "[]")
        try:
            types_list = json.loads(types_raw) if types_raw else []
        except (json.JSONDecodeError, TypeError):
            types_list = []
        # EXCLUDED_TYPES 제외, 첫 3개만
        display_types = [t for t in types_list if t not in EXCLUDED_TYPES][:3]
        types_str = ", ".join(display_types)[:28]

        desc_raw = metadata.get("description", "-") or "-"
        desc = (desc_raw[:30] + "...") if len(desc_raw) > 30 else desc_raw

        poi_indicator = _score_indicator(poi_sim)
        type_indicator = _score_indicator(type_score)

        print(
            f"{rank:>4}  {poi_indicator} {poi_sim:>6.4f}  {type_indicator} {type_score:>6.4f}  "
            f"{category:<12}  {name:<28}  {city:<8}  {types_str:<30}  {desc}"
        )

    print(separator)

    # ── 7. 통계 요약 ──
    poi_scores = [s[0] for s in scored_items]
    type_scores = [s[1] for s in scored_items]

    avg_poi = sum(poi_scores) / len(poi_scores) if poi_scores else 0
    avg_type = sum(type_scores) / len(type_scores) if type_scores else 0

    high_poi = sum(1 for s in poi_scores if s >= 0.7)
    mid_poi = sum(1 for s in poi_scores if 0.5 <= s < 0.7)
    low_poi = sum(1 for s in poi_scores if s < 0.5)

    displayed = len(scored_items) if not top_pois else f"{len(scored_items)} (top {top_pois})"

    print(f"\n📊 요약 ({displayed} / 매칭 전체 {len(all_poi_ids)}개)")
    print(f"   POI 유사도 (쿼리↔POI 임베딩):   평균 {avg_poi:.4f}")
    print(f"   타입 유사도 (키워드↔타입 임베딩): 평균 {avg_type:.4f}")
    print(f"   🟢 높음 (≥0.7): {high_poi}개")
    print(f"   🟡 보통 (0.5~0.7): {mid_poi}개")
    print(f"   🔴 낮음 (<0.5): {low_poi}개")


def main():
    parser = argparse.ArgumentParser(
        description="타입 기반 POI 유사도 확인 도구",
        epilog="예시: python scripts/check_type_similarity.py '맛집' '역사 유적지' --top-types 5",
    )
    parser.add_argument(
        "keywords", nargs="+", type=str,
        help="검색 키워드 리스트 (공백으로 구분)",
    )
    parser.add_argument(
        "--city", type=str, default=None,
        help="도시 필터 (예: 도쿄)",
    )
    parser.add_argument(
        "--top-types", type=int, default=5,
        help="키워드당 검색할 최대 타입 수 (기본: 5)",
    )
    parser.add_argument(
        "--top-pois", type=int, default=None,
        help="최종 출력할 상위 POI 수 (기본: 전체)",
    )
    parser.add_argument(
        "--metric", type=str, default="cosine",
        choices=list(SIMILARITY_METRICS.keys()),
        help="유사도 계산 방식 (기본: cosine)",
    )

    args = parser.parse_args()
    asyncio.run(
        check_type_similarity(
            keywords=args.keywords,
            city_filter=args.city,
            top_types=args.top_types,
            top_pois=args.top_pois,
            metric_name=args.metric,
        )
    )


if __name__ == "__main__":
    main()
