"""
Itinerary 데이터 모델 테스트
"""
import pytest
from app.core.models.ItineraryAgentDataclass.itinerary import (
    TravelMode,
    Transfer,
    Itinerary,
)
from app.core.models.PoiAgentDataclass.poi import PoiData, PoiCategory, PoiSource


class TestTravelMode:
    """TravelMode Enum 테스트"""

    def test_travel_mode_values(self):
        """이동 수단 값 확인"""
        assert TravelMode.DRIVING.value == "driving"
        assert TravelMode.WALKING.value == "walking"
        assert TravelMode.TRANSIT.value == "transit"
        assert TravelMode.BICYCLING.value == "bicycling"

    def test_travel_mode_from_string(self):
        """문자열에서 TravelMode 변환"""
        assert TravelMode("walking") == TravelMode.WALKING
        assert TravelMode("driving") == TravelMode.DRIVING


class TestTransfer:
    """Transfer 모델 테스트"""

    def test_transfer_creation(self):
        """Transfer 생성"""
        transfer = Transfer(
            from_poi_id="poi_1",
            to_poi_id="poi_2",
            travel_mode=TravelMode.WALKING,
            duration_minutes=15,
            distance_km=1.2
        )

        assert transfer.from_poi_id == "poi_1"
        assert transfer.to_poi_id == "poi_2"
        assert transfer.travel_mode == TravelMode.WALKING
        assert transfer.duration_minutes == 15
        assert transfer.distance_km == 1.2

    def test_transfer_default_values(self):
        """기본값 확인"""
        transfer = Transfer(
            from_poi_id="poi_1",
            to_poi_id="poi_2"
        )

        assert transfer.travel_mode == TravelMode.WALKING
        assert transfer.duration_minutes == 0
        assert transfer.distance_km == 0.0


class TestItinerary:
    """Itinerary 모델 테스트"""

    @pytest.fixture
    def sample_pois(self):
        """테스트용 POI 리스트"""
        return [
            PoiData(
                id=f"poi_{i}",
                name=f"장소 {i}",
                category=PoiCategory.ATTRACTION,
                source=PoiSource.WEB_SEARCH,
                raw_text=f"테스트 장소 {i}"
            )
            for i in range(3)
        ]

    @pytest.fixture
    def sample_transfers(self):
        """테스트용 Transfer 리스트"""
        return [
            Transfer(
                from_poi_id="poi_0",
                to_poi_id="poi_1",
                duration_minutes=10,
                distance_km=0.8
            ),
            Transfer(
                from_poi_id="poi_1",
                to_poi_id="poi_2",
                duration_minutes=15,
                distance_km=1.2
            )
        ]

    def test_itinerary_creation(self, sample_pois, sample_transfers):
        """Itinerary 생성"""
        itinerary = Itinerary(
            date="2024-01-15",
            pois=sample_pois,
            transfers=sample_transfers,
            total_duration_minutes=180
        )

        assert itinerary.date == "2024-01-15"
        assert len(itinerary.pois) == 3
        assert len(itinerary.transfers) == 2
        assert itinerary.total_duration_minutes == 180

    def test_itinerary_empty_creation(self):
        """빈 Itinerary 생성"""
        itinerary = Itinerary(date="2024-01-15")

        assert itinerary.date == "2024-01-15"
        assert itinerary.pois == []
        assert itinerary.transfers == []
        assert itinerary.total_duration_minutes == 0

    def test_validate_transfers_count_valid(self, sample_pois, sample_transfers):
        """Transfer 개수 검증 - 유효한 경우"""
        itinerary = Itinerary(
            date="2024-01-15",
            pois=sample_pois,
            transfers=sample_transfers
        )

        # POI 3개, Transfer 2개 (3-1)
        assert itinerary.validate_transfers_count() is True

    def test_validate_transfers_count_invalid(self, sample_pois):
        """Transfer 개수 검증 - 유효하지 않은 경우"""
        itinerary = Itinerary(
            date="2024-01-15",
            pois=sample_pois,
            transfers=[]  # Transfer가 없음
        )

        assert itinerary.validate_transfers_count() is False

    def test_validate_transfers_count_single_poi(self):
        """Transfer 개수 검증 - POI 1개일 때"""
        poi = PoiData(
            id="poi_1",
            name="장소 1",
            category=PoiCategory.ATTRACTION,
            source=PoiSource.WEB_SEARCH,
            raw_text="테스트"
        )
        itinerary = Itinerary(
            date="2024-01-15",
            pois=[poi],
            transfers=[]
        )

        # POI 1개면 Transfer 0개가 정상
        assert itinerary.validate_transfers_count() is True
