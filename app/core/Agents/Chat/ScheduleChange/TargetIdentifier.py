"""
TargetIdentifier: 사용자 자연어 요청에서 수정 대상 이벤트를 식별하는 노드

vLLM을 사용하여 "2일차 두번째 일정을 맛집으로 바꿔줘" 같은 자연어를
구조화된 TargetEventInfo로 변환합니다.
처리 불가능한 요청은 사유와 함께 종료합니다.

전체일 대상("마지막 날 전부 바꿔줘") 및 장소 이름 추출도 지원합니다.
"""
import logging
from typing import Literal, Optional

from pydantic import BaseModel, Field, model_validator

from app.core.LLMClient.BaseLlmClient import BaseLLMClient
from app.core.models.LlmClientDataclass.ChatMessageDataclass import (
    ChatMessage as LlmChatMessage,
    MessageData,
)
from app.core.Agents.Chat.ChatState import TargetEventInfo
from app.schemas.Itinerary import ItineraryResponse

logger = logging.getLogger(__name__)


class TargetIdentifierResult(BaseModel):
    """LLM이 출력하는 수정 대상 식별 결과"""
    is_resolvable: bool = Field(
        ..., description="요청을 처리할 수 있으면 true, 처리할 수 없으면 false"
    )
    reject_reason: Optional[str] = Field(
        None,
        description="is_resolvable이 false일 때만 작성. 처리 불가 사유를 설명",
    )
    action: Optional[Literal["edit", "delete", "add"]] = Field(
        None,
        description="is_resolvable이 true이면 반드시 설정. 수정='edit', 삭제='delete', 추가='add'",
    )
    day: Optional[int] = Field(
        None,
        description="is_resolvable이 true이면 반드시 설정. 대상 일차 번호 (1부터 시작)",
    )
    event_index: Optional[int] = Field(
        None,
        description="대상 이벤트 순서 (1부터 시작, POI 기준). 전체일 대상이면 null",
    )
    target_scope: Literal["single", "all_day"] = Field(
        "single",
        description="'single'=특정 이벤트 하나, 'all_day'=해당 일차 전체",
    )
    requested_place: Optional[str] = Field(
        None,
        description="사용자가 요청한 구체적 장소 이름. 예: '디즈니랜드', '스타벅스'. 추상적 표현('맛집', '카페')이면 null",
    )
    detail: Optional[str] = Field(
        None,
        description="is_resolvable이 true이면 반드시 설정. 사용자가 원하는 변경 내용을 한 줄로 요약",
    )

    @model_validator(mode="after")
    def check_required_when_resolvable(self) -> "TargetIdentifierResult":
        """is_resolvable=True일 때 action, day, detail이 반드시 존재하는지 검증"""
        if self.is_resolvable:
            missing = []
            if self.action is None:
                missing.append("action")
            if self.day is None:
                missing.append("day")
            if self.detail is None:
                missing.append("detail")
            if missing:
                raise ValueError(
                    f"is_resolvable=true인데 필수 필드가 누락됨: {', '.join(missing)}"
                )
            # single scope에서 edit/delete일 때 event_index 필수
            if self.target_scope == "single" and self.action in ("edit", "delete"):
                if self.event_index is None:
                    raise ValueError(
                        "target_scope='single'이고 action이 edit/delete이면 event_index 필수"
                    )
        return self


