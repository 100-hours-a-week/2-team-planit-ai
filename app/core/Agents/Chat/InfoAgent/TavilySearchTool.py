"""
TavilySearchTool: Tavily API를 활용한 인터넷 검색 도구

여행 정보, 장소 정보 등을 인터넷에서 검색하여 반환합니다.
settings.tavily_api_key를 사용합니다.
"""
import logging
from typing import List, Optional
from dataclasses import dataclass, field

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)

TAVILY_SEARCH_URL = "https://api.tavily.com/search"


@dataclass
class TavilySearchResult:
    """Tavily 검색 결과 단건"""
    title: str
    url: str
    content: str
    score: float = 0.0


@dataclass
class TavilySearchResponse:
    """Tavily 검색 응답"""
    query: str
    results: List[TavilySearchResult] = field(default_factory=list)
    answer: Optional[str] = None


class TavilySearchTool:
    """Tavily API 기반 인터넷 검색 도구

    여행 관련 정보를 웹에서 검색합니다.
    Tavily API는 AI 에이전트에 최적화된 검색 API로,
    관련도 높은 결과와 자동 요약을 제공합니다.
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        timeout: int = 30,
        max_results: int = 5,
    ):
        """
        Args:
            api_key: Tavily API 키 (None이면 settings에서 가져옴)
            timeout: HTTP 요청 타임아웃 (초)
            max_results: 검색 결과 최대 개수
        """
        self._api_key = api_key or settings.tavily_api_key
        self._timeout = timeout
        self._max_results = max_results

        if not self._api_key:
            logger.warning("Tavily API 키가 설정되지 않았습니다.")

    async def search(
        self,
        query: str,
        search_depth: str = "basic",
        include_answer: bool = True,
        max_results: Optional[int] = None,
    ) -> TavilySearchResponse:
        """Tavily API로 검색 수행

        Args:
            query: 검색 쿼리
            search_depth: 검색 깊이 ("basic" 또는 "advanced")
            include_answer: AI 생성 답변 포함 여부
            max_results: 결과 최대 개수 (None이면 기본값 사용)

        Returns:
            TavilySearchResponse: 검색 결과
        """
        if not self._api_key:
            logger.error("Tavily API 키가 없어 검색을 수행할 수 없습니다.")
            return TavilySearchResponse(query=query)

        request_data = {
            "api_key": self._api_key,
            "query": query,
            "search_depth": search_depth,
            "include_answer": include_answer,
            "max_results": max_results or self._max_results,
        }

        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                response = await client.post(
                    TAVILY_SEARCH_URL,
                    json=request_data,
                )

                if response.status_code != 200:
                    logger.error(
                        f"Tavily API 오류 (HTTP {response.status_code}): "
                        f"{response.text}"
                    )
                    return TavilySearchResponse(query=query)

                data = response.json()

                results = [
                    TavilySearchResult(
                        title=item.get("title", ""),
                        url=item.get("url", ""),
                        content=item.get("content", ""),
                        score=item.get("score", 0.0),
                    )
                    for item in data.get("results", [])
                ]

                return TavilySearchResponse(
                    query=query,
                    results=results,
                    answer=data.get("answer"),
                )

        except httpx.TimeoutException:
            logger.error(f"Tavily API 타임아웃: query='{query}'")
            return TavilySearchResponse(query=query)

        except httpx.RequestError as e:
            logger.error(f"Tavily API 요청 실패: {e}")
            return TavilySearchResponse(query=query)

    async def search_multiple(
        self,
        queries: List[str],
        search_depth: str = "basic",
        include_answer: bool = False,
    ) -> List[TavilySearchResponse]:
        """여러 쿼리를 순차 검색

        Args:
            queries: 검색 쿼리 리스트
            search_depth: 검색 깊이
            include_answer: AI 생성 답변 포함 여부

        Returns:
            List[TavilySearchResponse]: 쿼리별 검색 결과
        """
        results = []
        for query in queries:
            result = await self.search(
                query=query,
                search_depth=search_depth,
                include_answer=include_answer,
            )
            results.append(result)
        return results

    def format_results_as_text(
        self, response: TavilySearchResponse
    ) -> str:
        """검색 결과를 LLM에 전달할 텍스트로 포맷

        Args:
            response: Tavily 검색 응답

        Returns:
            str: 포맷된 텍스트
        """
        if not response.results:
            return f"'{response.query}'에 대한 검색 결과가 없습니다."

        lines = [f"검색 쿼리: {response.query}"]

        if response.answer:
            lines.append(f"\n요약: {response.answer}")

        lines.append(f"\n검색 결과 ({len(response.results)}건):")
        for i, result in enumerate(response.results, 1):
            lines.append(f"\n[{i}] {result.title}")
            lines.append(f"    URL: {result.url}")
            lines.append(f"    내용: {result.content[:300]}")

        return "\n".join(lines)
