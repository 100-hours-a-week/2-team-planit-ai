from typing import List, Dict
from app.core.models.PoiAgentDataclass.poi import PoiSearchResult, PoiSource


class ResultMerger:
    """
    웹 검색과 임베딩 검색 결과를 병합하는 모듈
    """
    
    def __init__(
        self,
        web_weight: float = 0.6,
        embedding_weight: float = 0.4
    ):
        """
        Args:
            web_weight: 웹 검색 결과 가중치
            embedding_weight: 임베딩 검색 결과 가중치
        """
        self.web_weight = web_weight
        self.embedding_weight = embedding_weight
    
    def merge(
        self,
        web_results: List[PoiSearchResult],
        embedding_results: List[PoiSearchResult],
        max_results: int = 20
    ) -> List[PoiSearchResult]:
        """
        웹 검색과 임베딩 검색 결과를 병합
        
        Args:
            web_results: 웹 검색 결과
            embedding_results: 임베딩 검색 결과
            max_results: 최대 반환 결과 수
            
        Returns:
            병합되고 정렬된 결과 리스트
        """
        # 가중치 적용된 점수 계산
        scored_results: Dict[str, PoiSearchResult] = {}
        
        # 웹 검색 결과 처리
        for result in web_results:
            key = self._get_result_key(result)
            weighted_score = result.relevance_score * self.web_weight
            
            if key in scored_results:
                # 중복 시 점수 합산
                existing = scored_results[key]
                existing.relevance_score += weighted_score
            else:
                result_copy = result.model_copy()
                result_copy.relevance_score = weighted_score
                scored_results[key] = result_copy
        
        # 임베딩 검색 결과 처리
        for result in embedding_results:
            key = self._get_result_key(result)
            weighted_score = result.relevance_score * self.embedding_weight
            
            if key in scored_results:
                existing = scored_results[key]
                existing.relevance_score += weighted_score
                # 임베딩 결과가 있으면 poi_id 업데이트
                if result.poi_id:
                    existing.poi_id = result.poi_id
            else:
                result_copy = result.model_copy()
                result_copy.relevance_score = weighted_score
                scored_results[key] = result_copy
        
        # 점수순 정렬
        merged = list(scored_results.values())
        merged.sort(key=lambda x: x.relevance_score, reverse=True)
        
        return merged[:max_results]
    
    def _get_result_key(self, result: PoiSearchResult) -> str:
        """결과 중복 체크용 키 생성"""
        # URL이 있으면 URL 기반, 없으면 제목 기반
        if result.url:
            return result.url
        if result.poi_id:
            return f"poi:{result.poi_id}"
        return f"title:{result.title.lower()}"
