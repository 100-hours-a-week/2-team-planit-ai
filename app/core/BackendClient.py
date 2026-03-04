"""
BackendClient: 백엔드 서버 통신 클라이언트

여행 일정 백엔드 API와 통신합니다:
- GET /trips/{tripId}/itineraries: 일정 조회
- PATCH /trips/itineraries/days: 일정 수정
"""
import logging
from typing import Optional

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)

# 기본 타임아웃 (초)
DEFAULT_TIMEOUT = 30.0


class BackendClient:
    """백엔드 서버 HTTP 클라이언트

    httpx.AsyncClient를 사용하여 백엔드 API를 호출합니다.
    모든 요청에 userJWT를 Authorization 헤더에 포함합니다.
    """

    def __init__(self, base_url: Optional[str] = None):
        """
        Args:
            base_url: 백엔드 서버 베이스 URL. None이면 settings에서 가져옴.
        """
        self.base_url = (base_url or settings.backend_base_url).rstrip("/")

    def _build_headers(self, user_jwt: str) -> dict:
        """인증 헤더 생성"""
        return {
            "Authorization": f"Bearer {user_jwt}",
            "Content-Type": "application/json",
        }

    async def get_itineraries(self, trip_id: int, user_jwt: str) -> dict:
        """일정 조회

        GET /trips/{tripId}/itineraries

        Args:
            trip_id: 여행 ID
            user_jwt: 사용자 JWT 토큰

        Returns:
            dict: 백엔드 응답 데이터 (ResponseSchema 형태)

        Raises:
            httpx.HTTPStatusError: HTTP 에러 응답 시
        """
        url = f"{self.base_url}/trips/{trip_id}/itineraries"
        headers = self._build_headers(user_jwt)

        logger.info(f"일정 조회 요청: GET {url}")

        async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT) as client:
            response = await client.get(url, headers=headers)
            response.raise_for_status()
            data = response.json()

        logger.info(
            f"일정 조회 완료: tripId={trip_id}, "
            f"itineraries={len(data.get('data', {}).get('itineraries', []))}일"
        )
        return data

    async def update_day_itinerary(
        self,
        trip_id: int,
        day_id: int,
        places: list[dict],
        user_jwt: str,
    ) -> dict:
        """일정 수정 (특정 일차)

        PATCH /trips/itineraries/days

        Args:
            trip_id: 여행 ID
            day_id: itineraryDayId (백엔드에서 할당한 일차 ID)
            places: 수정할 장소 목록 (PATCH body 형식)
            user_jwt: 사용자 JWT 토큰

        Returns:
            dict: 백엔드 응답 데이터

        Raises:
            httpx.HTTPStatusError: HTTP 에러 응답 시
        """
        url = f"{self.base_url}/trips/itineraries/days"
        headers = self._build_headers(user_jwt)
        body = {
            "tripId": trip_id,
            "dayId": day_id,
            "places": places,
        }

        logger.info(
            f"일정 수정 요청: PATCH {url}, "
            f"tripId={trip_id}, dayId={day_id}, places={len(places)}건"
        )

        async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT) as client:
            response = await client.patch(url, headers=headers, json=body)
            response.raise_for_status()
            data = response.json()

        logger.info(f"일정 수정 완료: tripId={trip_id}, dayId={day_id}")
        return data
