"""
테스트용 더미 일정 데이터

도쿄 3일 여행 일정을 기반으로 한 더미 데이터를 제공합니다.
두 가지 형태의 데이터를 생성할 수 있습니다:
  1. ItineraryResponse (API 응답 스키마)
  2. List[Itinerary] (도메인 모델)

Usage:
    from app.test.core.dummy_itinerary import (
        create_dummy_itinerary_response,
        create_dummy_itineraries,
    )

    # API 응답 형식
    response = create_dummy_itinerary_response(trip_id=1)

    # 도메인 모델 형식
    itineraries = create_dummy_itineraries()
"""

from app.core.models.PoiAgentDataclass.poi import PoiData, PoiCategory, PoiSource
from app.core.models.ItineraryAgentDataclass.itinerary import (
    Itinerary,
    Transfer,
    TravelMode,
    ScheduledPoiEntry,
)
from app.schemas.Itinerary import (
    ItineraryResponse,
)


# ---------------------------------------------------------------------------
# POI 원본 데이터 (PoiData)
# ---------------------------------------------------------------------------

_DUMMY_POIS: dict[str, PoiData] = {
    # ── Day 1: 아사쿠사 → 우에노 → 아키하바라 ──
    "sensoji": PoiData(
        id="poi_sensoji_001",
        name="센소지 (浅草寺)",
        category=PoiCategory.ATTRACTION,
        description="도쿄에서 가장 오래된 사찰. 카미나리몬(뇌문)과 나카미세 거리가 유명.",
        city="도쿄",
        address="東京都台東区浅草2-3-1",
        source=PoiSource.WEB_SEARCH,
        raw_text="센소지는 도쿄 아사쿠사에 위치한 일본에서 가장 오래된 사찰입니다.",
        google_place_id="ChIJ8T1GpMGOGGARDYGSgpooDWw",
        latitude=35.7148,
        longitude=139.7967,
        google_maps_uri="https://maps.google.com/?cid=sensoji",
        google_rating=4.5,
        user_rating_count=85000,
    ),
    "ueno_park": PoiData(
        id="poi_ueno_park_002",
        name="우에노 공원 (上野公園)",
        category=PoiCategory.ATTRACTION,
        description="도쿄 최대 공원. 박물관, 동물원, 벚꽃 명소.",
        city="도쿄",
        address="東京都台東区上野公園",
        source=PoiSource.WEB_SEARCH,
        raw_text="우에노 공원은 도쿄 최대 규모의 공원으로 박물관과 동물원이 있습니다.",
        google_place_id="ChIJURBNaGKMGGAR1gFp5eLjl10",
        latitude=35.7146,
        longitude=139.7732,
        google_maps_uri="https://maps.google.com/?cid=ueno_park",
        google_rating=4.3,
        user_rating_count=45000,
    ),
    "akihabara": PoiData(
        id="poi_akihabara_003",
        name="아키하바라 전기거리",
        category=PoiCategory.SHOPPING,
        description="일본 최대 전자상가 및 오타쿠 문화 중심지.",
        city="도쿄",
        address="東京都千代田区外神田",
        source=PoiSource.WEB_SEARCH,
        raw_text="아키하바라는 전자제품과 애니메이션 관련 상품을 판매하는 거리입니다.",
        google_place_id="ChIJGa1GMWCMGGAR_LJB9Ysyqhk",
        latitude=35.6984,
        longitude=139.7731,
        google_maps_uri="https://maps.google.com/?cid=akihabara",
        google_rating=4.2,
        user_rating_count=22000,
    ),
    "asakusa_lunch": PoiData(
        id="poi_asakusa_lunch_004",
        name="아사쿠사 소메타로 (染太郎)",
        category=PoiCategory.RESTAURANT,
        description="1937년 창업 전통 오코노미야키 전문점.",
        city="도쿄",
        address="東京都台東区西浅草2-2-2",
        source=PoiSource.WEB_SEARCH,
        raw_text="소메타로는 아사쿠사의 전통 오코노미야키 가게입니다.",
        google_place_id="ChIJSometaro",
        latitude=35.7120,
        longitude=139.7930,
        google_maps_uri="https://maps.google.com/?cid=sometaro",
        google_rating=4.1,
        user_rating_count=3200,
        price_level="PRICE_LEVEL_MODERATE",
    ),

    # ── Day 2: 시부야 → 하라주쿠 → 신주쿠 ──
    "shibuya_crossing": PoiData(
        id="poi_shibuya_005",
        name="시부야 스크램블 교차로",
        category=PoiCategory.ATTRACTION,
        description="세계에서 가장 붐비는 횡단보도. 도쿄의 상징적 명소.",
        city="도쿄",
        address="東京都渋谷区道玄坂2丁目",
        source=PoiSource.WEB_SEARCH,
        raw_text="시부야 스크램블 교차로는 한 번에 3000명이 건너는 세계 최대 횡단보도입니다.",
        google_place_id="ChIJ_shibuya",
        latitude=35.6595,
        longitude=139.7004,
        google_maps_uri="https://maps.google.com/?cid=shibuya_crossing",
        google_rating=4.4,
        user_rating_count=62000,
    ),
    "meiji_shrine": PoiData(
        id="poi_meiji_006",
        name="메이지 신궁 (明治神宮)",
        category=PoiCategory.ATTRACTION,
        description="하라주쿠에 위치한 대규모 신사. 울창한 숲과 전통 건축.",
        city="도쿄",
        address="東京都渋谷区代々木神園町1-1",
        source=PoiSource.WEB_SEARCH,
        raw_text="메이지 신궁은 도쿄 도심 속 울창한 숲에 자리한 일본 최대 신사입니다.",
        google_place_id="ChIJ_meiji",
        latitude=35.6764,
        longitude=139.6993,
        google_maps_uri="https://maps.google.com/?cid=meiji_shrine",
        google_rating=4.6,
        user_rating_count=55000,
    ),
    "takeshita_street": PoiData(
        id="poi_takeshita_007",
        name="다케시타 거리 (竹下通り)",
        category=PoiCategory.SHOPPING,
        description="하라주쿠의 패션 거리. 트렌디한 의류와 디저트 가게.",
        city="도쿄",
        address="東京都渋谷区神宮前1丁目",
        source=PoiSource.WEB_SEARCH,
        raw_text="다케시타 거리는 젊은 패션과 크레이프가 유명한 하라주쿠의 대표 거리입니다.",
        google_place_id="ChIJ_takeshita",
        latitude=35.6702,
        longitude=139.7026,
        google_maps_uri="https://maps.google.com/?cid=takeshita",
        google_rating=4.1,
        user_rating_count=35000,
    ),
    "ichiran_shibuya": PoiData(
        id="poi_ichiran_008",
        name="이치란 라멘 시부야점",
        category=PoiCategory.RESTAURANT,
        description="1인 칸막이 좌석으로 유명한 돈코츠 라멘 체인.",
        city="도쿄",
        address="東京都渋谷区神南1-22-7",
        source=PoiSource.WEB_SEARCH,
        raw_text="이치란 라멘은 칸막이 좌석과 진한 돈코츠 국물로 유명합니다.",
        google_place_id="ChIJ_ichiran",
        latitude=35.6620,
        longitude=139.6995,
        google_maps_uri="https://maps.google.com/?cid=ichiran_shibuya",
        google_rating=4.3,
        user_rating_count=12000,
        price_level="PRICE_LEVEL_MODERATE",
    ),
    "shinjuku_gyoen": PoiData(
        id="poi_shinjuku_gyoen_009",
        name="신주쿠 교엔 (新宿御苑)",
        category=PoiCategory.ATTRACTION,
        description="프랑스·영국·일본식 정원이 어우러진 대규모 국립 공원.",
        city="도쿄",
        address="東京都新宿区内藤町11",
        source=PoiSource.WEB_SEARCH,
        raw_text="신주쿠 교엔은 세 가지 양식의 정원을 갖춘 도쿄의 대표 공원입니다.",
        google_place_id="ChIJ_shinjuku_gyoen",
        latitude=35.6852,
        longitude=139.7100,
        google_maps_uri="https://maps.google.com/?cid=shinjuku_gyoen",
        google_rating=4.5,
        user_rating_count=40000,
    ),

    # ── Day 3: 오다이바 → 츠키지 → 도쿄타워 ──
    "teamlab_borderless": PoiData(
        id="poi_teamlab_010",
        name="팀랩 보더리스 (teamLab Borderless)",
        category=PoiCategory.ENTERTAINMENT,
        description="세계 최대 몰입형 디지털 아트 뮤지엄.",
        city="도쿄",
        address="東京都江東区青海1-3-8",
        source=PoiSource.WEB_SEARCH,
        raw_text="팀랩 보더리스는 경계 없는 디지털 아트 전시로 전 세계 관광객을 끌어모읍니다.",
        google_place_id="ChIJ_teamlab",
        latitude=35.6260,
        longitude=139.7839,
        google_maps_uri="https://maps.google.com/?cid=teamlab",
        google_rating=4.5,
        user_rating_count=28000,
    ),
    "tsukiji_outer": PoiData(
        id="poi_tsukiji_011",
        name="츠키지 장외시장",
        category=PoiCategory.RESTAURANT,
        description="신선한 해산물과 길거리 음식의 천국.",
        city="도쿄",
        address="東京都中央区築地4丁目",
        source=PoiSource.WEB_SEARCH,
        raw_text="츠키지 장외시장은 스시, 타마고야키 등 신선한 해산물을 맛볼 수 있는 곳입니다.",
        google_place_id="ChIJ_tsukiji",
        latitude=35.6654,
        longitude=139.7707,
        google_maps_uri="https://maps.google.com/?cid=tsukiji",
        google_rating=4.2,
        user_rating_count=47000,
        price_level="PRICE_LEVEL_MODERATE",
    ),
    "tokyo_tower": PoiData(
        id="poi_tokyo_tower_012",
        name="도쿄타워 (東京タワー)",
        category=PoiCategory.ATTRACTION,
        description="333m 높이의 도쿄 랜드마크. 야경 명소.",
        city="도쿄",
        address="東京都港区芝公園4-2-8",
        source=PoiSource.WEB_SEARCH,
        raw_text="도쿄타워는 도쿄의 상징적인 랜드마크로 전망대에서 시내를 한눈에 볼 수 있습니다.",
        google_place_id="ChIJ_tokyo_tower",
        latitude=35.6586,
        longitude=139.7454,
        google_maps_uri="https://maps.google.com/?cid=tokyo_tower",
        google_rating=4.4,
        user_rating_count=72000,
    ),
    "odaiba_cafe": PoiData(
        id="poi_odaiba_cafe_013",
        name="빌즈 오다이바 (bills Odaiba)",
        category=PoiCategory.CAFE,
        description="세계 최고의 팬케이크로 유명한 호주 브런치 카페.",
        city="도쿄",
        address="東京都港区台場1-6-1",
        source=PoiSource.WEB_SEARCH,
        raw_text="빌즈는 리코타 팬케이크가 시그니처 메뉴인 호주 브런치 카페입니다.",
        google_place_id="ChIJ_bills",
        latitude=35.6270,
        longitude=139.7750,
        google_maps_uri="https://maps.google.com/?cid=bills_odaiba",
        google_rating=4.0,
        user_rating_count=5000,
        price_level="PRICE_LEVEL_MODERATE",
    ),
}


