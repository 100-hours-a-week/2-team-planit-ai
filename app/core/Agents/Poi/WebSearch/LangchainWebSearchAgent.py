import asyncio
import os
from typing import List, Optional
from urllib.parse import urlparse

from langchain_tavily import TavilySearch
from app.core.Agents.Poi.WebSearch.BaseWebSearchAgent import BaseWebSearchAgent
from app.core.models.PoiAgentDataclass.poi import PoiSearchResult, PoiSource
from app.core.config import settings


class LangchainWebSearchAgent(BaseWebSearchAgent):
    """
    LangChain 기반 웹 검색 에이전트
    
    langchain_tavily의 TavilySearch Tool을 사용하여
    POI 정보를 검색합니다.
    """
    
    def __init__(self, max_results: int = 10):
        """
        Args:
            max_results: 기본 최대 결과 수
        """
        self.max_results = max_results
        self.api_key = settings.tavily_api_key
        
        # LangChain이 환경변수에서 API 키를 찾도록 설정
        if self.api_key:
            os.environ["TAVILY_API_KEY"] = self.api_key
        
        self.tool = TavilySearch(max_results=max_results)

    def _extract_title_from_url(self, url: str) -> str:
        """URL에서 제목 추출 (제목이 없는 경우의 fallback)"""
        if not url:
            return "Untitled"
        try:
            parsed = urlparse(url)
            path = parsed.path
            if not path or path == "/":
                return parsed.netloc
            return path.split("/")[-1].replace("-", " ").replace("_", " ").title()
        except Exception:
            return url
    
    async def search(self, query: str, num_results: int = 10) -> List[PoiSearchResult]:
        """
        단일 쿼리로 웹 검색 실행
        
        Args:
            query: 검색 쿼리
            num_results: 반환할 결과 수
            
        Returns:
            검색 결과 리스트
        """
        if not query:
            return []
            
        try:
            # max_results가 다르면 새 Tool 생성
            tool = self.tool
            if num_results != self.max_results:
                tool = TavilySearch(max_results=num_results)
            
            # TavilySearch.ainvoke()는 비동기 함수이며 리스트를 반환합니다.
            raw_results = await tool.ainvoke(query)
            
            # 결과가 리스트인지 확인 (API 버전에 따라 다름)
            results_list = []
            if isinstance(raw_results, list):
                results_list = raw_results
            elif isinstance(raw_results, dict) and 'results' in raw_results:
                results_list = raw_results['results']
            
            results = []
            for item in results_list:
                # 제목이 없으면 URL에서 추출
                title = item.get("title") or item.get("name")
                if not title and item.get("url"):
                    title = self._extract_title_from_url(item.get("url"))
                
                result = PoiSearchResult(
                    title=title or "Untitled POI",
                    snippet=item.get("content") or item.get("snippet") or "",
                    url=item.get("url", ""),
                    source=PoiSource.WEB_SEARCH,
                    relevance_score=item.get("score", 0.0)
                )
                results.append(result)
            
            return results
            
        except Exception as e:
            print(f"LangChain web search error: {e}")
            return []
    
    async def search_multiple(
        self, 
        queries: List[str], 
        num_results_per_query: int = 5
    ) -> List[PoiSearchResult]:
        """
        여러 쿼리로 병렬 검색 후 결과 병합
        
        Args:
            queries: 검색 쿼리 리스트
            num_results_per_query: 쿼리당 결과 수
            
        Returns:
            병합된 검색 결과 리스트
        """
        if not queries:
            return []
        
        # 병렬 검색 실행
        tasks = [
            self.search(query, num_results_per_query) 
            for query in queries
        ]
        results_list = await asyncio.gather(*tasks)
        
        # 결과 병합 및 중복 제거 (URL 기준)
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
