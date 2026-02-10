"""
Google Maps Places API를 사용한 POI 매퍼 구현

Places API (New) Text Search를 사용하여 POI를 검증하고
실제 장소 정보로 PoiData를 보강합니다.
"""
import asyncio
import hashlib
import json
import logging
import math
from pathlib import Path
from typing import List, Optional
from datetime import datetime

import httpx

from app.core.Agents.Poi.PoiMapper.BasePoiMapper import BasePoiMapper
from app.core.models.PoiAgentDataclass.poi import (
    PoiInfo,
    PoiData,
    PoiCategory,
    PoiSource,
    PoiValidationError,
    OpeningHours,
    DailyOpeningHours,
    TimeSlot,
    DayOfWeek
)
from app.core.config import settings

logger = logging.getLogger(__name__)


# Google Maps 타입 -> PoiCategory 매핑
GOOGLE_TYPE_TO_CATEGORY = {
    "restaurant": PoiCategory.RESTAURANT,
    "food": PoiCategory.RESTAURANT,
    "meal_takeaway": PoiCategory.RESTAURANT,
    "meal_delivery": PoiCategory.RESTAURANT,
    "cafe": PoiCategory.CAFE,
    "coffee_shop": PoiCategory.CAFE,
    "bakery": PoiCategory.CAFE,
    "tourist_attraction": PoiCategory.ATTRACTION,
    "museum": PoiCategory.ATTRACTION,
    "park": PoiCategory.ATTRACTION,
    "amusement_park": PoiCategory.ATTRACTION,
    "zoo": PoiCategory.ATTRACTION,
    "aquarium": PoiCategory.ATTRACTION,
    "lodging": PoiCategory.ACCOMMODATION,
    "hotel": PoiCategory.ACCOMMODATION,
    "motel": PoiCategory.ACCOMMODATION,
    "shopping_mall": PoiCategory.SHOPPING,
    "store": PoiCategory.SHOPPING,
    "supermarket": PoiCategory.SHOPPING,
    "night_club": PoiCategory.ENTERTAINMENT,
    "movie_theater": PoiCategory.ENTERTAINMENT,
    "bar": PoiCategory.ENTERTAINMENT,
}


