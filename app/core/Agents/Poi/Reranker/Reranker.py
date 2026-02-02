from typing import List
from app.core.LLMClient.BaseLlmClient import BaseLLMClient
from app.core.models.LlmClientDataclass.ChatMessageDataclass import ChatMessage, MessageData
from app.core.models.PoiAgentDataclass.poi import PoiSearchResult
from app.core.Agents.Poi.Reranker.BaseReranker import BaseReranker


RERANK_PROMPT = """당신은 여행 POI 관련도 평가 전문가입니다.

다음 여행자 페르소나와 검색 결과를 분석하여 관련도 점수(0.0~1.0)를 매겨주세요.

<persona>
{persona}
</persona>

<search_results>
{results}
</search_results>

각 검색 결과에 대해 페르소나와의 관련도를 평가해주세요.
- 페르소나의 취향, 예산, 여행 스타일과 얼마나 맞는지
- 높은 점수일수록 해당 여행자에게 적합

응답 형식 (검색 결과 ID 순서대로):
<scores>
<score id="1">0.85</score>
<score id="2">0.72</score>
...
</scores>
"""


class Reranker(BaseReranker):
    """
    검색 결과를 페르소나 기반으로 리랭킹하는 모듈
    """
    
    def __init__(self, llm_client: BaseLLMClient, top_n: int = 10):
        """
        Args:
            llm_client: LLM 클라이언트
            top_n: 리랭킹 후 반환할 상위 결과 수
        """
        self.llm = llm_client
        self.top_n = top_n
    
    async def rerank(
        self, 
        results: List[PoiSearchResult], 
        persona_summary: str
    ) -> List[PoiSearchResult]:
        """
        검색 결과를 페르소나 기반으로 리랭킹
        
        Args:
            results: 검색 결과 리스트
            persona_summary: 여행자 페르소나 요약
            
        Returns:
            리랭킹된 상위 n개 결과
        """
        if not results:
            return []
        
        if len(results) <= self.top_n:
            # 결과가 top_n 이하면 그대로 반환
            return results
        
        # 검색 결과를 텍스트로 변환
        results_text = self._format_results(results)
        
        prompt = RERANK_PROMPT.format(
            persona=persona_summary,
            results=results_text
        )
        
        messages = ChatMessage(content=[
            MessageData(role="user", content=prompt)
        ])
        
        try:
            response = await self.llm.call_llm(messages)
            scores = self._parse_scores(response, len(results))
            
            # 점수로 결과 정렬
            scored_results = list(zip(results, scores))
            scored_results.sort(key=lambda x: x[1], reverse=True)
            
            # 상위 n개만 반환, 점수 업데이트
            reranked = []
            for result, score in scored_results[:self.top_n]:
                result_copy = result.model_copy()
                result_copy.relevance_score = score
                reranked.append(result_copy)
            
            return reranked
            
        except Exception as e:
            print(f"Reranking error: {e}")
            # 에러 시 원본 상위 n개 반환
            return results[:self.top_n]
    
    def _format_results(self, results: List[PoiSearchResult]) -> str:
        """검색 결과를 텍스트 형식으로 변환"""
        lines = []
        for i, result in enumerate(results, 1):
            lines.append(f'<result id="{i}">')
            lines.append(f"  <title>{result.title}</title>")
            lines.append(f"  <content>{result.snippet[:200]}</content>")
            lines.append("</result>")
        return "\n".join(lines)
    
    def _parse_scores(self, response: str, count: int) -> List[float]:
        """LLM 응답에서 점수 파싱"""
        import re
        
        scores = [0.0] * count
        pattern = r'<score id="(\d+)">([\d.]+)</score>'
        matches = re.findall(pattern, response)
        
        for id_str, score_str in matches:
            try:
                idx = int(id_str) - 1
                score = float(score_str)
                if 0 <= idx < count:
                    scores[idx] = min(max(score, 0.0), 1.0)
            except ValueError:
                continue
        
        return scores

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

