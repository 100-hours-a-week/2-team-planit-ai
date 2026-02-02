"""
DistanceCalculateAgent: Google Maps Directions API를 이용한 이동 정보 계산

주요 기능:
- POI 간 이동 시간/거리 계산
- 캐싱을 통한 API 호출 비용 절감
"""
from typing import List, Dict, Optional, Tuple
import httpx
import asyncio

from app.core.config import settings
from app.core.models.PoiAgentDataclass.poi import PoiData
from app.core.models.ItineraryAgentDataclass.itinerary import (
    Transfer,
    TravelMode,
)


class DistanceCalculateAgent:
    """Google Maps API를 이용한 POI 간 이동 정보 계산 에이전트 (캐싱 지원)"""
    
    GOOGLE_MAPS_DIRECTIONS_URL = "https://maps.googleapis.com/maps/api/directions/json"
    
    def __init__(self, api_key: Optional[str] = None):
        """
        Args:
            api_key: Google Maps API 키 (None이면 settings에서 가져옴)
        """
        self.api_key = api_key or settings.google_maps_api_key
        self._cache: Dict[str, Transfer] = {}
    
    def _get_cache_key(self, from_id: str, to_id: str, mode: TravelMode) -> str:
        """캐시 키 생성"""
        return f"{from_id}|{to_id}|{mode.value}"
    
    def _get_from_cache(self, from_id: str, to_id: str, mode: TravelMode) -> Optional[Transfer]:
        """캐시에서 Transfer 조회"""
        key = self._get_cache_key(from_id, to_id, mode)
        return self._cache.get(key)
    
    def _save_to_cache(self, transfer: Transfer) -> None:
        """Transfer를 캐시에 저장"""
        key = self._get_cache_key(
            transfer.from_poi_id, 
            transfer.to_poi_id, 
            transfer.travel_mode
        )
        self._cache[key] = transfer
    
    def clear_cache(self) -> None:
        """캐시 초기화"""
        self._cache.clear()
    
    def get_cache_size(self) -> int:
        """현재 캐시 크기 반환"""
        return len(self._cache)
    
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
        cached = self._get_from_cache(from_poi.id, to_poi.id, mode)
        if cached:
            return cached
        
        # API 호출
        transfer = await self._call_directions_api(from_poi, to_poi, mode)
        
        # 캐시 저장
        self._save_to_cache(transfer)
        
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
        
        transfers = []
        tasks = []
        
        for i in range(len(pois) - 1):
            from_poi = pois[i]
            to_poi = pois[i + 1]
            
            # 캐시 확인
            cached = self._get_from_cache(from_poi.id, to_poi.id, mode)
            if cached:
                transfers.append((i, cached))
            else:
                # API 호출 태스크 생성
                tasks.append((i, self.calculate(from_poi, to_poi, mode)))
        
        # 캐시 미스된 것들만 병렬 API 호출
        if tasks:
            results = await asyncio.gather(*[task for _, task in tasks])
            for (idx, _), result in zip(tasks, results):
                transfers.append((idx, result))
        
        # 인덱스 순서로 정렬
        transfers.sort(key=lambda x: x[0])
        
        return [transfer for _, transfer in transfers]