class GoogleMapsPoiMapper(BasePoiMapper):
    """Google Maps Places API를 사용한 POI 매퍼
    
    Places API (New) Text Search를 통해 POI를 검증하고
    실제 장소 정보로 보강합니다.
    
    Attributes:
        api_key: Google Maps API 키
        base_url: Places API 기본 URL
    """
    
    # Places API (New) Text Search 엔드포인트
    BASE_URL = "https://places.googleapis.com/v1/places:searchText"
    
    # 요청할 필드 (Pro + 일부 Enterprise)
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
        "places.priceRange",
        "places.websiteUri",
        "places.internationalPhoneNumber",
        "places.regularOpeningHours",
        "places.editorialSummary",
        "places.generativeSummary",
        "places.reviews",
    ])
    
    # 도시 좌표 기반 locationBias 반경 (미터)
    DEFAULT_LOCATION_BIAS_RADIUS = 50000.0  # 50km

    # 도시 좌표 캐시 파일 기본 경로
    DEFAULT_CACHE_PATH = Path(__file__).resolve().parent.parent.parent.parent.parent / "data" / "city_location_cache.json"

    def __init__(self, cache_path: Optional[str] = None):
        """
        Args:
            cache_path: 도시 좌표 캐시 JSON 파일 경로 (미제공 시 app/data/city_location_cache.json)
        """
        self.api_key = settings.google_maps_api_key
        if not self.api_key:
            logger.warning("Google Maps API 키가 설정되지 않았습니다.")

        # 캐시 파일 경로 설정 및 로드
        self._cache_path = Path(cache_path) if cache_path else self.DEFAULT_CACHE_PATH
        self._city_location_cache: dict[str, Optional[dict]] = self._load_cache()

    def _load_cache(self) -> dict[str, Optional[dict]]:
        """캐시 파일에서 도시 좌표 로드"""
        if not self._cache_path.exists():
            return {}
        try:
            with open(self._cache_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            logger.info(f"도시 좌표 캐시 로드: {len(data)}개 도시 ({self._cache_path})")
            return data
        except (json.JSONDecodeError, OSError) as e:
            logger.warning(f"도시 좌표 캐시 로드 실패: {e}")
            return {}

    def _save_cache(self) -> None:
        """현재 캐시를 JSON 파일로 저장"""
        try:
            self._cache_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self._cache_path, "w", encoding="utf-8") as f:
                json.dump(self._city_location_cache, f, ensure_ascii=False, indent=2)
            logger.info(f"도시 좌표 캐시 저장: {len(self._city_location_cache)}개 도시")
        except OSError as e:
            logger.error(f"도시 좌표 캐시 저장 실패: {e}")

    @staticmethod
    def generate_poi_id(url: str) -> str:
        """
        Generate poi_id from URL using MD5 hash.

        Args:
            url: Source URL of the POI

        Returns:
            MD5 hash of the URL as poi_id
        """
        return hashlib.md5(url.encode('utf-8')).hexdigest()

    async def _resolve_city_location(self, city: str) -> Optional[dict]:
        """
        도시명으로 좌표를 조회하고 캐시에 저장

        Google Places API의 includedType="locality"를 사용하여
        도시/행정구역만 검색하므로, 동명의 음식점/카페/테마파크가
        반환되는 것을 방지합니다.

        Args:
            city: 도시명 (예: "베네치아", "Paris")

        Returns:
            {"latitude": float, "longitude": float} 또는 None
        """
        if city in self._city_location_cache:
            return self._city_location_cache[city]

        # 도시 타입으로 제한하여 검색 (카페/레스토랑 등 제외)
        place_data = await self._search_city(city)
        if place_data:
            location = place_data.get("location")
            self._city_location_cache[city] = location
            self._save_cache()
            logger.info(f"도시 좌표 캐시 저장: {city} → {location}")
            return location

        self._city_location_cache[city] = None
        self._save_cache()
        logger.warning(f"도시 좌표 조회 실패: {city}")
        return None

    async def _search_city(self, city_name: str) -> Optional[dict]:
        """
        도시 전용 검색 (includedType으로 도시/행정구역만 반환)

        Args:
            city_name: 도시명

        Returns:
            첫 번째 결과의 place 데이터 또는 None
        """
        headers = {
            "Content-Type": "application/json",
            "X-Goog-Api-Key": self.api_key,
            "X-Goog-FieldMask": "places.location,places.displayName,places.formattedAddress",
        }

        payload = {
            "textQuery": city_name,
            "languageCode": "ko",
            "includedType": "locality",
        }

        async with httpx.AsyncClient() as client:
            response = await client.post(
                self.BASE_URL,
                headers=headers,
                json=payload,
                timeout=10.0,
            )

            if response.status_code != 200:
                logger.error(f"도시 검색 API 오류 [{response.status_code}]: {response.text}")
                return None

            places = response.json().get("places", [])
            if not places:
                logger.warning(f"도시 검색 결과 없음: {city_name}")
                return None

            logger.info(f"도시 검색 성공: {city_name} → {places[0].get('displayName', {}).get('text')}")
            return places[0]

    async def map_poi(
        self,
        poi_info: PoiInfo,
        city: str,
        source_url: Optional[str] = None,
        raise_on_failure: bool = False
    ) -> Optional[PoiData]:
        """
        단일 POI를 Google Maps로 검증 및 매핑

        Args:
            poi_info: 검증할 POI 정보
            city: 검색 컨텍스트 도시명
            source_url: POI 원본 URL (poi_id 생성에 사용)
            raise_on_failure: True이면 검증 실패 시 PoiValidationError 발생

        Returns:
            검증 성공 시 PoiData, 실패 시 None (raise_on_failure=False인 경우)

        Raises:
            PoiValidationError: raise_on_failure=True이고 검증 실패 시
        """
        # TODO: 이전에 검색한적이 있으면 캐쉬를 이용하여 재검색 방지
        if not self.api_key:
            error_msg = "API 키 없음 - 매핑 불가"
            logger.error(error_msg)
            if raise_on_failure:
                raise PoiValidationError(error_msg)
            return None

        # 도시 좌표를 먼저 조회하여 locationBias로 사용
        city_location = await self._resolve_city_location(city)

        # 검색 쿼리 생성: "POI명 도시명" → 실패 시 "POI명"으로 재검색
        query = f"{poi_info.name} {city}"

        try:
            place_data = await self._search_place(query, location_bias=city_location)

            if not place_data:
                logger.info(f"'{query}' 검색 결과 없음, POI명으로 재검색: {poi_info.name}")
                place_data = await self._search_place(poi_info.name, location_bias=city_location)

            if not place_data:
                error_msg = f"장소를 찾을 수 없음: {poi_info.name}"
                logger.info(error_msg)
                if raise_on_failure:
                    raise PoiValidationError(error_msg)
                return None

            # PoiData로 변환
            poi_data = self._convert_to_poi_data(poi_info, place_data, city, source_url)
            return poi_data

        except PoiValidationError:
            raise
        except Exception as e:
            error_msg = f"POI 매핑 실패 [{poi_info.name}]: {e}"
            logger.error(error_msg)
            if raise_on_failure:
                raise PoiValidationError(error_msg)
            return None
    
    async def map_pois_batch(
        self, 
        poi_infos: List[PoiInfo], 
        city: str
    ) -> List[PoiData]:
        """
        여러 POI를 배치로 매핑
        
        Args:
            poi_infos: POI 정보 리스트
            city: 검색 컨텍스트 도시명
            
        Returns:
            검증 성공한 PoiData 리스트
        """
        if not poi_infos:
            return []
        
        # 동시 요청 (rate limit 고려하여 세마포어 사용)
        semaphore = asyncio.Semaphore(5)  # 동시 최대 5개 요청
        
        async def map_with_semaphore(poi_info: PoiInfo) -> Optional[PoiData]:
            async with semaphore:
                return await self.map_poi(poi_info, city)
        
        results = await asyncio.gather(
            *[map_with_semaphore(poi) for poi in poi_infos],
            return_exceptions=True
        )
        
        # 성공한 결과만 필터링
        valid_results = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                logger.error(f"배치 매핑 오류 [{poi_infos[i].name}]: {result}")
            elif result is not None:
                valid_results.append(result)
        
        logger.info(f"배치 매핑 완료: {len(valid_results)}/{len(poi_infos)} 성공")
        return valid_results
    
    async def _search_place(
        self,
        query: str,
        location_bias: Optional[dict] = None
    ) -> Optional[dict]:
        """
        Google Places Text Search API 호출

        Args:
            query: 검색 쿼리
            location_bias: 검색 중심 좌표 {"latitude": float, "longitude": float}
                          설정 시 해당 좌표 주변 결과를 우선 반환

        Returns:
            첫 번째 결과의 place 데이터 또는 None
        """
        headers = {
            "Content-Type": "application/json",
            "X-Goog-Api-Key": self.api_key,
            "X-Goog-FieldMask": self.FIELD_MASK,
        }

        payload = {
            "textQuery": query,
            "languageCode": "ko",
        }

        # 좌표가 있으면 locationRestriction(rectangle) 적용 (해당 지역 내 결과만 반환)
        if location_bias and "latitude" in location_bias and "longitude" in location_bias:
            lat = location_bias["latitude"]
            lng = location_bias["longitude"]
            # 반경(m)을 위도/경도 오프셋으로 변환 (근사값: 위도 1도 ≈ 111km)
            lat_offset = self.DEFAULT_LOCATION_BIAS_RADIUS / 111_000
            lng_offset = self.DEFAULT_LOCATION_BIAS_RADIUS / (111_000 * max(abs(math.cos(math.radians(lat))), 0.01))
            payload["locationRestriction"] = {
                "rectangle": {
                    "low": {
                        "latitude": lat - lat_offset,
                        "longitude": lng - lng_offset,
                    },
                    "high": {
                        "latitude": lat + lat_offset,
                        "longitude": lng + lng_offset,
                    },
                }
            }
        
        async with httpx.AsyncClient() as client:
            response = await client.post(
                self.BASE_URL,
                headers=headers,
                json=payload,
                timeout=10.0
            )
            
            if response.status_code != 200:
                logger.error(f"API 오류 [{response.status_code}]: {response.text}")
                return None
            
            data = response.json()
            places = data.get("places", [])
            
            if not places:
                return None
            
            return places[0]  # 첫 번째 결과 반환
    
    def _convert_to_poi_data(
        self,
        poi_info: PoiInfo,
        place_data: dict,
        city: str,
        source_url: Optional[str] = None
    ) -> PoiData:
        """
        Google Places 응답을 PoiData로 변환

        Args:
            poi_info: 원본 POI 정보
            place_data: Google Places API 응답 데이터
            city: 도시명
            source_url: POI 원본 URL (poi_id 생성에 사용)

        Returns:
            변환된 PoiData
        """
        # 위치 정보
        location = place_data.get("location", {})

        # 카테고리 매핑
        primary_type = place_data.get("primaryType", "")
        types = place_data.get("types", [])
        category = self._map_category(primary_type, types)

        # 영업시간 파싱
        opening_hours = self._parse_opening_hours(
            place_data.get("regularOpeningHours", {})
        )

        # 가격 정보 파싱
        price_range_str = self._parse_price_range(
            place_data.get("priceRange", {})
        )

        # 임베딩용 텍스트 생성
        raw_text = self._build_raw_text(poi_info, place_data)

        # poi_id 결정: 구글 Places ID 사용
        poi_id = place_data.get("id")

        # source_url 결정: 제공된 source_url 또는 Google Maps URI
        final_source_url = source_url or place_data.get("googleMapsUri")

        # Summary 필드 파싱
        editorial_summary = self._extract_summary_text(place_data.get("editorialSummary"))
        generative_summary = self._extract_summary_text(place_data.get("generativeSummary"))
        review_summary = self._extract_review_summary(place_data.get("reviews"))

        return PoiData(
            id=poi_id,
            name=place_data.get("displayName", {}).get("text", poi_info.name),
            category=category,
            description=poi_info.description,
            city=city,
            address=place_data.get("formattedAddress"),
            source=PoiSource.WEB_SEARCH,
            source_url=final_source_url,
            raw_text=raw_text,
            created_at=datetime.now(),
            # Google Maps 필드
            google_place_id=place_data.get("id"),
            latitude=location.get("latitude"),
            longitude=location.get("longitude"),
            google_maps_uri=place_data.get("googleMapsUri"),
            types=types,
            primary_type=primary_type,
            google_rating=place_data.get("rating"),
            user_rating_count=place_data.get("userRatingCount"),
            price_level=place_data.get("priceLevel"),
            price_range=price_range_str,
            website_uri=place_data.get("websiteUri"),
            phone_number=place_data.get("internationalPhoneNumber"),
            opening_hours=opening_hours,
            # Summary 필드
            editorial_summary=editorial_summary,
            generative_summary=generative_summary,
            review_summary=review_summary,
        )
    
    def _map_category(self, primary_type: str, types: List[str]) -> PoiCategory:
        """Google 타입을 PoiCategory로 매핑"""
        # primary_type 우선 확인
        if primary_type in GOOGLE_TYPE_TO_CATEGORY:
            return GOOGLE_TYPE_TO_CATEGORY[primary_type]
        
        # types 목록에서 찾기
        for t in types:
            if t in GOOGLE_TYPE_TO_CATEGORY:
                return GOOGLE_TYPE_TO_CATEGORY[t]
        
        return PoiCategory.OTHER
    
    def _parse_opening_hours(self, hours_data: dict) -> Optional[OpeningHours]:
        """
        Google API 영업시간을 구조화된 OpeningHours 모델로 변환
        
        Args:
            hours_data: Google API regularOpeningHours 데이터
            
        Returns:
            구조화된 OpeningHours 또는 None
        """
        if not hours_data:
            return None
        
        # 원본 텍스트 백업
        raw_text = hours_data.get("weekdayDescriptions", [])
        
        # periods 파싱
        periods_data = hours_data.get("periods", [])
        daily_hours_map: dict[int, DailyOpeningHours] = {}
        
        for period in periods_data:
            open_info = period.get("open", {})
            close_info = period.get("close", {})
            
            open_day = open_info.get("day")  # 0=일, 1=월, ... 6=토 (Google 기준)
            open_hour = open_info.get("hour", 0)
            open_minute = open_info.get("minute", 0)
            
            close_day = close_info.get("day", open_day)
            close_hour = close_info.get("hour", 23)
            close_minute = close_info.get("minute", 59)
            
            if open_day is None:
                continue
            
            # Google의 요일(0=일요일) → ISO 8601(1=월요일) 변환
            iso_day = 7 if open_day == 0 else open_day
            
            try:
                from datetime import time as dt_time
                open_time = dt_time(open_hour, open_minute)
                close_time = dt_time(close_hour, close_minute)
                
                time_slot = TimeSlot(open_time=open_time, close_time=close_time)
                
                if iso_day not in daily_hours_map:
                    daily_hours_map[iso_day] = DailyOpeningHours(
                        day=DayOfWeek(iso_day),
                        slots=[],
                        is_closed=False
                    )
                
                daily_hours_map[iso_day].slots.append(time_slot)
                
            except (ValueError, TypeError) as e:
                logger.warning(f"영업시간 파싱 오류: {e}")
                continue
        
        # 모든 요일에 대해 데이터 생성 (없는 요일은 휴무)
        periods = []
        for day_num in range(1, 8):  # 1(월) ~ 7(일)
            if day_num in daily_hours_map:
                periods.append(daily_hours_map[day_num])
            else:
                periods.append(DailyOpeningHours(
                    day=DayOfWeek(day_num),
                    slots=[],
                    is_closed=True
                ))
        
        return OpeningHours(
            periods=periods,
            raw_text=raw_text if raw_text else None
        )
    
    def _parse_price_range(self, price_range_data: dict) -> Optional[str]:
        """
        가격 범위 파싱
        
        Args:
            price_range_data: Google API의 priceRange 데이터
            
        Returns:
            "최저가 ~ 최고가" 형식의 문자열 또는 None
        """
        if not price_range_data:
            return None
        
        start_price = price_range_data.get("startPrice", {})
        end_price = price_range_data.get("endPrice", {})
        
        start_text = self._format_price(start_price)
        end_text = self._format_price(end_price)
        
        if start_text and end_text:
            return f"{start_text} ~ {end_text}"
        elif start_text:
            return f"{start_text} ~"
        elif end_text:
            return f"~ {end_text}"
        
        return None
    
    def _format_price(self, price_data: dict) -> Optional[str]:
        """가격 데이터를 포맷팅"""
        if not price_data:
            return None
        
        units = price_data.get("units", "")
        currency = price_data.get("currencyCode", "")
        
        if units:
            return f"{units} {currency}"
        
        return None
    
    def _build_raw_text(self, poi_info: PoiInfo, place_data: dict) -> str:
        """임베딩용 텍스트 생성"""
        parts = [place_data.get("displayName", {}).get("text", poi_info.name)]

        if poi_info.description:
            parts.append(poi_info.description)

        address = place_data.get("formattedAddress")
        if address:
            parts.append(f"위치: {address}")

        if poi_info.highlights:
            parts.append(f"특징: {', '.join(poi_info.highlights)}")

        return ". ".join(parts)

    def _extract_summary_text(self, summary_data: Optional[dict]) -> Optional[str]:
        """editorialSummary, generativeSummary에서 텍스트 추출"""
        if not summary_data:
            return None
        # Google API 응답: {"text": "...", "languageCode": "ko"} 또는 {"overview": {"text": "..."}}
        if "text" in summary_data:
            return summary_data.get("text")
        if "overview" in summary_data:
            return summary_data.get("overview", {}).get("text")
        return None

    def _extract_review_summary(self, reviews: Optional[List[dict]]) -> Optional[str]:
        """reviews 배열에서 상위 리뷰 요약 생성"""
        if not reviews:
            return None
        # 상위 3개 리뷰 텍스트 결합
        summaries = []
        for review in reviews[:3]:
            text = review.get("text", {}).get("text") if isinstance(review.get("text"), dict) else review.get("text")
            if text:
                summaries.append(text[:200])  # 각 리뷰 200자 제한
        return " | ".join(summaries) if summaries else None
