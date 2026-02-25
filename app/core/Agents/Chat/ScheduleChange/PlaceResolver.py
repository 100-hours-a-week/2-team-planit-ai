"""
PlaceResolver: 사용자가 요청한 장소를 DB에서 검증하는 모듈

검색 흐름:
1. SQLite(PoiAliasCache)에서 장소 이름으로 google_place_id 조회
2. 성공 시 VectorDB(ChromaDB)에서 google_place_id로 상세 PoiData 조회
3. Google Maps API fallback은 확장 가능하도록 구조만 준비
"""
import logging
from dataclasses import dataclass, field
from typing import Optional

from app.core.Agents.Poi.PoiAliasCache import PoiAliasCache
from app.core.Agents.Poi.VectorDB.VectorSearchAgent import VectorSearchAgent
from app.core.models.PoiAgentDataclass.poi import PoiData

logger = logging.getLogger(__name__)


@dataclass
class ResolvedPlace:
    """검증된 장소 정보"""
    place_name: str                         # 검색에 사용된 장소 이름
    google_place_id: Optional[str] = None   # Google Place ID (SQLite 히트 시)
    source: str = "unknown"                 # "sqlite" | "vectordb" | "google_maps"
    is_found: bool = False                  # 검색 성공 여부
    poi_data: Optional[PoiData] = None      # VectorDB에서 가져온 상세 데이터

    def to_dict(self) -> dict:
        """ChatState 저장용 dict 변환"""
        result = {
            "place_name": self.place_name,
            "google_place_id": self.google_place_id,
            "source": self.source,
            "is_found": self.is_found,
        }

        # PoiData가 있으면 주요 필드 포함
        if self.poi_data:
            result["poi_detail"] = {
                "id": self.poi_data.id,
                "name": self.poi_data.name,
                "category": self.poi_data.category.value,
                "description": self.poi_data.description,
                "address": self.poi_data.address,
                "latitude": self.poi_data.latitude,
                "longitude": self.poi_data.longitude,
                "google_maps_uri": self.poi_data.google_maps_uri,
                "google_rating": self.poi_data.google_rating,
                "types": self.poi_data.types,
                "primary_type": self.poi_data.primary_type,
            }

        return result


class PlaceResolver:
    """장소 검증 모듈

    검색 순서:
    1. PoiAliasCache (SQLite) — find_by_name()으로 google_place_id 조회
    2. VectorSearchAgent (ChromaDB) — google_place_id로 상세 PoiData 조회
    3. (향후 확장) Google Maps API — 실시간 검색

    기존 코드는 수정 없이 import하여 호출만 합니다.
    """

    def __init__(
        self,
        poi_alias_cache: Optional[PoiAliasCache] = None,
        vector_search_agent: Optional[VectorSearchAgent] = None,
    ):
        """
        Args:
            poi_alias_cache: PoiAliasCache 인스턴스 (None이면 기본 생성)
            vector_search_agent: VectorSearchAgent 인스턴스 (None이면 VectorDB 조회 스킵)
        """
        self._alias_cache = poi_alias_cache or PoiAliasCache()
        self._vector_agent = vector_search_agent

    async def resolve(
        self,
        place_name: str,
        city: str = "",
    ) -> ResolvedPlace:
        """장소 이름으로 DB 검색

        Args:
            place_name: 검색할 장소 이름
            city: 도시 이름 (필터링용)

        Returns:
            ResolvedPlace: 검증 결과 (상세 PoiData 포함 가능)
        """
        # 1단계: SQLite (PoiAliasCache) 검색
        resolved = await self._search_sqlite(place_name, city)
        if not resolved.is_found:
            # 향후 Google Maps API fallback 위치
            logger.info(f"장소를 찾지 못함: '{place_name}' (city='{city}')")
            return resolved

        logger.info(
            f"SQLite에서 장소 발견: '{place_name}' → "
            f"place_id={resolved.google_place_id}"
        )

        # 2단계: VectorDB에서 상세 데이터 조회
        if resolved.google_place_id and self._vector_agent:
            enriched = await self._enrich_from_vectordb(
                resolved, city
            )
            return enriched

        return resolved

    async def _search_sqlite(
        self,
        place_name: str,
        city: str,
    ) -> ResolvedPlace:
        """PoiAliasCache (SQLite)에서 장소 검색"""
        try:
            place_id = await self._alias_cache.find_by_name(
                name=place_name,
                city=city,
            )

            if place_id:
                return ResolvedPlace(
                    place_name=place_name,
                    google_place_id=place_id,
                    source="sqlite",
                    is_found=True,
                )

            return ResolvedPlace(
                place_name=place_name,
                source="sqlite",
                is_found=False,
            )

        except Exception as e:
            logger.error(f"SQLite 검색 실패: {e}")
            return ResolvedPlace(
                place_name=place_name,
                source="sqlite",
                is_found=False,
            )

    async def _enrich_from_vectordb(
        self,
        resolved: ResolvedPlace,
        city: str,
    ) -> ResolvedPlace:
        """VectorDB에서 google_place_id로 상세 PoiData 조회

        SQLite에서 찾은 google_place_id를 이용하여
        ChromaDB에 저장된 상세 데이터(카테고리, 설명, 좌표, 평점 등)를 가져옵니다.
        """
        try:
            poi_data = await self._vector_agent.find_by_google_place_id(
                google_place_id=resolved.google_place_id,
                city_filter=city or None,
            )

            if poi_data:
                resolved.poi_data = poi_data
                resolved.source = "vectordb"
                logger.info(
                    f"VectorDB에서 상세 데이터 조회 성공: '{resolved.place_name}' "
                    f"(category={poi_data.category}, rating={poi_data.google_rating})"
                )
            else:
                logger.info(
                    f"VectorDB에 상세 데이터 없음: "
                    f"place_id={resolved.google_place_id} (SQLite 정보만 사용)"
                )

        except Exception as e:
            logger.error(f"VectorDB 조회 실패: {e} (SQLite 정보만 사용)")

        return resolved

    async def _search_google_maps(
        self,
        place_name: str,
        city: str,
    ) -> ResolvedPlace:
        """Google Maps API로 장소 검색 (향후 확장용)

        TODO: GoogleMapsPoiMapper를 활용하여 실시간 검색 구현
        """
        raise NotImplementedError(
            "Google Maps API 검색은 아직 구현되지 않았습니다. "
            "향후 GoogleMapsPoiMapper를 활용하여 구현 예정."
        )
