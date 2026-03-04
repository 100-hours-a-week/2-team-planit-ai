"""
itinerary_tools: 일정 조회/수정/삭제/추가 도구

ReAct 에이전트가 사용하는 일정 관련 도구들입니다.
클로저 패턴으로 state_container와 하위 에이전트를 캡처합니다.
"""
import asyncio
import logging
from copy import deepcopy
from typing import Optional

from langchain_core.tools import tool

from app.core.Agents.Chat.ScheduleChange.PlaceResolver import PlaceResolver
from app.core.Agents.Chat.ScheduleChange.EventEditAgent import EventEditAgent
from app.core.Agents.Chat.ScheduleChange.EventDeleteTool import EventDeleteTool
from app.core.Agents.Chat.ScheduleChange.EventAddTool import EventAddTool
from app.core.Agents.Chat.ScheduleChange.ConsistencyChecker import ConsistencyChecker
from app.core.BackendClient import BackendClient
from app.schemas.Itinerary import ActivityResponse, ItineraryResponse

logger = logging.getLogger(__name__)


def create_itinerary_tools(
    state_container: dict,
    place_resolver: PlaceResolver,
    event_edit_agent: EventEditAgent,
    consistency_checker: ConsistencyChecker,
    backend_client: Optional[BackendClient] = None,
) -> list:
    """일정 관련 도구 생성

    Args:
        state_container: 요청별 상태 컨테이너
        place_resolver: 장소 검증 모듈
        event_edit_agent: 이벤트 수정 에이전트
        consistency_checker: 정합성 검사 모듈
        backend_client: 백엔드 API 클라이언트

    Returns:
        list: 일정 관련 도구 함수 리스트
    """

    async def _sync_backend(modified: ItineraryResponse, target_day: int) -> None:
        """수정된 일정을 백엔드에 PATCH 반영 (내부 헬퍼)"""
        if not backend_client:
            return

        user_jwt = state_container.get("user_jwt")
        backend_data = state_container.get("backend_itinerary_data")

        if not user_jwt or not backend_data:
            logger.warning("user_jwt 또는 backend_itinerary_data 없음 — PATCH 스킵")
            return

        try:
            backend_itineraries = backend_data.get("itineraries", [])
            if target_day < 1 or target_day > len(backend_itineraries):
                logger.error(f"유효하지 않은 target_day={target_day}")
                return

            day_data = backend_itineraries[target_day - 1]
            day_id = day_data.get("itineraryDayId")

            if day_id is None:
                logger.error("백엔드 데이터에서 itineraryDayId를 찾을 수 없습니다.")
                return

            from app.core.Agents.Chat.ScheduleChange.ScheduleChangeAgent import (
                ScheduleChangeAgent,
            )
            places = ScheduleChangeAgent._convert_to_patch_format(
                modified, target_day, day_data,
            )

            await backend_client.update_day_itinerary(
                trip_id=modified.tripId,
                day_id=day_id,
                places=places,
                user_jwt=user_jwt,
            )

            logger.info(
                f"백엔드 PATCH 완료: tripId={modified.tripId}, "
                f"dayId={day_id}, places={len(places)}건"
            )
        except Exception as e:
            logger.error(f"백엔드 PATCH 호출 실패: {e}")

    # ─── 도구 1: view_current_itinerary ─────────────────

    @tool
    async def view_current_itinerary(day: int = 0) -> str:
        """현재 여행 일정을 조회합니다.

        Args:
            day: 조회할 일차 (1-indexed). 0이면 전체 일정을 조회합니다.

        Returns:
            현재 일정의 텍스트 요약
        """
        itinerary: Optional[ItineraryResponse] = state_container.get("current_itinerary")

        if not itinerary or not itinerary.itineraries:
            return "현재 일정이 없습니다. 일정을 먼저 생성해주세요."

        if day > 0:
            # 특정 일차만 조회
            if day > len(itinerary.itineraries):
                return (
                    f"유효하지 않은 일차입니다. "
                    f"1~{len(itinerary.itineraries)}일차 중 선택해주세요."
                )
            return _format_day(itinerary.itineraries[day - 1], day)

        # 전체 일정 조회
        lines = [f"전체 일정 ({len(itinerary.itineraries)}일):"]
        for day_itin in itinerary.itineraries:
            lines.append(_format_day(day_itin, day_itin.day))
        return "\n\n".join(lines)

    # ─── 도구 2: edit_schedule_event ────────────────────

    @tool
    async def edit_schedule_event(
        day: int,
        event_index: int,
        user_request: str,
        new_place_name: Optional[str] = None,
        target_scope: str = "single",
    ) -> str:
        """기존 일정의 이벤트를 수정합니다.

        먼저 view_current_itinerary로 일정을 확인한 후 사용하세요.

        Args:
            day: 수정할 일차 (1-indexed)
            event_index: 수정할 이벤트 순서 (1-indexed, POI 기준)
            user_request: 사용자의 수정 요청 내용 (예: "스시 맛집으로 변경")
            new_place_name: 변경할 새 장소 이름 (있으면 장소 검증 수행)
            target_scope: "single" (단건) 또는 "all_day" (전체일)

        Returns:
            수정 결과 메시지
        """
        itinerary: Optional[ItineraryResponse] = state_container.get("current_itinerary")
        if not itinerary:
            return "현재 일정이 없습니다. 일정을 먼저 생성해주세요."

        # 장소 검증
        resolved = None
        if new_place_name:
            resolved_place = await place_resolver.resolve(place_name=new_place_name, city="")
            if resolved_place.is_found:
                resolved = resolved_place.to_dict()
            else:
                return (
                    f"'{new_place_name}'을(를) 데이터베이스에서 찾지 못했습니다. "
                    f"다른 장소를 지정하거나 더 정확한 이름으로 다시 시도해주세요."
                )

        # 수정 실행
        modified, error = await event_edit_agent.edit(
            itinerary=itinerary,
            day=day,
            event_index=event_index if target_scope == "single" else None,
            user_request=user_request,
            target_scope=target_scope,
            resolved_place=resolved,
        )

        if error:
            return f"수정 실패: {error}"

        # 정합성 검사
        is_valid, feedback = consistency_checker.check(modified)

        # 상태 업데이트
        state_container["current_itinerary"] = modified

        # 백엔드 동기화
        await _sync_backend(modified, day)

        if is_valid:
            return "일정이 성공적으로 수정되었습니다."
        else:
            return f"일정이 수정되었지만 정합성 문제가 있습니다:\n{feedback}"

    # ─── 도구 3: delete_schedule_event ───────────────────

    @tool
    async def delete_schedule_event(
        day: int,
        event_index: Optional[int] = None,
        target_scope: str = "single",
    ) -> str:
        """일정에서 이벤트를 삭제합니다.

        먼저 view_current_itinerary로 일정을 확인한 후 사용하세요.

        Args:
            day: 삭제할 일차 (1-indexed)
            event_index: 삭제할 이벤트 순서 (1-indexed, POI 기준). all_day면 불필요
            target_scope: "single" (단건) 또는 "all_day" (전체일)

        Returns:
            삭제 결과 메시지
        """
        itinerary: Optional[ItineraryResponse] = state_container.get("current_itinerary")
        if not itinerary:
            return "현재 일정이 없습니다. 일정을 먼저 생성해주세요."

        modified, error = EventDeleteTool.delete(
            itinerary=itinerary,
            day=day,
            event_index=event_index,
            target_scope=target_scope,
        )

        if error:
            return f"삭제 실패: {error}"

        # 정합성 검사
        is_valid, feedback = consistency_checker.check(modified)

        # 상태 업데이트
        state_container["current_itinerary"] = modified

        # 백엔드 동기화
        await _sync_backend(modified, day)

        if is_valid:
            return "일정이 성공적으로 삭제되었습니다."
        else:
            return f"일정이 삭제되었지만 정합성 문제가 있습니다:\n{feedback}"

    # ─── 도구 4: add_schedule_event ──────────────────────

    @tool
    async def add_schedule_event(
        day: int,
        place_name: str,
        position: Optional[int] = None,
        duration: int = 60,
    ) -> str:
        """일정에 새 장소를 추가합니다.

        먼저 view_current_itinerary로 일정을 확인한 후 사용하세요.

        Args:
            day: 추가할 일차 (1-indexed)
            place_name: 추가할 장소 이름
            position: 삽입 위치 (1-indexed, POI 기준). None이면 마지막에 추가
            duration: 체류 시간 (분, 기본값 60)

        Returns:
            추가 결과 메시지
        """
        itinerary: Optional[ItineraryResponse] = state_container.get("current_itinerary")
        if not itinerary:
            return "현재 일정이 없습니다. 일정을 먼저 생성해주세요."

        # 장소 검증
        resolved_place = await place_resolver.resolve(place_name=place_name, city="")

        if resolved_place.is_found:
            new_activity = EventAddTool.create_activity_from_resolved(
                resolved_place.to_dict(), duration=duration,
            )
        else:
            new_activity = ActivityResponse(
                placeName=place_name,
                type="attraction",
                eventOrder=0,
                duration=duration,
                memo="챗봇에서 추가됨",
            )

        modified, error = EventAddTool.add(
            itinerary=itinerary,
            day=day,
            activity=new_activity,
            position=position,
        )

        if error:
            return f"추가 실패: {error}"

        # 정합성 검사
        is_valid, feedback = consistency_checker.check(modified)

        # 상태 업데이트
        state_container["current_itinerary"] = modified

        # 백엔드 동기화
        await _sync_backend(modified, day)

        if is_valid:
            return f"'{place_name}'이(가) {day}일차에 성공적으로 추가되었습니다."
        else:
            return (
                f"'{place_name}'이(가) {day}일차에 추가되었지만 "
                f"정합성 문제가 있습니다:\n{feedback}"
            )

    return [
        view_current_itinerary,
        edit_schedule_event,
        delete_schedule_event,
        add_schedule_event,
    ]


def _format_day(day_itin, day_num: int) -> str:
    """DayItineraryResponse를 텍스트로 포맷"""
    poi_activities = [a for a in day_itin.activities if a.type != "route"]

    if not poi_activities:
        return f"Day {day_num} ({day_itin.date or '날짜 미정'}): 일정 없음"

    lines = [f"Day {day_num} ({day_itin.date or '날짜 미정'}):"]
    for i, act in enumerate(poi_activities, 1):
        time_str = act.startTime or "미정"
        name = act.placeName or "이름 없음"
        duration = f"{act.duration}분" if act.duration else ""
        act_type = act.type or ""
        lines.append(f"  {i}. [{time_str}] {name} ({act_type}, {duration})")

    return "\n".join(lines)
