import json
import logging
import sqlite3
from pathlib import Path
from typing import Dict, List, Optional

from app.core.models.PoiAgentDataclass.poi import PoiSearchResult

logger = logging.getLogger(__name__)

# 기본 DB 경로
_DEFAULT_DB_PATH = str(
    Path(__file__).resolve().parent.parent.parent.parent.parent / "data" / "url_cache.db"
)


class UrlCache:
    """
    URL 추출 결과 캐시 - SQLite 기반 (파일 영속성 + 인메모리 속도)

    웹 페이지에서 POI를 추출한 결과를 캐싱하여
    동일 URL에 대한 Jina Reader + LangExtractor 재호출을 방지합니다.
    여행지(destination) 컬럼으로 인덱싱되어 빠른 조회가 가능합니다.
    """

    def __init__(self, db_path: Optional[str] = None):
        """
        Args:
            db_path: SQLite DB 파일 경로. None이면 app/data/url_cache.db 사용.
        """
        self.db_path = db_path or _DEFAULT_DB_PATH
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self.db_path)
        self._conn.execute("PRAGMA journal_mode=WAL")  # 동시 읽기 성능 향상
        self._create_table()

    def _create_table(self):
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS url_cache (
                url TEXT NOT NULL,
                destination TEXT NOT NULL DEFAULT '',
                results_json TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (url, destination)
            )
        """)
        self._conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_url_cache_destination ON url_cache(destination)"
        )
        self._conn.commit()

    def get(self, url: str, destination: str = "") -> Optional[List[PoiSearchResult]]:
        """캐시에서 URL의 추출 결과를 조회합니다."""
        cursor = self._conn.execute(
            "SELECT results_json FROM url_cache WHERE url = ? AND destination = ?",
            (url, destination),
        )
        row = cursor.fetchone()
        if row is None:
            logger.debug(f"[UrlCache] MISS - url={url}, destination={destination}")
            return None
        try:
            results = self._deserialize(row[0])
            logger.info(f"[UrlCache] HIT - url={url}, destination={destination}, POI {len(results)}개 반환")
            return results
        except Exception as e:
            logger.warning(f"[UrlCache] 역직렬화 실패 (url={url}): {e}")
            return None

    def put(self, url: str, destination: str, results: List[PoiSearchResult]) -> None:
        """추출 결과를 캐시에 저장합니다."""
        try:
            results_json = self._serialize(results)
            self._conn.execute(
                "INSERT OR REPLACE INTO url_cache (url, destination, results_json) VALUES (?, ?, ?)",
                (url, destination, results_json),
            )
            self._conn.commit()
            logger.info(f"[UrlCache] STORE - url={url}, destination={destination}, POI {len(results)}개 저장")
        except Exception as e:
            logger.error(f"[UrlCache] 저장 실패 (url={url}): {e}")

    def has(self, url: str, destination: str = "") -> bool:
        """URL이 캐시에 존재하는지 확인합니다."""
        cursor = self._conn.execute(
            "SELECT 1 FROM url_cache WHERE url = ? AND destination = ?",
            (url, destination),
        )
        return cursor.fetchone() is not None

    def get_by_destination(self, destination: str) -> Dict[str, List[PoiSearchResult]]:
        """특정 여행지의 모든 캐시된 URL과 결과를 조회합니다."""
        cursor = self._conn.execute(
            "SELECT url, results_json FROM url_cache WHERE destination = ?",
            (destination,),
        )
        result = {}
        for url, results_json in cursor.fetchall():
            try:
                result[url] = self._deserialize(results_json)
            except Exception:
                continue
        total_pois = sum(len(v) for v in result.values())
        logger.info(f"[UrlCache] LOOKUP BY DESTINATION - destination={destination}, URL {len(result)}개, POI 총 {total_pois}개")
        return result

    def _serialize(self, results: List[PoiSearchResult]) -> str:
        return json.dumps(
            [r.model_dump(mode="json") for r in results], ensure_ascii=False
        )

    def _deserialize(self, json_str: str) -> List[PoiSearchResult]:
        data = json.loads(json_str)
        return [PoiSearchResult(**item) for item in data]

    def close(self):
        self._conn.close()
