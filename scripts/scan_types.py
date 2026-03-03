"""
VectorDB에 저장된 POI들의 types 분석 스크립트

기존 ChromaDB에 저장된 모든 POI의 types 필드를 스캔하여:
1. unique type 목록 + 빈도수
2. type별 POI 수
3. 여행 관련/무관 타입 분류
결과를 콘솔 + JSON 파일로 출력합니다.
"""

import json
import os
import sys
from collections import Counter, defaultdict
from pathlib import Path

import chromadb
from chromadb.config import Settings

# 프로젝트 루트를 PYTHONPATH에 추가
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# ======= 설정 =======
VECTOR_DB_DIR = PROJECT_ROOT / "app" / "data" / "vector_db"
COLLECTION_NAME = "poi_embeddings"
OUTPUT_DIR = PROJECT_ROOT / "results"
OUTPUT_FILE = OUTPUT_DIR / "type_analysis.json"

# 여행 추천에 부적합한 타입 (제외 대상)
EXCLUDED_TYPES = {
    # Table B 메타 타입
    "geocode",
    # Transportation (대부분)
    "airport", "airstrip", "bus_station", "bus_stop",
    "ferry_terminal", "heliport", "international_airport",
    "light_rail_station", "park_and_ride", "subway_station",
    "taxi_stand", "train_station", "transit_depot",
    "transit_station", "truck_stop",
}


def main():
    """메인 실행 함수"""
    print(f"VectorDB 경로: {VECTOR_DB_DIR}")
    print(f"컬렉션 이름: {COLLECTION_NAME}")
    print("=" * 80)

    # 1. ChromaDB 연결
    if not VECTOR_DB_DIR.exists():
        print(f"❌ VectorDB 디렉토리가 존재하지 않습니다: {VECTOR_DB_DIR}")
        return

    client = chromadb.PersistentClient(
        path=str(VECTOR_DB_DIR),
        settings=Settings(anonymized_telemetry=False)
    )

    try:
        collection = client.get_collection(name=COLLECTION_NAME)
    except Exception as e:
        print(f"❌ 컬렉션을 찾을 수 없습니다: {e}")
        print(f"존재하는 컬렉션: {[c.name for c in client.list_collections()]}")
        return

    total_count = collection.count()
    print(f"총 POI 수: {total_count}")
    print()

    if total_count == 0:
        print("⚠️ 컬렉션에 데이터가 없습니다.")
        return

    # 2. 모든 메타데이터 가져오기 (배치로)
    BATCH_SIZE = 1000
    all_type_counter = Counter()       # type → 전체 빈도
    type_to_pois = defaultdict(list)   # type → [poi_id, ...]
    poi_type_counts = []               # POI별 타입 수 리스트
    pois_without_types = 0

    for offset in range(0, total_count, BATCH_SIZE):
        results = collection.get(
            offset=offset,
            limit=BATCH_SIZE,
            include=["metadatas"]
        )
        ids = results["ids"]
        metadatas = results["metadatas"]

        for doc_id, metadata in zip(ids, metadatas):
            types_raw = metadata.get("types", "[]")
            try:
                types = json.loads(types_raw) if types_raw else []
            except (json.JSONDecodeError, TypeError):
                types = []

            if not types:
                pois_without_types += 1
                poi_type_counts.append(0)
                continue

            poi_type_counts.append(len(types))
            for t in types:
                all_type_counter[t] += 1
                type_to_pois[t].append(doc_id)

    # 3. 분석 결과 출력
    print(f"📊 타입 분석 결과")
    print("=" * 80)
    print(f"총 POI 수: {total_count}")
    print(f"타입이 없는 POI 수: {pois_without_types}")
    print(f"전체 unique 타입 수: {len(all_type_counter)}")
    print()

    if poi_type_counts:
        avg_types = sum(poi_type_counts) / len(poi_type_counts)
        max_types = max(poi_type_counts)
        print(f"POI당 평균 타입 수: {avg_types:.1f}")
        print(f"POI당 최대 타입 수: {max_types}")
        print()

    # 여행 관련 vs 제외 타입 분류
    travel_types = {}
    excluded_found = {}
    for type_name, count in all_type_counter.most_common():
        if type_name in EXCLUDED_TYPES:
            excluded_found[type_name] = {
                "count": count,
                "poi_count": len(type_to_pois[type_name])
            }
        else:
            travel_types[type_name] = {
                "count": count,
                "poi_count": len(type_to_pois[type_name])
            }

    print(f"✅ 여행 관련 타입: {len(travel_types)}개")
    print("-" * 60)
    for type_name, info in sorted(travel_types.items(), key=lambda x: -x[1]["count"]):
        print(f"  {type_name:40s}  빈도: {info['count']:4d}  POI: {info['poi_count']:4d}개")

    print()
    print(f"❌ 제외 타입 (EXCLUDED_TYPES에 해당): {len(excluded_found)}개")
    print("-" * 60)
    for type_name, info in sorted(excluded_found.items(), key=lambda x: -x[1]["count"]):
        print(f"  {type_name:40s}  빈도: {info['count']:4d}  POI: {info['poi_count']:4d}개")

    # 4. JSON 저장
    output = {
        "summary": {
            "total_pois": total_count,
            "pois_without_types": pois_without_types,
            "total_unique_types": len(all_type_counter),
            "travel_related_types": len(travel_types),
            "excluded_types": len(excluded_found),
            "avg_types_per_poi": round(avg_types, 2) if poi_type_counts else 0,
        },
        "travel_types": {
            k: v for k, v in sorted(travel_types.items(), key=lambda x: -x[1]["count"])
        },
        "excluded_types_found": {
            k: v for k, v in sorted(excluded_found.items(), key=lambda x: -x[1]["count"])
        },
        "all_types_frequency": dict(all_type_counter.most_common()),
    }

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print()
    print(f"💾 결과 저장: {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