# ---------------------------------------------------------------------------
# 더미 Itinerary (도메인 모델) 생성
# ---------------------------------------------------------------------------

def create_dummy_itineraries() -> list[Itinerary]:
    """도쿄 3일 여행 더미 일정을 도메인 모델(List[Itinerary])로 반환한다.

    Returns:
        3일치 Itinerary 리스트
    """
    p = _DUMMY_POIS

    # ── Day 1: 아사쿠사 → 점심 → 우에노 → 아키하바라 ──
    day1 = Itinerary(
        date="2026-03-14",
        pois=[p["sensoji"], p["asakusa_lunch"], p["ueno_park"], p["akihabara"]],
        schedule=[
            ScheduledPoiEntry(poi_id="poi_sensoji_001", start_time="09:00", duration_minutes=90),
            ScheduledPoiEntry(poi_id="poi_asakusa_lunch_004", start_time="10:45", duration_minutes=60),
            ScheduledPoiEntry(poi_id="poi_ueno_park_002", start_time="12:15", duration_minutes=120),
            ScheduledPoiEntry(poi_id="poi_akihabara_003", start_time="14:45", duration_minutes=90),
        ],
        transfers=[
            Transfer(
                from_poi_id="poi_sensoji_001",
                to_poi_id="poi_asakusa_lunch_004",
                travel_mode=TravelMode.WALKING,
                duration_minutes=8,
                distance_km=0.6,
            ),
            Transfer(
                from_poi_id="poi_asakusa_lunch_004",
                to_poi_id="poi_ueno_park_002",
                travel_mode=TravelMode.WALKING,
                duration_minutes=15,
                distance_km=1.2,
            ),
            Transfer(
                from_poi_id="poi_ueno_park_002",
                to_poi_id="poi_akihabara_003",
                travel_mode=TravelMode.TRANSIT,
                duration_minutes=10,
                distance_km=2.5,
            ),
        ],
        total_duration_minutes=393,
    )

    # ── Day 2: 시부야 → 이치란 → 메이지 신궁 → 다케시타 → 신주쿠 교엔 ──
    day2 = Itinerary(
        date="2026-03-15",
        pois=[
            p["shibuya_crossing"],
            p["ichiran_shibuya"],
            p["meiji_shrine"],
            p["takeshita_street"],
            p["shinjuku_gyoen"],
        ],
        schedule=[
            ScheduledPoiEntry(poi_id="poi_shibuya_005", start_time="09:00", duration_minutes=30),
            ScheduledPoiEntry(poi_id="poi_ichiran_008", start_time="09:40", duration_minutes=45),
            ScheduledPoiEntry(poi_id="poi_meiji_006", start_time="10:45", duration_minutes=90),
            ScheduledPoiEntry(poi_id="poi_takeshita_007", start_time="12:25", duration_minutes=60),
            ScheduledPoiEntry(poi_id="poi_shinjuku_gyoen_009", start_time="13:45", duration_minutes=120),
        ],
        transfers=[
            Transfer(
                from_poi_id="poi_shibuya_005",
                to_poi_id="poi_ichiran_008",
                travel_mode=TravelMode.WALKING,
                duration_minutes=5,
                distance_km=0.3,
            ),
            Transfer(
                from_poi_id="poi_ichiran_008",
                to_poi_id="poi_meiji_006",
                travel_mode=TravelMode.WALKING,
                duration_minutes=15,
                distance_km=1.0,
            ),
            Transfer(
                from_poi_id="poi_meiji_006",
                to_poi_id="poi_takeshita_007",
                travel_mode=TravelMode.WALKING,
                duration_minutes=10,
                distance_km=0.7,
            ),
            Transfer(
                from_poi_id="poi_takeshita_007",
                to_poi_id="poi_shinjuku_gyoen_009",
                travel_mode=TravelMode.TRANSIT,
                duration_minutes=15,
                distance_km=3.0,
            ),
        ],
        total_duration_minutes=390,
    )

    # ── Day 3: 오다이바 → 카페 → 츠키지 → 도쿄타워 ──
    day3 = Itinerary(
        date="2026-03-16",
        pois=[
            p["teamlab_borderless"],
            p["odaiba_cafe"],
            p["tsukiji_outer"],
            p["tokyo_tower"],
        ],
        schedule=[
            ScheduledPoiEntry(poi_id="poi_teamlab_010", start_time="10:00", duration_minutes=120),
            ScheduledPoiEntry(poi_id="poi_odaiba_cafe_013", start_time="12:15", duration_minutes=60),
            ScheduledPoiEntry(poi_id="poi_tsukiji_011", start_time="14:00", duration_minutes=90),
            ScheduledPoiEntry(poi_id="poi_tokyo_tower_012", start_time="16:00", duration_minutes=60),
        ],
        transfers=[
            Transfer(
                from_poi_id="poi_teamlab_010",
                to_poi_id="poi_odaiba_cafe_013",
                travel_mode=TravelMode.WALKING,
                duration_minutes=10,
                distance_km=0.5,
            ),
            Transfer(
                from_poi_id="poi_odaiba_cafe_013",
                to_poi_id="poi_tsukiji_011",
                travel_mode=TravelMode.TRANSIT,
                duration_minutes=30,
                distance_km=8.0,
            ),
            Transfer(
                from_poi_id="poi_tsukiji_011",
                to_poi_id="poi_tokyo_tower_012",
                travel_mode=TravelMode.TRANSIT,
                duration_minutes=15,
                distance_km=3.5,
            ),
        ],
        total_duration_minutes=385,
    )

    return [day1, day2, day3]


