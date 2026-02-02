"""
POI 매핑을 위한 추상 베이스 클래스

POI 정보를 외부 API를 통해 검증하고 PoiData로 변환하는 인터페이스 정의
"""
from abc import ABC, abstractmethod
from typing import List, Optional

from app.core.models.PoiAgentDataclass.poi import PoiInfo, PoiData


class BasePoiMapper(ABC):
    """POI 매핑 추상 클래스
    
    PoiInfo를 외부 API(예: Google Maps)를 통해 검증하고
    실제 존재하는 장소인 경우 PoiData로 변환합니다.
    """
    
    @abstractmethod
    async def map_poi(
        self, 
        poi_info: PoiInfo, 
        city: str
    ) -> Optional[PoiData]:
        """
        단일 POI 정보를 검증하고 PoiData로 매핑
        
        Args:
            poi_info: 변환할 POI 정보
            city: 검색 컨텍스트로 사용할 도시명
            
        Returns:
            검증 성공 시 PoiData, 실패 시 None
        """
        pass
    
    @abstractmethod
    async def map_pois_batch(
        self, 
        poi_infos: List[PoiInfo], 
        city: str
    ) -> List[PoiData]:
        """
        여러 POI를 배치로 매핑
        
        Args:
            poi_infos: 변환할 POI 정보 리스트
            city: 검색 컨텍스트로 사용할 도시명
            
        Returns:
            검증에 성공한 PoiData 리스트 (실패한 POI는 제외)
        """
        pass
