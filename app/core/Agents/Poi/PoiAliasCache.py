"""
POI 별칭 캐시 (SQLite 영속성)

같은 장소가 다른 이름으로 등장하는 경우를 감지하기 위한 별칭 테이블.
(name, city) → google_place_id 매핑을 저장하여
Google Maps API 중복 호출을 방지합니다.
"""
import asyncio
import logging
import re
import sqlite3
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

DEFAULT_DB_PATH = str(
    Path(__file__).resolve().parent.parent.parent.parent / "data" / "poi_alias_cache.db"
)


class PoiAliasCache:
    """POI 이름 → Google Place ID 별칭 캐시 (SQLite 영속성)"""

    def __init__(self, db_path: Optional[str] = None):
        self._db_path = db_path or DEFAULT_DB_PATH
        self._lock = asyncio.Lock()
        self._init_db()

    def _init_db(self) -> None:
        """테이블 생성 (없으면)"""
        Path(self._db_path).parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self._db_path)
        try:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS poi_alias (
                    name TEXT NOT NULL,
                    city TEXT NOT NULL,
                    google_place_id TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (name, city)
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_place_id
                ON poi_alias(google_place_id)
            """)
            conn.commit()
        finally:
            conn.close()

    @staticmethod
    def normalize_name(name: str) -> str:
        """이름 정규화: strip, lower, 연속 공백 제거"""
        if not name:
            return ""
        normalized = re.sub(r'\s+', ' ', name.strip())
        return normalized.lower()

    async def find_by_name(self, name: str, city: str) -> Optional[str]:
        """(name, city)로 google_place_id 조회. 없으면 None."""
        normalized = self.normalize_name(name)
        if not normalized:
            return None

        async with self._lock:
            return await asyncio.to_thread(
                self._find_by_name_sync, normalized, city
            )

    def _find_by_name_sync(self, name: str, city: str) -> Optional[str]:
        conn = sqlite3.connect(self._db_path)
        try:
            cursor = conn.execute(
                "SELECT google_place_id FROM poi_alias WHERE name = ? AND city = ?",
                (name, city)
            )
            row = cursor.fetchone()
            return row[0] if row else None
        finally:
            conn.close()

    async def has_place_id(self, place_id: str) -> bool:
        """google_place_id가 이미 등록되어 있는지 확인."""
        if not place_id:
            return False

        async with self._lock:
            return await asyncio.to_thread(
                self._has_place_id_sync, place_id
            )

    def _has_place_id_sync(self, place_id: str) -> bool:
        conn = sqlite3.connect(self._db_path)
        try:
            cursor = conn.execute(
                "SELECT 1 FROM poi_alias WHERE google_place_id = ? LIMIT 1",
                (place_id,)
            )
            return cursor.fetchone() is not None
        finally:
            conn.close()

    async def add(self, name: str, city: str, place_id: str) -> None:
        """별칭 등록. 이미 존재하면 무시."""
        normalized = self.normalize_name(name)
        if not normalized or not place_id:
            return

        async with self._lock:
            await asyncio.to_thread(
                self._add_sync, normalized, city, place_id
            )

    def _add_sync(self, name: str, city: str, place_id: str) -> None:
        conn = sqlite3.connect(self._db_path)
        try:
            conn.execute(
                "INSERT OR IGNORE INTO poi_alias (name, city, google_place_id) VALUES (?, ?, ?)",
                (name, city, place_id)
            )
            conn.commit()
        finally:
            conn.close()
