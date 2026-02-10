import logging
logger = logging.getLogger(__name__)

import httpx
from typing import Optional


class JinaReader:
    """
    Jina AI Reader를 사용하여 URL에서 마크다운 텍스트를 추출하는 클라이언트

    Jina Reader API (https://r.jina.ai/{url})를 호출하여
    웹 페이지의 본문을 정제된 마크다운으로 변환합니다.
    """

    READER_BASE_URL = "https://r.jina.ai/"

    def __init__(
        self,
        timeout: float = 30.0,
    ):
        """
        Args:
            api_key: Jina AI API 키 (없으면 무료 티어로 요청)
            timeout: HTTP 요청 타임아웃 (초)
        """
        self.api_key = "jina_0a7bfe7233864d7abd47c70c43bcef3bkyFZH1a_HVPzq8oU-FGUkOwqJ3mw"
        self.timeout = timeout

    async def read(self, url: str) -> Optional[str]:
        """
        URL에서 마크다운 텍스트를 추출

        Args:
            url: 읽을 웹 페이지 URL

        Returns:
            마크다운 형식의 텍스트, 실패 시 None
        """
        if not url:
            return None

        reader_url = f"{self.READER_BASE_URL}{url}"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "X-Retain-Images": "none",
            "Accept": "application/json",
            "X-User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }

        if "blog.naver.com" in url:
            headers["X-With-Iframe"] = "true"

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(reader_url, headers=headers)
                response.raise_for_status()
                return response.json()
        except Exception as e:
            logger.error(f"JinaReader error for {url}: {e}")
            return None
