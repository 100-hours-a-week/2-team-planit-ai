from typing import List, Dict, Optional
from app.core.models.PoiAgentDataclass.poi import PoiSearchResult, PoiSource, PoiSearchStats


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
        stats: Optional[PoiSearchStats] = None
    ) -> List[PoiSearchResult]:
        """
        웹 검색과 임베딩 검색 결과를 병합
        
        Args:
            web_results: 웹 검색 결과
            embedding_results: 임베딩 검색 결과
            stats: 통계 수집용 dict (선택적)
            
        Returns:
            병합되고 정렬된 결과 리스트
        """
        # 가중치 적용된 점수 계산
        scored_results: Dict[str, PoiSearchResult] = {}
        
        # 중복 통계
        web_dup_count = 0
        emb_dup_count = 0
        web_dup_names: List[str] = []
        emb_dup_names: List[str] = []
        merge_dup_pairs: List[Dict[str, str]] = []
        
        # 웹 검색 결과 처리
        for result in web_results:
            key = self._get_result_key(result)
            weighted_score = result.relevance_score * self.web_weight
            
            if key in scored_results:
                # 중복 시 점수 합산
                existing = scored_results[key]
                existing.relevance_score += weighted_score
                web_dup_count += 1
                web_dup_names.append(result.title)
                # 중복 POI의 title과 기존 항목의 poi_id를 기록
                existing_poi_id = existing.poi_id or ""
                if existing_poi_id:
                    merge_dup_pairs.append({"title": result.title, "poi_id": existing_poi_id})
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
                emb_dup_count += 1
                emb_dup_names.append(result.title)
                # 중복 POI의 title과 기존 항목의 poi_id를 기록
                existing_poi_id = existing.poi_id or ""
                if existing_poi_id:
                    merge_dup_pairs.append({"title": result.title, "poi_id": existing_poi_id})
            else:
                result_copy = result.model_copy()
                result_copy.relevance_score = weighted_score
                scored_results[key] = result_copy
        
        # 점수순 정렬
        merged = list(scored_results.values())
        merged.sort(key=lambda x: x.relevance_score, reverse=True)
        
        # 통계 수집: 병합 중복 제거
        if stats is not None:
            stats["merge_web_dup_count"] = web_dup_count
            stats["merge_emb_dup_count"] = emb_dup_count
            stats["merge_total_dup_count"] = web_dup_count + emb_dup_count
            stats["merge_web_dup_names"] = web_dup_names
            stats["merge_emb_dup_names"] = emb_dup_names
            stats["merge_dup_pairs"] = merge_dup_pairs
        
        return merged
    
    def _get_result_key(self, result: PoiSearchResult) -> str:
        """결과 중복 체크용 키 생성"""
        if result.poi_id:
            return f"poi:{result.poi_id}"
        if result.url:
            return f"url:{result.url}"
        return f"title:{result.title}"
