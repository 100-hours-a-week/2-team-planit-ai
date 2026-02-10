"""
Transfer 캐시 (SQLite 영속성)

POI 간 이동 정보(Transfer)를 SQLite에 저장하여
Google Maps API 중복 호출을 방지하고 프로세스 재시작 시에도 캐시를 유지합니다.
"""
import asyncio
import logging
import sqlite3
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from app.core.models.ItineraryAgentDataclass.itinerary import Transfer, TravelMode

logger = logging.getLogger(__name__)

DEFAULT_DB_PATH = str(
    Path(__file__).resolve().parent.parent.parent.parent / "data" / "transfer_cache.db"
)


class TransferCache:
    """POI 간 이동 정보 캐시 (SQLite 영속성)"""

    DEFAULT_DB_PATH = DEFAULT_DB_PATH

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
                CREATE TABLE IF NOT EXISTS transfer_cache (
                    from_poi_id     TEXT    NOT NULL,
                    to_poi_id       TEXT    NOT NULL,
                    travel_mode     TEXT    NOT NULL,
                    duration_minutes INTEGER NOT NULL DEFAULT 0,
                    distance_km     REAL    NOT NULL DEFAULT 0.0,
                    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (from_poi_id, to_poi_id, travel_mode)
                )
            """)
            conn.commit()
        finally:
            conn.close()

    # ------------------------------------------------------------------
    # 단건 조회 / 저장
    # ------------------------------------------------------------------

    async def get(
        self, from_id: str, to_id: str, mode: TravelMode
    ) -> Optional[Transfer]:
        """캐시에서 Transfer 조회. 없으면 None."""
        async with self._lock:
            return await asyncio.to_thread(
                self._get_sync, from_id, to_id, mode.value
            )

    def _get_sync(
        self, from_id: str, to_id: str, mode_value: str
    ) -> Optional[Transfer]:
        conn = sqlite3.connect(self._db_path)
        try:
            cursor = conn.execute(
                "SELECT from_poi_id, to_poi_id, travel_mode, duration_minutes, distance_km "
                "FROM transfer_cache WHERE from_poi_id = ? AND to_poi_id = ? AND travel_mode = ?",
                (from_id, to_id, mode_value),
            )
            row = cursor.fetchone()
            if row is None:
                return None
            return Transfer(
                from_poi_id=row[0],
                to_poi_id=row[1],
                travel_mode=TravelMode(row[2]),
                duration_minutes=row[3],
                distance_km=row[4],
            )
        finally:
            conn.close()

    async def put(self, transfer: Transfer) -> None:
        """Transfer를 캐시에 저장 (INSERT OR REPLACE)."""
        async with self._lock:
            await asyncio.to_thread(self._put_sync, transfer)

    def _put_sync(self, transfer: Transfer) -> None:
        conn = sqlite3.connect(self._db_path)
        try:
            conn.execute(
                "INSERT OR REPLACE INTO transfer_cache "
                "(from_poi_id, to_poi_id, travel_mode, duration_minutes, distance_km) "
                "VALUES (?, ?, ?, ?, ?)",
                (
                    transfer.from_poi_id,
                    transfer.to_poi_id,
                    transfer.travel_mode.value,
                    transfer.duration_minutes,
                    transfer.distance_km,
                ),
            )
            conn.commit()
        finally:
            conn.close()

    # ------------------------------------------------------------------
    # 배치 조회 / 저장
    # ------------------------------------------------------------------

    async def get_batch(
        self, pairs: List[Tuple[str, str, TravelMode]]
    ) -> Dict[str, Transfer]:
        """다건 조회. 키: '{from_id}|{to_id}|{mode.value}', 값: Transfer"""
        async with self._lock:
            return await asyncio.to_thread(self._get_batch_sync, pairs)

    def _get_batch_sync(
        self, pairs: List[Tuple[str, str, TravelMode]]
    ) -> Dict[str, Transfer]:
        result: Dict[str, Transfer] = {}
        conn = sqlite3.connect(self._db_path)
        try:
            for from_id, to_id, mode in pairs:
                cursor = conn.execute(
                    "SELECT from_poi_id, to_poi_id, travel_mode, duration_minutes, distance_km "
                    "FROM transfer_cache WHERE from_poi_id = ? AND to_poi_id = ? AND travel_mode = ?",
                    (from_id, to_id, mode.value),
                )
                row = cursor.fetchone()
                if row is not None:
                    key = f"{from_id}|{to_id}|{mode.value}"
                    result[key] = Transfer(
                        from_poi_id=row[0],
                        to_poi_id=row[1],
                        travel_mode=TravelMode(row[2]),
                        duration_minutes=row[3],
                        distance_km=row[4],
                    )
            return result
        finally:
            conn.close()

    async def put_batch(self, transfers: List[Transfer]) -> None:
        """다건 저장 (INSERT OR REPLACE)."""
        if not transfers:
            return
        async with self._lock:
            await asyncio.to_thread(self._put_batch_sync, transfers)

    def _put_batch_sync(self, transfers: List[Transfer]) -> None:
        conn = sqlite3.connect(self._db_path)
        try:
            conn.executemany(
                "INSERT OR REPLACE INTO transfer_cache "
                "(from_poi_id, to_poi_id, travel_mode, duration_minutes, distance_km) "
                "VALUES (?, ?, ?, ?, ?)",
                [
                    (
                        t.from_poi_id,
                        t.to_poi_id,
                        t.travel_mode.value,
                        t.duration_minutes,
                        t.distance_km,
                    )
                    for t in transfers
                ],
            )
            conn.commit()
        finally:
            conn.close()

    # ------------------------------------------------------------------
    # 유틸리티
    # ------------------------------------------------------------------

    async def clear(self) -> None:
        """전체 삭제."""
        async with self._lock:
            await asyncio.to_thread(self._clear_sync)

    def _clear_sync(self) -> None:
        conn = sqlite3.connect(self._db_path)
        try:
            conn.execute("DELETE FROM transfer_cache")
            conn.commit()
        finally:
            conn.close()

    async def size(self) -> int:
        """건수 조회."""
        async with self._lock:
            return await asyncio.to_thread(self._size_sync)

    def _size_sync(self) -> int:
        conn = sqlite3.connect(self._db_path)
        try:
            cursor = conn.execute("SELECT COUNT(*) FROM transfer_cache")
            return cursor.fetchone()[0]
        finally:
            conn.close()
