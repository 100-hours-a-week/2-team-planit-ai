import logging
from typing import List, Optional

from sentence_transformers import CrossEncoder

from app.core.models.PoiAgentDataclass.poi import PoiSearchResult
from app.core.Agents.Poi.Reranker.BaseReranker import BaseReranker


logger = logging.getLogger(__name__)


class CrossEncoderReranker(BaseReranker):
    """
    HuggingFace CrossEncoder 기반 리랭커
    
    페르소나와 POI 간의 관련도를 CrossEncoder 모델로 재계산합니다.
    기존 LLM 기반 리랭커 대비 비용 절감 및 지연 시간 단축.
    """
    
    def __init__(
        self,
        model_name: str = "cross-encoder/ms-marco-MiniLM-L6-v2",
        min_score: float = 0.5
    ):
        """
        Args:
            model_name: HuggingFace CrossEncoder 모델명
                - cross-encoder/ms-marco-MiniLM-L6-v2 (기본값, 균형)
                - cross-encoder/ms-marco-TinyBERT-L-2-v2 (빠름)
                - cross-encoder/ms-marco-MiniLM-L-12-v2 (정확도 높음)
            min_score: 최소 점수 임계값 (이하는 필터링)
        """
        self.min_score = min_score
        self._model_name = model_name
        self._model: Optional[CrossEncoder] = None
    
    def _get_model(self) -> CrossEncoder:
        """지연 로딩으로 모델 초기화"""
        if self._model is None:
            logger.info(f"CrossEncoder 모델 로딩: {self._model_name}")
            self._model = CrossEncoder(self._model_name)
        return self._model
    
    async def rerank(
        self, results: List[PoiSearchResult], persona_summary: str
    ) -> List[PoiSearchResult]:
        """
        검색 결과를 CrossEncoder로 리랭킹
        
        Args:
            results: 검색 결과 리스트
            persona_summary: 여행자 페르소나 요약
            
        Returns:
            리랭킹된 결과 (min_score 이상만 포함)
        """
        if not results:
            return []
        
        model = self._get_model()
        
        # (query, document) 쌍 생성
        pairs = [
            (persona_summary, f"{r.title}. {r.snippet}") 
            for r in results
        ]
        
        # CrossEncoder로 점수 계산
        scores = model.predict(pairs)
        
        # 점수 업데이트
        scored = []
        for result, score in zip(results, scores):
            result_copy = result.model_copy()
            result_copy.relevance_score = float(score)
            scored.append(result_copy)
        
        # 점수순 정렬
        scored.sort(key=lambda x: x.relevance_score, reverse=True)
        
        # 최소 점수 필터링
        filtered = [r for r in scored if r.relevance_score >= self.min_score]
        
        logger.info(f"CrossEncoder 리랭킹: {len(results)}개 → {len(filtered)}개 (min_score={self.min_score})")
        
        return filtered
    
    async def rerank_batch(
        self,
        web_results: List[PoiSearchResult],
        embedding_results: List[PoiSearchResult],
        persona_summary: str
    ) -> tuple[List[PoiSearchResult], List[PoiSearchResult]]:
        """
        웹 검색 결과와 임베딩 검색 결과를 동시에 리랭킹
        
        Args:
            web_results: 웹 검색 결과 리스트
            embedding_results: 임베딩 검색 결과 리스트
            persona_summary: 여행자 페르소나 요약
            
        Returns:
            (리랭킹된 웹 결과, 리랭킹된 임베딩 결과) 튜플
        """
        reranked_web = await self.rerank(web_results, persona_summary)
        reranked_embedding = await self.rerank(embedding_results, persona_summary)
        return reranked_web, reranked_embedding
