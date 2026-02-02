from typing import List
import uuid
import re

from app.core.models.PoiAgentDataclass.poi import (
    PoiSearchResult, 
    PoiInfo, 
    PoiCategory
)
from app.core.LLMClient.BaseLlmClient import BaseLLMClient
from app.core.models.LlmClientDataclass.ChatMessageDataclass import ChatMessage, MessageData


INFO_SUMMARIZE_SINGLE_PROMPT = """당신은 여행 검색 정보 요약 전문가입니다.
poi는 장소에 대한 정보입니다. 검색 결과에서 장소에 대한 정보를 추출하여 poi에 대해서 작성하여 답변합니다.

다음 여행자 페르소나와 단일 검색 결과를 바탕으로 해당 POI의 정보를 요약해주세요.

<persona>
{persona}
</persona>

<search_result>
<title>{title}</title>
<content>{snippet}</content>
<url>{url}</url>
</search_result>

위 정보를 바탕으로 이 POI에 대한 상세 정보를 생성해주세요.

중요한 규칙:
1. 검색 결과에 있는 정보만 사용하세요.
2. 추측이나 가정을 하지 마세요.
3. 정보가 불충분하면 해당 필드를 비워두세요.
4.검색 결과에서 장소에 대한 정보를 추출하여 poi에 대해서 작성해주세요.
5. 장소가 여러 개이면 여러 개의 poi를 작성해주세요.

다음 형식으로 응답해주세요:

<poi>
<name>POI 이름 (정확한 상호명)</name>
<category>restaurant|cafe|attraction|accommodation|shopping|entertainment|other</category>
<description>이 POI에 대한 객관적인 설명 (2-3문장, 해당 POI만의 특징)</description>
<address>주소 (검색 결과에서 찾을 수 없으면 비워두기)</address>
<summary>이 여행자에게 추천하는 이유 (2-3문장, 페르소나에 맞춤)</summary>
<highlights>특징1, 특징2, 특징3</highlights>
</poi>
"""


INFO_SUMMARIZE_PROMPT = """당신은 여행 POI 정보 요약 전문가입니다.

다음 여행자 페르소나와 검색 결과들을 바탕으로 추천할 POI(관광지/맛집 등) 목록을 생성해주세요.

<persona>
{persona}
</persona>

<search_results>
{results}
</search_results>

위 정보를 바탕으로 여행자에게 추천할 POI 목록을 생성해주세요.

중요한 규칙:
1. 각 POI의 정보는 반드시 해당 POI에 대한 정보만 사용하세요.
2. 다른 POI의 정보를 혼합하지 마세요.
3. 검색 결과에서 해당 POI가 언급된 부분만 참조하세요.

각 POI에 대해 다음 형식으로 응답해주세요:

<poi_list>
<poi>
<name>POI 이름 (정확한 상호명)</name>
<category>restaurant|cafe|attraction|accommodation|shopping|entertainment|other</category>
<description>이 POI에 대한 객관적인 설명 (2-3문장, 해당 POI만의 특징)</description>
<address>주소 (검색 결과에서 찾을 수 없으면 비워두기)</address>
<summary>이 여행자에게 추천하는 이유 (2-3문장, 페르소나에 맞춤)</summary>
<highlights>특징1, 특징2, 특징3</highlights>
</poi>
</poi_list>

최대 5개의 POI를 추천해주세요. 여행자의 페르소나에 맞는 POI를 우선 추천하세요.
"""



class InfoSummarizeAgent:
    """
    검색 결과를 요약하고 최종 POI 추천 목록을 생성하는 에이전트
    """

    def __init__(self, llm_client: BaseLLMClient):
        self.llm = llm_client

    async def summarize_single(
        self,
        poi_result: PoiSearchResult,
        persona_summary: str = ""
    ) -> PoiInfo | None:
        """
        단일 POI 검색 결과를 요약하여 PoiInfo 생성

        Args:
            poi_result: 단일 검색 결과
            persona_summary: 사용자 페르소나 요약

        Returns:
            생성된 PoiInfo 또는 None (실패 시)
        """
        prompt = INFO_SUMMARIZE_SINGLE_PROMPT.format(
            persona=persona_summary if persona_summary else "정보 없음",
            title=poi_result.title,
            snippet=poi_result.snippet,
            url=poi_result.url or ""
        )

        messages = ChatMessage(content=[
            MessageData(role="user", content=prompt)
        ])

        try:
            response = await self.llm.call_llm(messages)
            pois = self._parse_poi_list(response)
            if pois:
                return pois[0]
            return None

        except Exception as e:
            print(f"Info summarize single error: {e}")
            return None

    async def summarize(
        self,
        merged_results: List[PoiSearchResult],
        persona_summary: str = "",
        max_pois: int = 5
    ) -> List[PoiInfo]:
        """
        검색 결과를 요약하여 POI 추천 목록 생성
        """
        if not merged_results:
            return []
        
        # 검색 결과를 텍스트로 변환
        results_text = self._format_results(merged_results[:15])
        
        prompt = INFO_SUMMARIZE_PROMPT.format(
            persona=persona_summary if persona_summary else "정보 없음",
            results=results_text
        )
        
        messages = ChatMessage(content=[
            MessageData(role="user", content=prompt)
        ])
        
        try:
            response = await self.llm.call_llm(messages)
            pois = self._parse_poi_list(response)
            return pois[:max_pois]
            
        except Exception as e:
            print(f"Info summarize error: {e}")
            return []
    
    def _format_results(self, results: List[PoiSearchResult]) -> str:
        """검색 결과를 텍스트 형식으로 변환"""
        # TODO: 구조화될 출력이 필요함
        lines = []
        for i, result in enumerate(results, 1):
            lines.append(f"<result id=\"{i}\">")
            lines.append(f"  <title>{result.title}</title>")
            lines.append(f"  <content>{result.snippet}</content>")
            lines.append("</result>")
        return "\n".join(lines)
    
    def _parse_poi_list(self, response: str) -> List[PoiInfo]:
        """LLM 응답에서 POI 목록 파싱"""
        import re
        
        pois = []
        poi_pattern = r"<poi>(.*?)</poi>"
        poi_matches = re.findall(poi_pattern, response, re.DOTALL)
        
        for poi_text in poi_matches:
            poi = self._parse_single_poi(poi_text)
            if poi:
                pois.append(poi)
        
        return pois
    
    def _extract_tag(self, tag: str, poi_text: str) -> str:
        pattern = f"<{tag}>(.*?)</{tag}>"
        match = re.search(pattern, poi_text, re.DOTALL)
        return match.group(1).strip() if match else ""

    def _parse_single_poi(self, poi_text: str) -> PoiInfo | None:
        """단일 POI 파싱"""    
        
        name = self._extract_tag("name", poi_text)
        if not name:
            return None
        
        category_str = self._extract_tag("category", poi_text).lower()
        try:
            category = PoiCategory(category_str)
        except ValueError:
            category = PoiCategory.OTHER
        
        description = self._extract_tag("description", poi_text)
        address = self._extract_tag("address", poi_text) or None
        summary = self._extract_tag("summary", poi_text)
        highlights_str = self._extract_tag("highlights", poi_text)
        # TODO: ","로만 구분하니깐 너무 많이 쓰여서 구분이 이상한 경우가 존재함
        highlights = [h.strip() for h in highlights_str.split(",") if h.strip()]
        
        return PoiInfo(
            id=str(uuid.uuid4()),
            name=name,
            category=category,
            description=description,
            address=address,
            summary=summary,
            highlights=highlights
        )
