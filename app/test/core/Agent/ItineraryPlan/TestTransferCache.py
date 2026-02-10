"""
TransferCache 단위 테스트
"""
import asyncio

import pytest

from app.core.Agents.ItineraryPlan.TransferCache import TransferCache
from app.core.models.ItineraryAgentDataclass.itinerary import Transfer, TravelMode


class TestTransferCacheUnit:
    """TransferCache 단위 테스트"""

    @pytest.fixture
    def cache(self, tmp_path):
        """임시 디렉토리에 SQLite DB를 생성하는 캐시"""
        db_path = str(tmp_path / "test_transfer.db")
        return TransferCache(db_path=db_path)

    @pytest.fixture
    def sample_transfer(self):
        return Transfer(
            from_poi_id="poi_1",
            to_poi_id="poi_2",
            travel_mode=TravelMode.WALKING,
            duration_minutes=20,
            distance_km=1.5,
        )

    # === 단건 put / get ===

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_put_and_get(self, cache, sample_transfer):
        """저장 후 조회"""
        await cache.put(sample_transfer)
        result = await cache.get("poi_1", "poi_2", TravelMode.WALKING)

        assert result is not None
        assert result.from_poi_id == "poi_1"
        assert result.to_poi_id == "poi_2"
        assert result.travel_mode == TravelMode.WALKING
        assert result.duration_minutes == 20
        assert result.distance_km == 1.5

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_get_miss(self, cache):
        """미등록 조회 시 None"""
        result = await cache.get("poi_x", "poi_y", TravelMode.WALKING)
        assert result is None

    # === travel_mode 별 독립 저장 ===

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_different_travel_modes(self, cache):
        """같은 출발/도착이라도 travel_mode가 다르면 독립 저장"""
        walking = Transfer(
            from_poi_id="A", to_poi_id="B",
            travel_mode=TravelMode.WALKING, duration_minutes=30, distance_km=2.0,
        )
        driving = Transfer(
            from_poi_id="A", to_poi_id="B",
            travel_mode=TravelMode.DRIVING, duration_minutes=10, distance_km=3.0,
        )
        await cache.put(walking)
        await cache.put(driving)

        w = await cache.get("A", "B", TravelMode.WALKING)
        d = await cache.get("A", "B", TravelMode.DRIVING)

        assert w is not None and w.duration_minutes == 30
        assert d is not None and d.duration_minutes == 10

    # === 중복 저장 (INSERT OR REPLACE) ===

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_overwrite_on_duplicate(self, cache):
        """같은 키로 재저장하면 덮어쓰기"""
        t1 = Transfer(
            from_poi_id="A", to_poi_id="B",
            travel_mode=TravelMode.WALKING, duration_minutes=10, distance_km=1.0,
        )
        t2 = Transfer(
            from_poi_id="A", to_poi_id="B",
            travel_mode=TravelMode.WALKING, duration_minutes=20, distance_km=2.0,
        )
        await cache.put(t1)
        await cache.put(t2)

        result = await cache.get("A", "B", TravelMode.WALKING)
        assert result is not None
        assert result.duration_minutes == 20
        assert result.distance_km == 2.0

    # === 배치 put / get ===

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_batch_put_and_get(self, cache):
        """다건 저장 후 다건 조회"""
        transfers = [
            Transfer(from_poi_id="A", to_poi_id="B", travel_mode=TravelMode.WALKING, duration_minutes=10, distance_km=1.0),
            Transfer(from_poi_id="B", to_poi_id="C", travel_mode=TravelMode.WALKING, duration_minutes=15, distance_km=1.5),
            Transfer(from_poi_id="C", to_poi_id="D", travel_mode=TravelMode.DRIVING, duration_minutes=5, distance_km=3.0),
        ]
        await cache.put_batch(transfers)

        pairs = [
            ("A", "B", TravelMode.WALKING),
            ("B", "C", TravelMode.WALKING),
            ("C", "D", TravelMode.DRIVING),
            ("X", "Y", TravelMode.WALKING),  # 캐시 미스
        ]
        result = await cache.get_batch(pairs)

        assert len(result) == 3
        assert "A|B|walking" in result
        assert "B|C|walking" in result
        assert "C|D|driving" in result
        assert "X|Y|walking" not in result

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_put_batch_empty(self, cache):
        """빈 리스트 배치 저장"""
        await cache.put_batch([])  # 에러 없이 통과
        assert await cache.size() == 0

    # === clear / size ===

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_clear_and_size(self, cache, sample_transfer):
        """clear 후 size 0"""
        await cache.put(sample_transfer)
        assert await cache.size() == 1

        await cache.clear()
        assert await cache.size() == 0

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_size_multiple(self, cache):
        """여러 건 저장 시 size 정확"""
        for i in range(5):
            t = Transfer(
                from_poi_id=f"p{i}", to_poi_id=f"p{i+1}",
                travel_mode=TravelMode.WALKING, duration_minutes=i * 10, distance_km=float(i),
            )
            await cache.put(t)
        assert await cache.size() == 5

    # === 영속성 ===

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_persistence(self, tmp_path):
        """인스턴스 재생성 후에도 데이터 유지"""
        db_path = str(tmp_path / "persist_test.db")

        cache1 = TransferCache(db_path=db_path)
        await cache1.put(Transfer(
            from_poi_id="A", to_poi_id="B",
            travel_mode=TravelMode.WALKING, duration_minutes=25, distance_km=2.0,
        ))

        cache2 = TransferCache(db_path=db_path)
        result = await cache2.get("A", "B", TravelMode.WALKING)
        assert result is not None
        assert result.duration_minutes == 25

    # === 동시성 ===

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_concurrent_access(self, cache):
        """동시 접근 시 데이터 정합성"""
        async def put_entry(idx: int):
            await cache.put(Transfer(
                from_poi_id=f"p{idx}", to_poi_id=f"p{idx+100}",
                travel_mode=TravelMode.WALKING, duration_minutes=idx, distance_km=float(idx),
            ))

        await asyncio.gather(*[put_entry(i) for i in range(10)])

        for i in range(10):
            result = await cache.get(f"p{i}", f"p{i+100}", TravelMode.WALKING)
            assert result is not None
            assert result.duration_minutes == i
