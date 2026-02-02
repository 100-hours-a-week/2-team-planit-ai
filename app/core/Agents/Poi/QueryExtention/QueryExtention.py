from typing import List
from app.core.LLMClient.BaseLlmClient import BaseLLMClient
from app.core.models.LlmClientDataclass.ChatMessageDataclass import ChatMessage, MessageData
from app.core.Agents.Poi.QueryExtention.BaseKeywordExtractor import BaseKeywordExtractor


KEYWORD_EXTRACTION_PROMPT = """당신은 여행 키워드 추출 전문가입니다.

여행자가 "{destination}"(으)로 여행을 계획하고 있습니다.
다음 여행자 페르소나와 여행 기간을 분석하여, 해당 여행지에서 이 여행자가 좋아할 만한 POI 검색 키워드를 추출해주세요.

<destination>
{destination}
</destination>

<travel_period>
시작일: {start_date}
종료일: {end_date}
</travel_period>

<persona>
{persona}
</persona>

지침:
- 반드시 "{destination}" 여행지에 특화된 키워드를 생성할 것
- 페르소나의 여행 스타일, 취향, 예산, 동행인 등을 고려
- "{destination}"의 유명 관광지, 로컬 맛집, 숨은 명소 등을 반영
- 여행 기간의 계절과 시기를 반드시 고려하여 키워드 생성:
  - 해당 시기에 가능한 계절 활동 (예: 3-4월 벚꽃, 10-11월 단풍, 7-8월 해수욕/물놀이, 12-2월 스키/온천)
  - 해당 기간에 열리는 축제나 이벤트
  - 해당 계절에 먹을 수 있는 제철 음식
  - 비수기/성수기 특성 고려
  - 해당 시기에 불가능한 활동은 제외 (예: 겨울에 해수욕, 여름에 스키)
- 5-10개의 검색 키워드 생성
- 맛집, 카페, 관광지, 쇼핑, 액티비티 등 다양한 카테고리 포함
- 모든 키워드에 여행지명을 포함할 것

응답 형식:
<keywords>
<keyword>{destination} 혼밥 맛집</keyword>
<keyword>{destination} 로컬 카페</keyword>
<keyword>{destination} 인스타 감성 카페</keyword>
</keywords>
"""


class QueryExtension(BaseKeywordExtractor):
    """페르소나 기반 여행 키워드 추출 모듈"""
    
    def __init__(self, llm_client: BaseLLMClient):
        self.llm = llm_client
    
    async def extract_keywords(self, persona_summary: str, destination: str, start_date: str, end_date: str) -> List[str]:
        """
        페르소나와 여행지 기반 키워드 추출
        
        Args:
            persona_summary: 여행자 페르소나 요약
            destination: 여행 목적지 (도시명)
            start_date: 여행 시작일 (예: "2026-03-01")
            end_date: 여행 종료일 (예: "2026-03-04")
            
        Returns:
            추출된 검색 키워드 리스트
        """
        if not persona_summary:
            return []
        
        prompt = KEYWORD_EXTRACTION_PROMPT.format(
            persona=persona_summary,
            destination=destination,
            start_date=start_date,
            end_date=end_date
        )
        
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
