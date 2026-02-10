"""
DistanceCalculateAgent: Google Maps Directions API를 이용한 이동 정보 계산

주요 기능:
- POI 간 이동 시간/거리 계산
- SQLite 캐싱을 통한 API 호출 비용 절감 (프로세스 재시작 후에도 유지)
"""
from typing import List, Optional, Tuple
import httpx
import asyncio

from app.core.config import settings
from app.core.models.PoiAgentDataclass.poi import PoiData
from app.core.models.ItineraryAgentDataclass.itinerary import (
    Transfer,
    TravelMode,
)
from app.core.Agents.ItineraryPlan.TransferCache import TransferCache


class DistanceCalculateAgent:
    """Google Maps API를 이용한 POI 간 이동 정보 계산 에이전트 (SQLite 캐싱 지원)"""

    GOOGLE_MAPS_DIRECTIONS_URL = "https://maps.googleapis.com/maps/api/directions/json"

    def __init__(self, api_key: Optional[str] = None, db_path: Optional[str] = None):
        """
        Args:
            api_key: Google Maps API 키 (None이면 settings에서 가져옴)
            db_path: SQLite DB 경로 (None이면 기본 경로 사용)
        """
        self.api_key = api_key or settings.google_maps_api_key
        self._cache = TransferCache(db_path=db_path)

    async def clear_cache(self) -> None:
        """캐시 초기화"""
        await self._cache.clear()

    async def get_cache_size(self) -> int:
        """현재 캐시 크기 반환"""
        return await self._cache.size()

    async def calculate(
        self,
        from_poi: PoiData,
        to_poi: PoiData,
        mode: TravelMode = TravelMode.WALKING
    ) -> Transfer:
        """
        두 POI 간 이동 정보 계산

        Args:
            from_poi: 시작 POI
            to_poi: 도착 POI
            mode: 이동 수단

        Returns:
            Transfer 객체
        """
        # 캐시 확인
        cached = await self._cache.get(from_poi.id, to_poi.id, mode)
        if cached:
            return cached

        # API 호출
        transfer = await self._call_directions_api(from_poi, to_poi, mode)

        # 캐시 저장
        await self._cache.put(transfer)

        return transfer

    async def _call_directions_api(
        self,
        from_poi: PoiData,
        to_poi: PoiData,
        mode: TravelMode
    ) -> Transfer:
        """Google Maps Directions API 호출"""
        if not self.api_key:
            # API 키가 없으면 기본값 반환
            return Transfer(
                from_poi_id=from_poi.id,
                to_poi_id=to_poi.id,
                travel_mode=mode,
                duration_minutes=0,
                distance_km=0.0
            )

        # 주소 기반 검색 (주소가 없으면 이름 사용)
        origin = from_poi.address or from_poi.name
        destination = to_poi.address or to_poi.name

        params = {
            "origin": origin,
            "destination": destination,
            "mode": mode.value,
            "key": self.api_key,
        }

        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    self.GOOGLE_MAPS_DIRECTIONS_URL,
                    params=params,
                    timeout=10.0
                )
                data = response.json()

            if data.get("status") == "OK" and data.get("routes"):
                route = data["routes"][0]
                leg = route["legs"][0]

                duration_seconds = leg["duration"]["value"]
                distance_meters = leg["distance"]["value"]

                return Transfer(
                    from_poi_id=from_poi.id,
                    to_poi_id=to_poi.id,
                    travel_mode=mode,
                    duration_minutes=duration_seconds // 60,
                    distance_km=distance_meters / 1000.0
                )
            else:
                # API 오류 시 기본값 반환
                return Transfer(
                    from_poi_id=from_poi.id,
                    to_poi_id=to_poi.id,
                    travel_mode=mode,
                    duration_minutes=0,
                    distance_km=0.0
                )
        except Exception as e:
            print(f"Google Maps API 호출 실패: {e}")
            return Transfer(
                from_poi_id=from_poi.id,
                to_poi_id=to_poi.id,
                travel_mode=mode,
                duration_minutes=0,
                distance_km=0.0
            )

    async def calculate_batch(
        self,
        pois: List[PoiData],
        mode: TravelMode = TravelMode.WALKING
    ) -> List[Transfer]:
        """
        POI 리스트의 연속 구간별 이동 정보 일괄 계산

        Args:
            pois: POI 리스트 (순서대로)
            mode: 이동 수단

        Returns:
            Transfer 리스트 (len(pois) - 1 개)
        """
        if len(pois) <= 1:
            return []

        # 배치 캐시 조회
        pairs: List[Tuple[str, str, TravelMode]] = [
            (pois[i].id, pois[i + 1].id, mode) for i in range(len(pois) - 1)
        ]
        cached_map = await self._cache.get_batch(pairs)

        transfers = []
        tasks = []

        for i in range(len(pois) - 1):
            from_poi = pois[i]
            to_poi = pois[i + 1]
            key = f"{from_poi.id}|{to_poi.id}|{mode.value}"

            cached = cached_map.get(key)
            if cached:
                transfers.append((i, cached))
            else:
                tasks.append((i, self.calculate(from_poi, to_poi, mode)))

        # 캐시 미스된 것들만 병렬 API 호출
        if tasks:
            results = await asyncio.gather(*[task for _, task in tasks])
            for (idx, _), result in zip(tasks, results):
                transfers.append((idx, result))

        # 인덱스 순서로 정렬
        transfers.sort(key=lambda x: x[0])

        return [transfer for _, transfer in transfers]
