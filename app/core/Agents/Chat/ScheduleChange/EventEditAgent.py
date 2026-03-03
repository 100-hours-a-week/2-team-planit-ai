"""
EventEditAgent: 일정 이벤트 수정 에이전트

vLLM을 활용하여 전체 또는 일부 일정을 수정합니다.
수정 범위가 다양(단건 교체, 전체일 교체, 시간 재배치 등)하므로 에이전트로 구성합니다.
검증된 장소 정보(resolved_place)가 있으면 활용합니다.
"""
import logging
from copy import deepcopy
from typing import Optional

from pydantic import BaseModel, Field

from app.core.LLMClient.BaseLlmClient import BaseLLMClient
from app.core.models.LlmClientDataclass.ChatMessageDataclass import (
    ChatMessage as LlmChatMessage,
    MessageData,
)
from app.schemas.Itinerary import (
    ActivityResponse,
    DayItineraryResponse,
    ItineraryResponse,
)

logger = logging.getLogger(__name__)


class EditPlan(BaseModel):
    """LLM이 생성하는 수정 계획"""
    edit_type: str = Field(
        ..., description="수정 유형: 'replace_event' | 'change_time' | 'change_duration' | 'swap_events'"
    )
    target_day: int = Field(..., description="대상 일차 (1-indexed)")
    target_event_index: int = Field(
        ..., description="대상 이벤트 순서 (1-indexed, POI 기준)"
    )
    new_place_name: Optional[str] = Field(
        None, description="교체할 장소 이름 (replace_event일 때)"
    )
    new_place_type: Optional[str] = Field(
        None, description="교체할 장소 타입 (예: restaurant, attraction)"
    )
    new_start_time: Optional[str] = Field(
        None, description="변경할 시작 시간 HH:MM (change_time일 때)"
    )
    new_duration: Optional[int] = Field(
        None, description="변경할 체류 시간(분) (change_duration일 때)"
    )
    swap_with_index: Optional[int] = Field(
        None, description="교환할 이벤트 순서 (swap_events일 때)"
    )
    reasoning: str = Field(..., description="수정 이유")


