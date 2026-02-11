"""
ItineraryPlanAgent: LLM을 활용한 일정 생성

주요 기능:
- POI 리스트를 날짜별로 배치
- 피드백 반영하여 일정 수정
- Transfer는 생성하지 않음 (DistanceCalculateAgent가 담당)
"""
import logging
import re
from typing import List, Optional, Type
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

from app.core.LLMClient.LangchainClient import LangchainClient
from app.core.models.LlmClientDataclass.ChatMessageDataclass import ChatMessage, MessageData
from app.core.models.PoiAgentDataclass.poi import PoiData
from app.core.models.ItineraryAgentDataclass.itinerary import Itinerary, ScheduledPoiEntry


class ScheduledPoi(BaseModel):
    """시간이 배정된 POI (LLM 출력용)"""
    poi_id: str = Field(..., description="POI ID")
    poi_name: str = Field(..., description="POI 이름")
    start_time: str = Field(..., description="시작 시간 (HH:MM, 24시간제)")
    duration_minutes: int = Field(..., description="체류 시간 (분)")


class DayPlan(BaseModel):
    """하루 일정 (LLM 출력용)"""
    date: str = Field(..., description="날짜 (YYYY-MM-DD)")
    scheduled_pois: List[ScheduledPoi] = Field(..., description="시간 배정된 POI 리스트 (순서대로)")


class ItineraryPlanResult(BaseModel):
    """일정 생성 결과 (LLM 출력용)"""
    day_plans: List[DayPlan] = Field(..., description="일별 일정 리스트")
    reasoning: str = Field(..., description="일정 배치 이유")