# ---------------------------------------------------------------------------
# 더미 ItineraryResponse (API 응답 스키마) 생성
# ---------------------------------------------------------------------------

def create_dummy_itinerary_response(trip_id: int = 1) -> ItineraryResponse:
    """도쿄 3일 여행 더미 일정을 API 응답 형식(ItineraryResponse)으로 반환한다.

    내부적으로 create_dummy_itineraries()를 호출한 뒤
    schemas.Itinerary.gen_itinerary()를 통해 변환합니다.

    Args:
        trip_id: 여행 ID (기본값 1)

    Returns:
        ItineraryResponse
    """
    from app.schemas.Itinerary import gen_itinerary

    itineraries = create_dummy_itineraries()
    return gen_itinerary(trip_id=trip_id, itineraries=itineraries)


# ---------------------------------------------------------------------------
# POI 데이터 접근 헬퍼
# ---------------------------------------------------------------------------

def get_dummy_pois() -> dict[str, PoiData]:
    """더미 POI 딕셔너리를 반환한다.

    키는 짧은 alias (예: "sensoji", "shibuya_crossing"),
    값은 PoiData 인스턴스.
    """
    return dict(_DUMMY_POIS)


def get_dummy_poi_list() -> list[PoiData]:
    """모든 더미 POI를 리스트로 반환한다."""
    return list(_DUMMY_POIS.values())