class EventEditAgent:
    """이벤트 수정 에이전트

    vLLM을 활용하여 사용자 요청을 분석하고,
    ItineraryResponse의 이벤트를 수정합니다.

    지원 기능:
    - 단건 수정 (replace_event, change_time 등)
    - 전체일 교체 (all_day + resolved_place)
    """

    SYSTEM_PROMPT = """당신은 여행 일정 수정 전문가입니다.
사용자의 요청을 분석하여 일정 수정 계획을 JSON으로 출력합니다.

수정 유형:
- replace_event: 특정 일정을 다른 장소로 교체
- change_time: 시작 시간 변경
- change_duration: 체류 시간 변경
- swap_events: 두 이벤트의 순서 교환

반드시 reasoning 필드에 수정 이유를 작성하세요."""

    def __init__(self, llm_client: BaseLLMClient):
        """
        Args:
            llm_client: vLLM 클라이언트
        """
        self.llm_client = llm_client

    async def edit(
        self,
        itinerary: ItineraryResponse,
        day: int,
        event_index: Optional[int],
        user_request: str,
        target_scope: str = "single",
        resolved_place: Optional[dict] = None,
    ) -> tuple[ItineraryResponse, Optional[str]]:
        """이벤트 수정 실행

        Args:
            itinerary: 현재 일정
            day: 수정 대상 일차 (1-indexed)
            event_index: 수정 대상 이벤트 순서 (1-indexed). all_day면 None
            user_request: 사용자 수정 요청 상세
            target_scope: "single" 또는 "all_day"
            resolved_place: PlaceResolver 검증 결과 (있으면 활용)

        Returns:
            tuple[ItineraryResponse, Optional[str]]:
                - 수정된 일정
                - 에러 메시지 (성공 시 None)
        """
        modified = deepcopy(itinerary)

        # 일차 유효성 검사
        if day < 1 or day > len(modified.itineraries):
            return itinerary, (
                f"유효하지 않은 일차입니다. "
                f"1~{len(modified.itineraries)}일차 중 선택해주세요."
            )

        day_itin = modified.itineraries[day - 1]

        # 전체일 교체
        if target_scope == "all_day":
            return self._edit_all_day(
                modified, day_itin, day, user_request, resolved_place
            )

        # 단건 수정
        poi_activities = [a for a in day_itin.activities if a.type != "route"]

        if event_index is None:
            return itinerary, "단건 수정 시 event_index가 필요합니다."

        if event_index < 1 or event_index > len(poi_activities):
            return itinerary, (
                f"{day}일차에는 {len(poi_activities)}개의 이벤트가 있습니다. "
                f"1~{len(poi_activities)} 중 선택해주세요."
            )

        # resolved_place가 있으면 바로 교체, 없으면 LLM으로 수정 계획 생성
        if resolved_place and resolved_place.get("is_found"):
            return self._replace_with_resolved(
                modified, day_itin, poi_activities, event_index, resolved_place
            )

        # LLM으로 수정 계획 생성
        try:
            edit_plan = await self._generate_edit_plan(
                day_itin=day_itin,
                day=day,
                event_index=event_index,
                user_request=user_request,
            )

        except Exception as e:
            logger.error(f"수정 계획 생성 실패: {e}")
            return itinerary, f"수정 계획을 생성하지 못했습니다: {e}"

        return self._apply_edit_plan(modified, day_itin, poi_activities, edit_plan)

    def _edit_all_day(
        self,
        itinerary: ItineraryResponse,
        day_itin: DayItineraryResponse,
        day: int,
        user_request: str,
        resolved_place: Optional[dict] = None,
    ) -> tuple[ItineraryResponse, Optional[str]]:
        """전체일 교체

        검증된 장소가 있으면 해당 장소로 전체 교체,
        없으면 기존 일정을 유지하면서 메모만 업데이트.
        poi_detail(VectorDB)이 있으면 카테고리, URL, 평점 등을 활용.
        """
        if resolved_place and resolved_place.get("is_found"):
            poi_detail = resolved_place.get("poi_detail")

            if poi_detail:
                # VectorDB 상세 데이터 활용
                place_name = poi_detail.get("name") or resolved_place.get("place_name", "새 장소")
                google_map_url = poi_detail.get("google_maps_uri")
                activity_type = _category_to_type(poi_detail.get("category", ""))
                memo_parts = [f"전체일 변경: {user_request}"]
                if poi_detail.get("google_rating"):
                    memo_parts.append(f"평점: {poi_detail['google_rating']}")
                if poi_detail.get("address"):
                    memo_parts.append(f"주소: {poi_detail['address']}")
                memo = " | ".join(memo_parts)
            else:
                # SQLite 정보만 사용
                place_name = resolved_place.get("place_name", "새 장소")
                google_place_id = resolved_place.get("google_place_id")
                google_map_url = None
                if google_place_id:
                    google_map_url = (
                        f"https://www.google.com/maps/place/"
                        f"?q=place_id:{google_place_id}"
                    )
                activity_type = "attraction"
                memo = f"전체일 변경: {user_request}"

            # 기존 활동 전부 제거 후 새 장소로 교체
            day_itin.activities = [
                ActivityResponse(
                    placeName=place_name,
                    type=activity_type,
                    eventOrder=1,
                    startTime="09:00",
                    duration=480,  # 하루 종일 (8시간)
                    googleMapUrl=google_map_url,
                    memo=memo,
                )
            ]

            logger.info(
                f"전체일 교체 완료: {day}일차 → '{place_name}'"
            )
        else:
            # 검증된 장소가 없으면 모든 POI의 memo에 요청 내용 기록
            for act in day_itin.activities:
                if act.type != "route":
                    act.memo = f"변경 요청: {user_request}"

            logger.info(
                f"전체일 메모 업데이트: {day}일차 (검증된 장소 없음)"
            )

        return itinerary, None

    def _replace_with_resolved(
        self,
        itinerary: ItineraryResponse,
        day_itin: DayItineraryResponse,
        poi_activities: list[ActivityResponse],
        event_index: int,
        resolved_place: dict,
    ) -> tuple[ItineraryResponse, Optional[str]]:
        """검증된 장소로 단건 교체

        poi_detail(VectorDB)이 있으면 카테고리, URL, 평점 등을 활용.
        """
        target = poi_activities[event_index - 1]
        poi_detail = resolved_place.get("poi_detail")

        if poi_detail:
            # VectorDB 상세 데이터 활용
            target.placeName = poi_detail.get("name") or resolved_place.get("place_name", target.placeName)
            target.googleMapUrl = poi_detail.get("google_maps_uri")
            target.type = _category_to_type(poi_detail.get("category", target.type))

            memo_parts = []
            if poi_detail.get("google_rating"):
                memo_parts.append(f"평점: {poi_detail['google_rating']}")
            if poi_detail.get("address"):
                memo_parts.append(f"주소: {poi_detail['address']}")
            if memo_parts:
                target.memo = " | ".join(memo_parts)
        else:
            # SQLite 정보만 사용
            place_name = resolved_place.get("place_name", target.placeName)
            google_place_id = resolved_place.get("google_place_id")
            target.placeName = place_name
            target.googleMapUrl = None
            if google_place_id:
                target.googleMapUrl = (
                    f"https://www.google.com/maps/place/"
                    f"?q=place_id:{google_place_id}"
                )

        logger.info(
            f"검증된 장소로 교체: {event_index}번째 → '{target.placeName}'"
        )

        return itinerary, None

    async def _generate_edit_plan(
        self,
        day_itin: DayItineraryResponse,
        day: int,
        event_index: int,
        user_request: str,
    ) -> EditPlan:
        """LLM으로 수정 계획 생성"""
        poi_activities = [a for a in day_itin.activities if a.type != "route"]
        current_schedule = "\n".join(
            f"  {i}. {a.placeName or '이름 없음'} "
            f"(시작: {a.startTime or '미정'}, {a.duration}분, 타입: {a.type})"
            for i, a in enumerate(poi_activities, 1)
        )

        user_prompt = f"""현재 {day}일차 일정:
{current_schedule}

수정 대상: {event_index}번째 이벤트 ({poi_activities[event_index - 1].placeName or '이름 없음'})
사용자 요청: {user_request}

위 정보를 바탕으로 수정 계획을 JSON으로 출력하세요.
target_day는 {day}, target_event_index는 {event_index}로 설정하세요."""

        prompt = LlmChatMessage(content=[
            MessageData(role="system", content=self.SYSTEM_PROMPT),
            MessageData(role="user", content=user_prompt),
        ])

        return await self.llm_client.call_llm_structured(prompt, EditPlan)

    def _apply_edit_plan(
        self,
        itinerary: ItineraryResponse,
        day_itin: DayItineraryResponse,
        poi_activities: list[ActivityResponse],
        plan: EditPlan,
    ) -> tuple[ItineraryResponse, Optional[str]]:
        """수정 계획 적용"""
        idx = plan.target_event_index - 1
        target = poi_activities[idx]

        if plan.edit_type == "replace_event":
            target.placeName = plan.new_place_name or target.placeName
            if plan.new_place_type:
                target.type = plan.new_place_type
            target.googleMapUrl = None
            logger.info(
                f"이벤트 교체: {plan.target_day}일차 {plan.target_event_index}번 "
                f"→ '{plan.new_place_name}'"
            )

        elif plan.edit_type == "change_time":
            if plan.new_start_time:
                target.startTime = plan.new_start_time

        elif plan.edit_type == "change_duration":
            if plan.new_duration is not None:
                target.duration = plan.new_duration

        elif plan.edit_type == "swap_events":
            if plan.swap_with_index is not None:
                swap_idx = plan.swap_with_index - 1
                if 0 <= swap_idx < len(poi_activities) and swap_idx != idx:
                    swap_target = poi_activities[swap_idx]
                    target.placeName, swap_target.placeName = (
                        swap_target.placeName, target.placeName
                    )
                    target.type, swap_target.type = (
                        swap_target.type, target.type
                    )
                    target.googleMapUrl, swap_target.googleMapUrl = (
                        swap_target.googleMapUrl, target.googleMapUrl
                    )
                else:
                    return itinerary, "교환 대상 이벤트가 유효하지 않습니다."
        else:
            return itinerary, f"알 수 없는 수정 유형입니다: {plan.edit_type}"
        return itinerary, None


def _category_to_type(category: str) -> str:
    """PoiCategory → ActivityResponse.type 매핑"""
    mapping = {
        "restaurant": "restaurant",
        "cafe": "cafe",
        "attraction": "attraction",
        "accommodation": "accommodation",
        "shopping": "shopping",
        "entertainment": "entertainment",
    }
    return mapping.get(category, "attraction")