class TargetIdentifier:
    """수정 대상 식별 노드

    사용자의 자연어 요청과 현재 일정을 분석하여
    구체적인 수정 대상(일차, 이벤트 순서, 수정 유형)을 식별합니다.

    처리 불가능하다고 판단되면 사유를 포함하여 종료합니다.
    """

    SYSTEM_PROMPT = """당신은 여행 일정 수정 요청을 분석하여 JSON으로 출력하는 전문가입니다.

## 출력 필드 규칙

[처리 가능한 요청일 때] is_resolvable=true로 설정하고 아래 필드를 반드시 채우세요:
- action: 반드시 "edit", "delete", "add" 중 하나. 절대 null 불가.
- day: 대상 일차 번호. 반드시 1 이상의 정수. 절대 null 불가.
- target_scope: "single" 또는 "all_day".
  - "single": 특정 이벤트 하나만 대상 → event_index 필수
  - "all_day": 해당 일차 전체 대상 → event_index는 null
- event_index: target_scope="single"이고 edit/delete일 때 반드시 설정 (1부터 시작, POI 기준). add일 때는 삽입 위치 또는 null.
- requested_place: 사용자가 구체적 장소 이름을 언급했으면 추출. 추상적 표현("맛집", "카페")이면 null.
- detail: 사용자 요청을 한 줄로 요약. 절대 null 불가.
- reject_reason: null로 설정.

[처리 불가능한 요청일 때] is_resolvable=false로 설정하고:
- reject_reason: 처리 불가 사유를 작성.
- action, day, event_index, detail, requested_place: 모두 null로 설정.

## action 판별 기준

사용자 표현 → action 값:
- 삭제, 제거, 빼줘, 없애줘, 취소 → "delete"
- 변경, 수정, 바꿔, 교체, 대신 → "edit"
- 추가, 넣어줘, 포함, 더해줘 → "add"

## target_scope 판별 기준

- "전부", "모두", "전체", "다", "일정 전체" → "all_day"
- 특정 순서를 언급 ("두번째", "3번째") → "single"

## requested_place 판별 기준

- 구체적 장소: "디즈니랜드", "센소지", "스타벅스", "이치란 라멘" → 해당 이름 추출
- 추상적 표현: "맛집", "카페", "볼거리", "좋은 곳" → null

## 예시

사용자: "2일차의 3번째 일정을 삭제해줘"
→ {"is_resolvable":true, "action":"delete", "day":2, "event_index":3, "target_scope":"single", "requested_place":null, "detail":"2일차 3번째 일정 삭제", "reject_reason":null}

사용자: "마지막 날 일정 전부 디즈니랜드로 변경해줘"
→ {"is_resolvable":true, "action":"edit", "day":3, "event_index":null, "target_scope":"all_day", "requested_place":"디즈니랜드", "detail":"마지막 날 전체 일정을 디즈니랜드로 변경", "reject_reason":null}

사용자: "1일차에 도쿄타워를 추가해줘"
→ {"is_resolvable":true, "action":"add", "day":1, "event_index":null, "target_scope":"single", "requested_place":"도쿄타워", "detail":"1일차에 도쿄타워 추가", "reject_reason":null}

사용자: "2일차 전체를 삭제해줘"
→ {"is_resolvable":true, "action":"delete", "day":2, "event_index":null, "target_scope":"all_day", "requested_place":null, "detail":"2일차 전체 일정 삭제", "reject_reason":null}"""

    def __init__(self, llm_client: BaseLLMClient):
        """
        Args:
            llm_client: vLLM 클라이언트
        """
        self.llm_client = llm_client

    async def identify(
        self,
        user_message: str,
        itinerary: ItineraryResponse,
    ) -> TargetEventInfo:
        """수정 대상 식별

        Args:
            user_message: 사용자 요청 메시지
            itinerary: 현재 일정

        Returns:
            TargetEventInfo: 식별된 수정 대상 정보
        """
        if not itinerary or not itinerary.itineraries:
            raise ValueError("일정이 없습니다.")
        # 현재 일정 텍스트 생성
        schedule_text = self._format_itinerary(itinerary)

        user_prompt = f"""현재 일정 (총 {len(itinerary.itineraries)}일):
{schedule_text}

사용자 요청: {user_message}

위 일정과 요청을 분석하여 수정 대상을 식별해주세요."""

        prompt = LlmChatMessage(content=[
            MessageData(role="system", content=self.SYSTEM_PROMPT),
            MessageData(role="user", content=user_prompt),
        ])

        try:
            result = await self.llm_client.call_llm_structured(
                prompt, TargetIdentifierResult
            )
        except Exception as e:
            logger.error(f"수정 대상 식별 실패: {e}")
            return TargetEventInfo(
                is_resolvable=False,
                reject_reason=f"요청을 분석하지 못했습니다: {e}",
            )

        # 결과 검증 & 변환
        return self._validate_and_convert(result, itinerary)

    def _format_itinerary(
        self, itinerary: Optional[ItineraryResponse]
    ) -> str:
        """ItineraryResponse를 LLM 입력용 텍스트로 포맷"""
        if itinerary is None or not itinerary.itineraries:
            return "(일정 없음)"

        lines = []
        for day_itin in itinerary.itineraries:
            lines.append(f"\n{day_itin.day}일차 ({day_itin.date}):")
            poi_idx = 1
            for act in day_itin.activities:
                if act.type == "route":
                    lines.append(
                        f"  → 이동 ({act.transport or '도보'}, {act.duration}분)"
                    )
                else:
                    lines.append(
                        f"  {poi_idx}. {act.placeName or '이름 없음'} "
                        f"(시작: {act.startTime or '미정'}, "
                        f"{act.duration}분, 타입: {act.type})"
                    )
                    poi_idx += 1
        return "\n".join(lines)

    def _validate_and_convert(
        self,
        result: TargetIdentifierResult,
        itinerary: Optional[ItineraryResponse],
    ) -> TargetEventInfo:
        """LLM 결과를 검증하고 TargetEventInfo로 변환"""
        if not result.is_resolvable:
            raise ValueError(result.reject_reason or "요청을 처리할 수 없습니다.")

        # action 검증
        if result.action not in ("edit", "delete", "add"):
            raise ValueError(f"알 수 없는 수정 유형: {result.action}")

        # day 범위 검증
        if itinerary and result.day is not None:
            if result.day < 1 or result.day > len(itinerary.itineraries):
                raise ValueError(
                    f"유효하지 않은 일차입니다. "
                    f"현재 일정은 {len(itinerary.itineraries)}일입니다. "
                    f"입력된 day: {result.day}"
                )

            # single scope에서 event_index 범위 검증
            if result.target_scope == "single" and result.action in ("edit", "delete"):
                if result.event_index is not None:
                    day_itin = itinerary.itineraries[result.day - 1]
                    poi_count = sum(
                        1 for a in day_itin.activities if a.type != "route"
                    )
                    if result.event_index < 1 or result.event_index > poi_count:
                        raise ValueError(
                            f"{result.day}일차에는 {poi_count}개의 이벤트가 있습니다. "
                            f"입력된 event_index: {result.event_index}"
                        )

        return TargetEventInfo(
            day=result.day,
            event_index=result.event_index,
            action=result.action,
            detail=result.detail,
            is_resolvable=True,
            reject_reason=None,
            target_scope=result.target_scope,
            requested_place=result.requested_place,
        )
"""
TargetIdentifier.py
"""
