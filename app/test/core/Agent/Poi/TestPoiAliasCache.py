import asyncio
import os
import tempfile

import pytest

from app.core.Agents.Poi.PoiAliasCache import PoiAliasCache


# =============================================================================
# 단위 테스트
# =============================================================================
class TestPoiAliasCacheUnit:
    """PoiAliasCache 단위 테스트"""

    @pytest.fixture
    def cache(self, tmp_path):
        """임시 디렉토리에 SQLite DB를 생성하는 캐시"""
        db_path = str(tmp_path / "test_alias.db")
        return PoiAliasCache(db_path=db_path)

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_add_and_find(self, cache):
        """등록 후 조회"""
        await cache.add("별다방", "서울", "ABC123")
        result = await cache.find_by_name("별다방", "서울")
        assert result == "ABC123"

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_find_miss(self, cache):
        """미등록 이름 조회 시 None"""
        result = await cache.find_by_name("없는장소", "서울")
        assert result is None

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_has_place_id(self, cache):
        """place_id 존재 확인"""
        await cache.add("별다방", "서울", "ABC123")
        assert await cache.has_place_id("ABC123") is True
        assert await cache.has_place_id("NOTEXIST") is False

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_alias_registration(self, cache):
        """같은 place_id에 다른 이름 등록 후 양쪽 모두 조회 가능"""
        await cache.add("별다방", "서울", "ABC123")
        await cache.add("스타카페", "서울", "ABC123")
        await cache.add("StarCafe", "서울", "ABC123")

        assert await cache.find_by_name("별다방", "서울") == "ABC123"
        assert await cache.find_by_name("스타카페", "서울") == "ABC123"
        assert await cache.find_by_name("starcafe", "서울") == "ABC123"

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_name_normalization(self, cache):
        """대소문자, 공백 차이 정규화"""
        await cache.add("Star  Cafe", "서울", "ABC123")

        # 대소문자 무시 + 연속 공백 정규화
        assert await cache.find_by_name("star cafe", "서울") == "ABC123"
        assert await cache.find_by_name("STAR CAFE", "서울") == "ABC123"
        assert await cache.find_by_name("  Star   Cafe  ", "서울") == "ABC123"

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_different_city_isolation(self, cache):
        """다른 도시의 같은 이름은 별개"""
        await cache.add("맛집", "서울", "ABC123")
        await cache.add("맛집", "부산", "DEF456")

        assert await cache.find_by_name("맛집", "서울") == "ABC123"
        assert await cache.find_by_name("맛집", "부산") == "DEF456"

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_duplicate_insert_ignored(self, cache):
        """중복 등록 시 무시 (INSERT OR IGNORE)"""
        await cache.add("별다방", "서울", "ABC123")
        await cache.add("별다방", "서울", "XYZ999")  # 같은 (name, city) → 무시

        result = await cache.find_by_name("별다방", "서울")
        assert result == "ABC123"  # 첫 등록 값 유지

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_empty_inputs(self, cache):
        """빈 값 입력 처리"""
        await cache.add("", "서울", "ABC123")  # 빈 이름 → 무시
        await cache.add("별다방", "서울", "")  # 빈 place_id → 무시

        assert await cache.find_by_name("", "서울") is None
        assert await cache.has_place_id("") is False

    @pytest.mark.unit
    def test_normalize_name_static(self):
        """정규화 함수 단독 테스트"""
        assert PoiAliasCache.normalize_name("  Star  Cafe  ") == "star cafe"
        assert PoiAliasCache.normalize_name("ABC") == "abc"
        assert PoiAliasCache.normalize_name("") == ""
        assert PoiAliasCache.normalize_name("  ") == ""

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_concurrent_access(self, cache):
        """동시 접근 시 데이터 정합성"""
        async def add_entry(name: str, place_id: str):
            await cache.add(name, "서울", place_id)

        # 10개 동시 등록
        tasks = [add_entry(f"장소_{i}", f"PID_{i}") for i in range(10)]
        await asyncio.gather(*tasks)

        # 모두 조회 가능
        for i in range(10):
            result = await cache.find_by_name(f"장소_{i}", "서울")
            assert result == f"PID_{i}"

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_persistence(self, tmp_path):
        """SQLite 영속성: DB 재생성해도 데이터 유지"""
        db_path = str(tmp_path / "persist_test.db")

        # 첫 인스턴스에서 데이터 추가
        cache1 = PoiAliasCache(db_path=db_path)
        await cache1.add("별다방", "서울", "ABC123")

        # 새 인스턴스로 조회
        cache2 = PoiAliasCache(db_path=db_path)
        result = await cache2.find_by_name("별다방", "서울")
        assert result == "ABC123"
