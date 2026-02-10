"""
DistanceCalculateAgent 테스트 (Mock 사용, SQLite 캐시)
"""
import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from app.core.Agents.ItineraryPlan.DistanceCalculateAgent import DistanceCalculateAgent
from app.core.models.ItineraryAgentDataclass.itinerary import TravelMode, Transfer
from app.core.models.PoiAgentDataclass.poi import PoiData, PoiCategory, PoiSource


class TestDistanceCalculateAgent:
    """DistanceCalculateAgent 테스트"""

    @pytest.fixture
    def agent(self, tmp_path):
        """테스트용 에이전트 (API 키 없음, 임시 DB)"""
        db_path = str(tmp_path / "test_transfer.db")
        return DistanceCalculateAgent(api_key=None, db_path=db_path)

    @pytest.fixture
    def agent_with_key(self, tmp_path):
        """테스트용 에이전트 (API 키 있음, 임시 DB)"""
        db_path = str(tmp_path / "test_transfer_key.db")
        return DistanceCalculateAgent(api_key="test_api_key", db_path=db_path)

    @pytest.fixture
    def sample_poi_1(self):
        """테스트용 POI 1"""
        return PoiData(
            id="poi_1",
            name="서울역",
            category=PoiCategory.ATTRACTION,
            address="서울특별시 용산구 한강대로 405",
            source=PoiSource.WEB_SEARCH,
            raw_text="서울의 중심 기차역"
        )

    @pytest.fixture
    def sample_poi_2(self):
        """테스트용 POI 2"""
        return PoiData(
            id="poi_2",
            name="남산타워",
            category=PoiCategory.ATTRACTION,
            address="서울특별시 용산구 남산공원길 105",
            source=PoiSource.WEB_SEARCH,
            raw_text="서울의 랜드마크"
        )

    @pytest.fixture
    def sample_poi_3(self):
        """테스트용 POI 3"""
        return PoiData(
            id="poi_3",
            name="경복궁",
            category=PoiCategory.ATTRACTION,
            address="서울특별시 종로구 사직로 161",
            source=PoiSource.WEB_SEARCH,
            raw_text="조선왕조의 궁궐"
        )

    # === 캐시 테스트 ===

    @pytest.mark.asyncio
    async def test_cache_save_and_get(self, agent, sample_poi_1, sample_poi_2):
        """캐시 저장 및 조회 테스트"""
        transfer = Transfer(
            from_poi_id=sample_poi_1.id,
            to_poi_id=sample_poi_2.id,
            travel_mode=TravelMode.WALKING,
            duration_minutes=20,
            distance_km=1.5
        )

        # 캐시에 저장
        await agent._cache.put(transfer)

        # 캐시에서 조회
        cached = await agent._cache.get(
            sample_poi_1.id,
            sample_poi_2.id,
            TravelMode.WALKING
        )

        assert cached is not None
        assert cached.duration_minutes == 20
        assert cached.distance_km == 1.5

    @pytest.mark.asyncio
    async def test_cache_miss(self, agent):
        """캐시 미스 테스트"""
        cached = await agent._cache.get("poi_x", "poi_y", TravelMode.WALKING)
        assert cached is None

    @pytest.mark.asyncio
    async def test_clear_cache(self, agent, sample_poi_1, sample_poi_2):
        """캐시 초기화 테스트"""
        transfer = Transfer(
            from_poi_id=sample_poi_1.id,
            to_poi_id=sample_poi_2.id,
            travel_mode=TravelMode.WALKING,
            duration_minutes=20,
            distance_km=1.5
        )
        await agent._cache.put(transfer)

        # 캐시 크기 확인
        assert await agent.get_cache_size() == 1

        # 캐시 초기화
        await agent.clear_cache()
        assert await agent.get_cache_size() == 0

    # === calculate 메서드 테스트 ===

    @pytest.mark.asyncio
    async def test_calculate_without_api_key(self, agent, sample_poi_1, sample_poi_2):
        """API 키 없이 계산 - 기본값 반환"""
        transfer = await agent.calculate(sample_poi_1, sample_poi_2)

        assert transfer.from_poi_id == "poi_1"
        assert transfer.to_poi_id == "poi_2"
        assert transfer.duration_minutes == 0
        assert transfer.distance_km == 0.0

    @pytest.mark.asyncio
    async def test_calculate_uses_cache(self, agent, sample_poi_1, sample_poi_2):
        """캐시 사용 테스트"""
        # 캐시에 미리 저장
        cached_transfer = Transfer(
            from_poi_id=sample_poi_1.id,
            to_poi_id=sample_poi_2.id,
            travel_mode=TravelMode.WALKING,
            duration_minutes=25,
            distance_km=2.0
        )
        await agent._cache.put(cached_transfer)

        # calculate 호출 - 캐시에서 가져와야 함
        result = await agent.calculate(sample_poi_1, sample_poi_2)

        assert result.duration_minutes == 25
        assert result.distance_km == 2.0

    @pytest.mark.asyncio
    async def test_calculate_with_mock_api(self, agent_with_key, sample_poi_1, sample_poi_2):
        """Mock API 응답으로 계산 테스트"""
        mock_response = {
            "status": "OK",
            "routes": [{
                "legs": [{
                    "duration": {"value": 900},  # 15분
                    "distance": {"value": 1200}  # 1.2km
                }]
            }]
        }

        with patch("httpx.AsyncClient") as mock_client:
            mock_instance = AsyncMock()
            mock_instance.get.return_value = MagicMock(json=lambda: mock_response)
            mock_client.return_value.__aenter__.return_value = mock_instance

            transfer = await agent_with_key.calculate(sample_poi_1, sample_poi_2)

            assert transfer.from_poi_id == "poi_1"
            assert transfer.to_poi_id == "poi_2"
            assert transfer.duration_minutes == 15
            assert transfer.distance_km == 1.2

    # === calculate_batch 테스트 ===

    @pytest.mark.asyncio
    async def test_calculate_batch(self, agent, sample_poi_1, sample_poi_2, sample_poi_3):
        """배치 계산 테스트"""
        pois = [sample_poi_1, sample_poi_2, sample_poi_3]
        transfers = await agent.calculate_batch(pois)

        assert len(transfers) == 2
        assert transfers[0].from_poi_id == "poi_1"
        assert transfers[0].to_poi_id == "poi_2"
        assert transfers[1].from_poi_id == "poi_2"
        assert transfers[1].to_poi_id == "poi_3"

    @pytest.mark.asyncio
    async def test_calculate_batch_empty(self, agent):
        """빈 리스트 배치 계산"""
        transfers = await agent.calculate_batch([])
        assert transfers == []

    @pytest.mark.asyncio
    async def test_calculate_batch_single_poi(self, agent, sample_poi_1):
        """POI 1개일 때 배치 계산"""
        transfers = await agent.calculate_batch([sample_poi_1])
        assert transfers == []
