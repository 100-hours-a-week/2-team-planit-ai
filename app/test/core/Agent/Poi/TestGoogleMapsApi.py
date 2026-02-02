"""
Google Maps Places API 독립 테스트

API 키와 기본 기능이 정상 작동하는지 확인하는 테스트 코드
pytest 없이도 직접 실행 가능
"""
import asyncio
import pytest
import httpx
from typing import Optional

# config에서 API 키 로드
try:
    from app.core.config import settings
    API_KEY = settings.google_maps_api_key
except ImportError:
    import os
    API_KEY = os.getenv("GOOGLE_MAPS_API_KEY")


# Constants
BASE_URL = "https://places.googleapis.com/v1/places:searchText"
FIELD_MASK = ",".join([
    "places.id",
    "places.displayName",
    "places.formattedAddress",
    "places.location",
    "places.types",
    "places.primaryType",
    "places.googleMapsUri",
    "places.rating",
    "places.userRatingCount",
    "places.priceLevel",
    "places.websiteUri",
    "places.internationalPhoneNumber",
    "places.regularOpeningHours",
])


async def search_place(query: str, api_key: str) -> Optional[dict]:
    """
    Google Places Text Search API 호출
    
    Args:
        query: 검색 쿼리
        api_key: Google Maps API 키
        
    Returns:
        API 응답 전체 또는 None
    """
    headers = {
        "Content-Type": "application/json",
        "X-Goog-Api-Key": api_key,
        "X-Goog-FieldMask": FIELD_MASK,
    }
    
    payload = {
        "textQuery": query,
        "languageCode": "ko",
    }
    
    async with httpx.AsyncClient() as client:
        response = await client.post(
            BASE_URL,
            headers=headers,
            json=payload,
            timeout=10.0
        )
        
        print(f"Status Code: {response.status_code}")
        
        if response.status_code != 200:
            print(f"Error: {response.text}")
            return None
        
        return response.json()


def print_place_info(place: dict):
    """장소 정보를 보기 좋게 출력"""
    print("\n" + "=" * 50)
    print(f"📍 {place.get('displayName', {}).get('text', 'N/A')}")
    print("=" * 50)
    print(f"  Place ID: {place.get('id', 'N/A')}")
    print(f"  주소: {place.get('formattedAddress', 'N/A')}")
    
    location = place.get('location', {})
    print(f"  위치: {location.get('latitude', 'N/A')}, {location.get('longitude', 'N/A')}")
    
    print(f"  유형: {place.get('primaryType', 'N/A')}")
    print(f"  Types: {place.get('types', [])}")
    print(f"  평점: {place.get('rating', 'N/A')} ({place.get('userRatingCount', 0)} 리뷰)")
    print(f"  가격대: {place.get('priceLevel', 'N/A')}")
    print(f"  전화: {place.get('internationalPhoneNumber', 'N/A')}")
    print(f"  웹사이트: {place.get('websiteUri', 'N/A')}")
    print(f"  구글맵: {place.get('googleMapsUri', 'N/A')}")
    
    opening_hours = place.get('regularOpeningHours', {})
    if opening_hours:
        print(f"  영업시간:")
        for desc in opening_hours.get('weekdayDescriptions', []):
            print(f"    - {desc}")


# =============================================================================
# pytest 테스트
# =============================================================================
class TestGoogleMapsApi:
    """Google Maps API 테스트"""
    
    @pytest.fixture
    def api_key(self):
        """API 키 fixture"""
        if not API_KEY:
            pytest.skip("Google Maps API 키가 설정되지 않음")
        return API_KEY
    
    @pytest.mark.asyncio
    async def test_text_search_basic(self, api_key):
        """기본 Text Search 호출 테스트"""
        result = await search_place("서울 경복궁", api_key)
        
        assert result is not None
        assert "places" in result
        assert len(result["places"]) > 0
        
        place = result["places"][0]
        print_place_info(place)
        
        # 필수 필드 확인
        assert "id" in place
        assert "displayName" in place
        assert "formattedAddress" in place
    
    @pytest.mark.asyncio
    async def test_text_search_fields(self, api_key):
        """요청 필드 정상 반환 확인"""
        result = await search_place("서울 남산타워", api_key)
        
        assert result is not None
        place = result["places"][0]
        
        # Pro SKU 필드
        assert "location" in place
        assert "latitude" in place["location"]
        assert "longitude" in place["location"]
        
        # Enterprise SKU 필드 (있을 수도 없을 수도)
        # rating, priceLevel 등은 장소에 따라 없을 수 있음
        print_place_info(place)
    
    @pytest.mark.asyncio
    async def test_text_search_not_found(self, api_key):
        """존재하지 않는 장소 검색"""
        result = await search_place("asdfghjklzxcvbnmqwertyuiop12345", api_key)
        
        assert result is not None
        # 결과가 없으면 places가 빈 배열이거나 없음
        places = result.get("places", [])
        assert len(places) == 0
    
    @pytest.mark.asyncio
    async def test_text_search_restaurant(self, api_key):
        """레스토랑 검색 테스트"""
        result = await search_place("서울 을지로 미쉐린 레스토랑", api_key)
        
        assert result is not None
        if result.get("places"):
            place = result["places"][0]
            print_place_info(place)


# =============================================================================
# 직접 실행용
# =============================================================================
async def main():
    """직접 실행 테스트"""
    if not API_KEY:
        print("❌ GOOGLE_MAPS_API_KEY가 설정되지 않았습니다.")
        print("  .env 파일에 google_maps_api_key를 설정하거나")
        print("  환경변수 GOOGLE_MAPS_API_KEY를 설정해주세요.")
        return
    
    print("🔍 Google Maps Places API 테스트")
    print(f"  API Key: {API_KEY[:10]}...{API_KEY[-4:]}")
    
    # 테스트 1: 유명 관광지
    print("\n\n[테스트 1] 유명 관광지 검색")
    result = await search_place("서울 경복궁", API_KEY)
    if result and result.get("places"):
        print_place_info(result["places"][0])
    else:
        print("❌ 검색 실패")
    
    # 테스트 2: 맛집
    print("\n\n[테스트 2] 맛집 검색")
    result = await search_place("서울 광장시장 빈대떡", API_KEY)
    if result and result.get("places"):
        print_place_info(result["places"][0])
    else:
        print("❌ 검색 실패")
    
    # 테스트 3: 존재하지 않는 장소
    print("\n\n[테스트 3] 존재하지 않는 장소")
    result = await search_place("zzzxxxcccvvvbbb123456789", API_KEY)
    if not result or not result.get("places"):
        print("✅ 예상대로 결과 없음")
    else:
        print(f"❓ 예상외 결과: {result}")
    
    print("\n\n✅ 테스트 완료!")


if __name__ == "__main__":
    asyncio.run(main())
