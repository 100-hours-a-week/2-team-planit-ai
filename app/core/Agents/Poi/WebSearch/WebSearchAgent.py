import asyncio
from typing import List, Optional
from tavily import TavilyClient

from app.core.Agents.Poi.WebSearch.BaseWebSearchAgent import BaseWebSearchAgent
from app.core.models.PoiAgentDataclass.poi import PoiSearchResult, PoiSource
from app.core.config import settings


class WebSearchAgent(BaseWebSearchAgent):
    """
    웹 검색 에이전트 구현
    
    Tavily API를 사용하여 POI 정보를 검색합니다.
    다른 API로 교체 시 이 클래스만 수정하면 됩니다.
    """
    
    def __init__(
        self, 
        api_key: Optional[str] = None,
        base_url: str = "https://api.tavily.com"
    ):
        self.api_key = api_key or getattr(settings, 'tavily_api_key', None)
        self.base_url = base_url
        if not self.api_key:
            raise ValueError("API 키가 없습니다.")
        self.client = TavilyClient(api_key=self.api_key)
        
    async def search(self, query: str, num_results: int = 10) -> List[PoiSearchResult]:
        """
        단일 쿼리로 웹 검색 실행
        """

        if query is None or query == "":
            return []

        try:
            response = self.client.search(
                query=query,
                max_results=num_results,
                include_answer=False,
                search_depth="basic"
            )
            
            results = []
            for item in response.get("results", []):
                result = PoiSearchResult(
                    title=item.get("title", ""),
                    snippet=item.get("content", ""),
                    url=item.get("url"),
                    source=PoiSource.WEB_SEARCH,
                    relevance_score=item.get("score", 0.0)
                )
                results.append(result)
            
            return results
                
        except Exception as e:
            # 검색 실패 시 빈 결과 반환 (전체 흐름 중단 방지)
            print(f"Web search error: {e}")
            return []
    
    async def search_multiple(
        self, 
        queries: List[str], 
        num_results_per_query: int = 5
    ) -> List[PoiSearchResult]:
        """
        여러 쿼리로 병렬 검색 후 결과 병합
        """
        if not queries:
            return []
        
        # 병렬 검색 실행
        tasks = [
            self.search(query, num_results_per_query) 
            for query in queries
        ]
        results_list = await asyncio.gather(*tasks)
        
        # 결과 병합 및 중복 제거
        seen_urls = set()
        merged_results = []
        
        for results in results_list:
            for result in results:
                if result.url and result.url not in seen_urls:
                    seen_urls.add(result.url)
                    merged_results.append(result)
                elif not result.url:
                    merged_results.append(result)
        
        # 관련도 점수로 정렬
        merged_results.sort(key=lambda x: x.relevance_score, reverse=True)
        
        return merged_results
