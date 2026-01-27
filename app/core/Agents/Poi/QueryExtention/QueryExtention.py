from typing import List
from app.core.LLMClient.BaseLlmClient import BaseLLMClient
from app.core.models.LlmClientDataclass.ChatMessageDataclass import ChatMessage, MessageData
from app.core.Agents.Poi.QueryExtention.BaseKeywordExtractor import BaseKeywordExtractor


KEYWORD_EXTRACTION_PROMPT = """당신은 여행 키워드 추출 전문가입니다.

다음 여행자 페르소나를 분석하여 이 여행자가 좋아할 만한 POI 검색 키워드를 추출해주세요.

<persona>
{persona}
</persona>

지침:
- 페르소나의 여행 스타일, 취향, 예산, 동행인 등을 고려
- 여행지 (도시명)을 포함한 구체적인 검색어 생성
- 5-10개의 검색 키워드 생성
- 맛집, 카페, 관광지, 쇼핑 등 다양한 카테고리 포함

응답 형식:
<keywords>
<keyword>서울 혼밥 맛집</keyword>
<keyword>강남 로컬 카페</keyword>
<keyword>홍대 인스타 감성 카페</keyword>
</keywords>
"""


class QueryExtension(BaseKeywordExtractor):
    """페르소나 기반 여행 키워드 추출 모듈"""
    
    def __init__(self, llm_client: BaseLLMClient):
        self.llm = llm_client
    
    async def extract_keywords(self, persona_summary: str) -> List[str]:
        """
        페르소나에서 여행 키워드 추출
        
        Args:
            persona_summary: 여행자 페르소나 요약
            
        Returns:
            추출된 검색 키워드 리스트
        """
        if not persona_summary:
            return []
        
        prompt = KEYWORD_EXTRACTION_PROMPT.format(persona=persona_summary)
        
        messages = ChatMessage(content=[
            MessageData(role="user", content=prompt)
        ])
        
        response = await self.llm.call_llm(messages)
        
        # XML 태그에서 키워드 추출
        keywords = self._parse_keywords(response)
        
        return keywords
    
    def _parse_keywords(self, response: str) -> List[str]:
        """LLM 응답에서 키워드 추출"""
        import re
        
        keywords = []
        pattern = r"<keyword>(.*?)</keyword>"
        matches = re.findall(pattern, response, re.DOTALL)
        
        for match in matches:
            cleaned = match.strip()
            if cleaned:
                keywords.append(cleaned)
        
        return keywords