class ItineraryPlanAgent:
    """LLM 기반 일정 생성 에이전트"""
    
    SYSTEM_PROMPT = """당신은 여행 일정을 계획하는 전문가입니다.
주어진 POI 목록을 여행 기간 내에 적절히 배치하여 최적의 일정을 만들어주세요.

규칙:
1. 각 날짜에 1-10개의 POI를 배치하세요. (장소의 체류 시간을 고려하여 너무 많거나 적지 않게)
2. 비슷한 위치의 POI는 같은 날에 배치하세요
3. 식당/카페는 적절한 시간대에 배치하세요 (점심 11:30-13:00, 저녁 17:30-19:00)
4. 피드백이 있다면 반드시 반영하세요
5. 각 POI에 시작 시간(HH:MM)과 체류 시간(분)을 배정하세요
6. 하루 일정은 09:00~21:00 사이로 계획하세요. 단 여행의 시작일({travel_start_date} {travel_start_time})과 종료일({travel_end_date} {travel_end_time})은 해당 시간에 맞게 조정하세요.
7. POI 간 이동 시간 30분을 고려하여 시간을 배정하세요
8. 체류 시간은 장소 특성에 맞게 자유롭게 결정하세요
9. 각 POI에 대해 poi_id와 poi_name을 반드시 함께 출력하세요. poi_id와 poi_name은 주어진 POI 목록의 값을 그대로 사용하세요."""

    def __init__(self, llm_client: LangchainClient):
        """
        Args:
            llm_client: LangchainClient 인스턴스
        """
        self.llm = llm_client
    
    async def generate(
        self,
        pois: List[PoiData],
        travel_destination: str,
        travel_start_date: str,
        travel_end_date: str,
        travel_start_time: str,
        travel_end_time: str,
        persona_summary: str,
        feedback: Optional[str] = None
    ) -> List[Itinerary]:
        """
        POI 리스트로 일정 생성
        
        Args:
            pois: POI 리스트
            travel_destination: 여행지
            travel_start_date: 여행 시작일
            travel_end_date: 여행 종료일
            persona_summary: 사용자 페르소나
            feedback: 이전 일정에 대한 피드백 (수정 시)
            
        Returns:
            Itinerary 리스트 (transfers는 빈 리스트)
        """
        logger.info("일정 생성 요청: POI 수=%d, 여행지=%s, 기간=%s~%s, 피드백 유무=%s",
                     len(pois), travel_destination, travel_start_date, travel_end_date, feedback is not None)
        logger.info("피드백 정보: %s", feedback)
        user_prompt = self._build_prompt(
            pois=pois,
            travel_destination=travel_destination,
            travel_start_date=travel_start_date,
            travel_end_date=travel_end_date,
            persona_summary=persona_summary,
            feedback=feedback
        )
        logger.info("프롬프트 생성 완료: 길이=%d자", len(user_prompt))

        chat_message = ChatMessage(content=[
            MessageData(role="system", content=self.SYSTEM_PROMPT.format(
                travel_start_date=travel_start_date,
                travel_end_date=travel_end_date,
                travel_start_time=travel_start_time,
                travel_end_time=travel_end_time
            )),
            MessageData(role="user", content=user_prompt)
        ])

        logger.info("프롬프트 내용: %s", chat_message.content)

        # LLM 호출 (LangChain Structured Output)
        logger.info("LLM 호출 시작")
        try:
            result: ItineraryPlanResult = await self.llm.call_structured(
                chat_message,
                ItineraryPlanResult
            )
        except Exception as e:
            logger.error("LLM 호출 실패: %s", e, exc_info=True)
            raise

        logger.info("LLM 호출 완료: day_plans 수=%d, reasoning 길이=%d자",
                     len(result.day_plans), len(result.reasoning))
        
        logger.info("LLM 결과: %s", result.model_dump())

        # 결과를 Itinerary로 변환
        return self._convert_to_itineraries(result, pois)
    
    def _build_prompt(
        self,
        pois: List[PoiData],
        travel_destination: str,
        travel_start_date: str,
        travel_end_date: str,
        persona_summary: str,
        feedback: Optional[str] = None
    ) -> str:
        """프롬프트 생성"""
        poi_info = "\n".join([
            f"<ID>{poi.id}</ID> <name>{poi.name}</name> <category>{poi.types}</category> "
            f"<description>{poi.description[:50] if poi.description else '정보 없음'}</description>"
            f"<address>{poi.address or '정보 없음'}</address>"
            for poi in pois
        ])
        
        prompt = f"""
<travel_info>
    <destination>{travel_destination}</destination>
    <start_date>{travel_start_date}</start_date>
    <end_date>{travel_end_date}</end_date>
</travel_info>

<persona>
{persona_summary}
</persona>

<poi_list>
{poi_info}
</poi_list>
"""
        
        if feedback:
            prompt += f"""
<feedback>
다음 피드백을 반영하여 일정을 수정해주세요:
{feedback}
</feedback>
"""
        
        prompt += """
위 정보를 바탕으로 최적의 여행 일정을 생성해주세요.
각 날짜에 방문할 POI를 순서대로 배치하고, 각 POI에 시작 시간과 체류 시간을 배정해주세요.
"""
        return prompt
    
    @staticmethod
    def _normalize_name(name: str) -> str:
        """POI 이름 정규화 (폴백 매핑용)"""
        if not name:
            return ""
        return re.sub(r'\s+', ' ', name.strip()).lower()

    def _convert_to_itineraries(
        self,
        result: ItineraryPlanResult,
        pois: List[PoiData]
    ) -> List[Itinerary]:
        """LLM 결과를 Itinerary로 변환 (ID 매핑 → 이름 폴백)"""
        # 1차: POI ID -> PoiData 매핑
        poi_map = {poi.id: poi for poi in pois}
        # 2차 폴백: 정규화된 이름 -> PoiData 매핑
        name_map = {self._normalize_name(poi.name): poi for poi in pois}

        unmapped_pois = []
        itineraries = []
        for day_plan in result.day_plans:
            day_pois = []
            day_schedule = []
            for sp in day_plan.scheduled_pois:
                matched_poi = None

                # 1차: ID 기반 매핑
                if sp.poi_id in poi_map:
                    matched_poi = poi_map[sp.poi_id]
                else:
                    # 2차: 이름 기반 폴백 매핑
                    normalized_name = self._normalize_name(sp.poi_name)
                    if normalized_name in name_map:
                        matched_poi = name_map[normalized_name]
                        logger.info("이름 폴백 매핑 성공: '%s' → poi_id=%s", sp.poi_name, matched_poi.id)

                if matched_poi:
                    day_pois.append(matched_poi)
                    day_schedule.append(ScheduledPoiEntry(
                        poi_id=matched_poi.id,
                        start_time=sp.start_time,
                        duration_minutes=sp.duration_minutes
                    ))
                else:
                    unmapped_pois.append(f"{sp.poi_name} (id={sp.poi_id})")

            itinerary = Itinerary(
                date=day_plan.date,
                pois=day_pois,
                schedule=day_schedule,
                transfers=[],  # DistanceCalculateAgent가 채울 예정
                total_duration_minutes=0  # 이후 계산
            )
            itineraries.append(itinerary)

        if unmapped_pois:
            logger.warning("매핑 실패 POI (ID+이름 모두 불일치): %s", unmapped_pois)
        logger.info("Itinerary 변환 완료: %d일 일정 생성", len(itineraries))
        return itineraries
    
    async def refine(
        self,
        current_itineraries: List[Itinerary],
        pois: List[PoiData],
        travel_destination: str,
        travel_start_date: str,
        travel_end_date: str,
        travel_start_time: str,
        travel_end_time: str,
        persona_summary: str,
        feedback: str
    ) -> List[Itinerary]:
        """
        피드백을 반영하여 일정 수정

        내부적으로 generate를 호출하며, 피드백을 전달합니다.
        """
        logger.info("일정 수정 요청: 피드백 길이=%d자", len(feedback))
        return await self.generate(
            pois=pois,
            travel_destination=travel_destination,
            travel_start_date=travel_start_date,
            travel_end_date=travel_end_date,
            travel_start_time=travel_start_time,
            travel_end_time=travel_end_time,
            persona_summary=persona_summary,
            feedback=feedback
        )
