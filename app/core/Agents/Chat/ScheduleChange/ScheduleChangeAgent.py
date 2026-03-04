"""
ScheduleChangeAgent: 일정 변경 총괄 에이전트 (LangGraph)

일정 변경 브랜치의 전체 흐름을 관리합니다:
1. TargetIdentifier로 수정 대상 식별 + 장소 이름 추출
2. PlaceResolver로 장소 검증 (edit/add일 때)
3. 식별 결과에 따라 CRUD 도구/에이전트 호출
4. ConsistencyChecker로 정합성 검사
"""
from cmath import e
import logging
from typing import Optional

from langgraph.graph import StateGraph, END

from app.core.LLMClient.BaseLlmClient import BaseLLMClient
from app.core.Agents.Chat.ChatState import ChatState, UserIntent
from app.core.Agents.Chat.ScheduleChange.TargetIdentifier import TargetIdentifier
from app.core.Agents.Chat.ScheduleChange.PlaceResolver import PlaceResolver
from app.core.Agents.Chat.ScheduleChange.EventDeleteTool import EventDeleteTool
from app.core.Agents.Chat.ScheduleChange.EventAddTool import EventAddTool
from app.core.Agents.Chat.ScheduleChange.EventEditAgent import EventEditAgent
from app.core.Agents.Chat.ScheduleChange.ConsistencyChecker import (
    ConsistencyChecker,
    MAX_CONSISTENCY_ATTEMPTS,
)
from app.schemas.Itinerary import ActivityResponse, ItineraryResponse
from app.core.Agents.Poi.VectorDB.VectorSearchAgent import VectorSearchAgent
from app.core.BackendClient import BackendClient
from app.core.langfuse_setup import get_langfuse_handler

from langfuse import observe

logger = logging.getLogger(__name__)


class ScheduleChangeAgent:
    """일정 변경 총괄 에이전트

    LangGraph StateGraph로 아래 흐름을 관리합니다:
    identify → resolve_place(edit/add) → CRUD → consistency → response

    Flow:
    1. identify_target: 수정 대상 식별 + 장소 이름 추출
       → 처리 불가 시 종료
    2. resolve_place: 장소 검증 (edit/add이고 requested_place가 있을 때)
       → 장소 못 찾으면 안내 후 종료
    3. execute_edit / execute_delete / execute_add: CRUD 실행
    4. check_consistency: 정합성 검사
    5. generate_response: 응답 생성
    """

    def __init__(
        self,
        llm_client: BaseLLMClient,
        total_budget: int,
        travel_start_date: str,
        travel_end_date: str,
        place_resolver: PlaceResolver,
        backend_client: Optional[BackendClient] = None,
    ):
        """
        Args:
            llm_client: vLLM 클라이언트
            total_budget: 총 예산 (원)
            travel_start_date: 여행 시작일
            travel_end_date: 여행 종료일
            place_resolver: 장소 검증기
            backend_client: 백엔드 API 클라이언트 (일정 수정 PATCH 호출용)
        """
        self.llm_client = llm_client
        self.target_identifier = TargetIdentifier(llm_client)
        self.place_resolver = place_resolver
        self.event_edit_agent = EventEditAgent(llm_client)
        self.backend_client = backend_client
        self.consistency_checker = ConsistencyChecker(
            total_budget=total_budget,
            travel_start_date=travel_start_date,
            travel_end_date=travel_end_date,
        )
        self.graph = self._build_graph()

    def _build_graph(self) -> StateGraph:
        """LangGraph 워크플로우 빌드"""
        graph = StateGraph(ChatState)

        # 노드 추가
        graph.add_node("identify_target", self._identify_target)
        graph.add_node("resolve_place", self._resolve_place)
        graph.add_node("execute_edit", self._execute_edit)
        graph.add_node("execute_delete", self._execute_delete)
        graph.add_node("execute_add", self._execute_add)
        graph.add_node("check_consistency", self._check_consistency)
        graph.add_node("generate_response", self._generate_response)

        # 엔트리 포인트
        graph.set_entry_point("identify_target")

        # identify → 장소 검증 필요 여부 판단
        graph.add_conditional_edges(
            "identify_target",
            self._route_after_identify,
            {
                "resolve": "resolve_place",
                "delete": "execute_delete",
                "end": "generate_response",
            },
        )

        # resolve_place → CRUD 라우팅
        graph.add_conditional_edges(
            "resolve_place",
            self._route_after_resolve,
            {
                "edit": "execute_edit",
                "add": "execute_add",
                "end": "generate_response",
            },
        )

        # CRUD → 정합성 검사
        graph.add_edge("execute_edit", "check_consistency")
        graph.add_edge("execute_delete", "check_consistency")
        graph.add_edge("execute_add", "check_consistency")

        # 정합성 결과 라우팅
        graph.add_conditional_edges(
            "check_consistency",
            self._route_after_consistency,
            {
                "pass": "generate_response",
                "retry": "generate_response",
            },
        )

        graph.add_edge("generate_response", END)

        return graph.compile()

    # ─── 노드 구현 ───────────────────────────────────────

    async def _identify_target(self, state: ChatState) -> dict:
        """수정 대상 식별"""
        if not state.get("current_user_message"):
            raise ValueError("사용자 메시지가 없습니다.")
        if not state.get("current_itinerary"):
            raise ValueError("일정 데이터가 없습니다.")

        target = await self.target_identifier.identify(
            user_message=state["current_user_message"],
            itinerary=state["current_itinerary"],
        )

        return {"target_event": target}

    async def _resolve_place(self, state: ChatState) -> dict:
        """장소 검증 (SQLite로 조회)"""
        target = state.get("target_event")
        requested_place = target.get("requested_place") if target else None

        if not requested_place:
            # 장소 이름이 없으면 검증 스킵
            return {"resolved_place": None}

        # TODO: city 정보를 어디서 가져올지 결정 필요
        resolved = await self.place_resolver.resolve(
            place_name=requested_place,
            city="",
        )

        return {"resolved_place": resolved.to_dict()}

    async def _execute_edit(self, state: ChatState) -> dict:
        """이벤트 수정 실행 → 백엔드 PATCH 호출"""
        itinerary = state.get("current_itinerary")
        target = state.get("target_event")
        resolved = state.get("resolved_place")

        if not itinerary or not target:
            raise ValueError("일정 데이터 또는 수정 대상이 없습니다.")

        modified, error = await self.event_edit_agent.edit(
            itinerary=itinerary,
            day=target.get("day", 0),
            event_index=target.get("event_index"),
            user_request=target.get("detail", ""),
            target_scope=target.get("target_scope", "single"),
            resolved_place=resolved,
        )

        if error:
            raise ValueError(f"수정 실패: {error}")

        # 백엔드 PATCH API 호출
        await self._apply_to_backend(state, modified, target_day=target.get("day", 0))

        return {"modified_itinerary": modified}

    async def _execute_delete(self, state: ChatState) -> dict:
        """이벤트 삭제 실행 → 백엔드 PATCH 호출"""
        itinerary = state.get("current_itinerary")
        target = state.get("target_event")

        if not itinerary or not target:
            raise ValueError("일정 데이터 또는 수정 대상이 없습니다.")

        modified, error = EventDeleteTool.delete(
            itinerary=itinerary,
            day=target.get("day", 0),
            event_index=target.get("event_index"),
            target_scope=target.get("target_scope", "single"),
        )

        if error:
            raise ValueError(f"삭제 실패: {error}")

        # 백엔드 PATCH API 호출
        await self._apply_to_backend(state, modified, target_day=target.get("day", 0))

        return {"modified_itinerary": modified}

    async def _execute_add(self, state: ChatState) -> dict:
        """이벤트 추가 실행 → 백엔드 PATCH 호출"""
        itinerary = state.get("current_itinerary")
        target = state.get("target_event")
        resolved = state.get("resolved_place")

        if not itinerary or not target:
            raise ValueError("일정 데이터 또는 수정 대상이 없습니다.")

        # 검증된 장소가 있으면 활용, 없으면 detail에서 생성
        if resolved and resolved.get("is_found"):
            new_activity = EventAddTool.create_activity_from_resolved(resolved)
        else:
            new_activity = ActivityResponse(
                placeName=target.get("requested_place") or target.get("detail", "새 장소"),
                type="attraction",
                eventOrder=0,
                duration=60,
                memo="챗봇에서 추가됨",
            )

        modified, error = EventAddTool.add(
            itinerary=itinerary,
            day=target.get("day", 0),
            activity=new_activity,
            position=target.get("event_index"),
        )

        if error:
            raise ValueError(f"추가 실패: {error}")

        # 백엔드 PATCH API 호출
        await self._apply_to_backend(state, modified, target_day=target.get("day", 0))

        return {"modified_itinerary": modified}

    def _check_consistency(self, state: ChatState) -> dict:
        """정합성 검사"""
        modified = state.get("modified_itinerary")
        attempts = state.get("consistency_attempts", 0)

        if not modified:
            return {
                "consistency_valid": False,
                "consistency_feedback": "변경된 일정이 없습니다.",
                "consistency_attempts": attempts + 1,
            }

        is_valid, feedback = self.consistency_checker.check(modified)

        return {
            "consistency_valid": is_valid,
            "consistency_feedback": feedback,
            "consistency_attempts": attempts + 1,
        }

    def _generate_response(self, state: ChatState) -> dict:
        """응답 생성"""
        target = state.get("target_event")

        # 처리 불가
        if target and not target.get("is_resolvable", False):
            reason = target.get("reject_reason", "요청을 처리할 수 없습니다.")
            return {"response": f"죄송합니다. {reason}"}

        # 장소 검증 실패
        resolved = state.get("resolved_place")
        if resolved and not resolved.get("is_found", False):
            place = resolved.get("place_name", "요청한 장소")
            return {
                "response": (
                    f"'{place}'을(를) 데이터베이스에서 찾지 못했습니다. "
                    f"다른 장소를 지정하거나 더 정확한 이름으로 다시 시도해주세요."
                )
            }

        # 이미 에러 응답이 있는 경우
        if state.get("response"):
            return {}

        modified = state.get("modified_itinerary")
        is_valid = state.get("consistency_valid", False)
        feedback = state.get("consistency_feedback")

        if modified and is_valid:
            return {
                "response": "일정이 성공적으로 수정되었습니다.",
                "current_itinerary": modified,
            }
        elif modified and feedback:
            return {
                "response": (
                    f"일정이 수정되었지만 정합성 문제가 있습니다:\n{feedback}\n"
                    f"수정된 일정을 적용했으나 위 사항을 확인해주세요."
                ),
                "current_itinerary": modified,
            }
        else:
            return {"response": "일정 수정을 완료하지 못했습니다."}

    # ─── 백엔드 PATCH 반영 ────────────────────────────────

    async def _apply_to_backend(
        self,
        state: ChatState,
        modified: ItineraryResponse,
        target_day: int,
    ) -> None:
        """수정된 일정을 PATCH API로 백엔드에 반영

        Args:
            state: 현재 ChatState (user_jwt, backend_itinerary_data 포함)
            modified: 수정된 일정
            target_day: 수정 대상 일차 (1-indexed)
        """
        if not self.backend_client:
            logger.warning("BackendClient 미설정 — PATCH 호출 스킵")
            return

        user_jwt = state.get("user_jwt")
        backend_data = state.get("backend_itinerary_data")

        if not user_jwt:
            logger.warning("user_jwt 없음 — PATCH 호출 스킵")
            return

        if not backend_data:
            logger.warning("backend_itinerary_data 없음 — PATCH 호출 스킵")
            return

        try:
            # 백엔드 원본 데이터에서 dayId 추출
            backend_itineraries = backend_data.get("itineraries", [])
            if target_day < 1 or target_day > len(backend_itineraries):
                logger.error(f"유효하지 않은 target_day={target_day}")
                return

            day_data = backend_itineraries[target_day - 1]
            day_id = day_data.get("itineraryDayId")

            if day_id is None:
                logger.error("백엔드 데이터에서 itineraryDayId를 찾을 수 없습니다.")
                return

            # modified에서 해당 일차의 activities를 PATCH 형식으로 변환
            places = self._convert_to_patch_format(
                modified, target_day, day_data,
            )

            await self.backend_client.update_day_itinerary(
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
            # PATCH 실패해도 로컬 수정은 유지 (사용자에게 알림)

    @staticmethod
    def _convert_to_patch_format(
        modified: ItineraryResponse,
        target_day: int,
        backend_day_data: dict,
    ) -> list[dict]:
        """수정된 일정을 PATCH API body의 places 형식으로 변환

        Args:
            modified: 수정된 ItineraryResponse
            target_day: 대상 일차 (1-indexed)
            backend_day_data: 원본 백엔드 일차 데이터 (activityId 매핑용)

        Returns:
            list[dict]: PATCH body의 places 배열
        """
        day_itin = modified.itineraries[target_day - 1]

        # 기존 activityId 매핑 (placeName → activityId)
        existing_activities = {}
        for act in backend_day_data.get("activities", []):
            existing_activities[act.get("placeName", "")] = act.get("activityId")

        places = []
        for activity in day_itin.activities:
            # route 타입은 PATCH에서 제외
            if activity.type == "route":
                continue

            # startTime 변환: "HH:mm:ss" → {hour, minute, second, nano}
            start_time_obj = {"hour": 0, "minute": 0, "second": 0, "nano": 0}
            if activity.startTime:
                parts = activity.startTime.split(":")
                if len(parts) >= 2:
                    start_time_obj["hour"] = int(parts[0])
                    start_time_obj["minute"] = int(parts[1])
                    if len(parts) >= 3:
                        start_time_obj["second"] = int(parts[2])

            # 기존 activityId 매핑 시도
            activity_id = existing_activities.get(activity.placeName, 0)

            # googleMapUrl에서 placeId 추출 시도
            place_id = ""
            google_map_url = activity.googleMapUrl or ""
            if "place_id:" in google_map_url:
                place_id = google_map_url.split("place_id:")[-1].split("&")[0]

            places.append({
                "activityId": activity_id,
                "placeName": activity.placeName or "",
                "placeId": place_id,
                "googleMapUrl": google_map_url,
                "startTime": start_time_obj,
                "durationMinutes": activity.duration,
                "cost": activity.cost or 0,
                "memo": activity.memo or "",
            })

        return places

    # ─── 라우팅 함수 ─────────────────────────────────────

    def _route_after_identify(self, state: ChatState) -> str:
        """TargetIdentifier 결과에 따른 라우팅"""
        target = state.get("target_event")

        if not target or not target.get("is_resolvable"):
            return "end"

        action = target.get("action")
        if not action:
            return "end"

        # delete는 장소 검증 불필요 → 바로 실행
        if action == "delete":
            return "delete"

        # edit/add는 장소 검증 필요할 수 있음 → resolve_place 노드로
        if action in ("edit", "add"):
            return "resolve"

        return "end"

    def _route_after_resolve(self, state: ChatState) -> str:
        """장소 검증 결과에 따른 라우팅"""
        target = state.get("target_event")
        resolved = state.get("resolved_place")

        if not target:
            return "end"

        action = target.get("action")
        requested_place = target.get("requested_place")

        # 구체적 장소를 요청했는데 못 찾으면 종료
        if requested_place and resolved and not resolved.get("is_found"):
            return "end"

        # CRUD 실행
        if action == "edit":
            return "edit"
        elif action == "add":
            return "add"

        return "end"

    def _route_after_consistency(self, state: ChatState) -> str:
        """정합성 검사 결과에 따른 라우팅"""
        is_valid = state.get("consistency_valid", False)
        attempts = state.get("consistency_attempts", 0)

        if is_valid:
            return "pass"

        if attempts >= MAX_CONSISTENCY_ATTEMPTS:
            logger.warning(
                f"정합성 재시도 횟수 초과 ({attempts}/{MAX_CONSISTENCY_ATTEMPTS})"
            )

        return "retry"

    # ─── 실행 ────────────────────────────────────────────

    @observe(name="schedule-change")
    async def run(self, state: ChatState) -> ChatState:
        """일정 변경 워크플로우 실행

        Args:
            state: 현재 대화 상태

        Returns:
            ChatState: 업데이트된 대화 상태
        """
        # Langfuse CallbackHandler 주입
        callbacks = []
        handler = get_langfuse_handler(tags=["schedule-change"])
        if handler:
            callbacks.append(handler)

        result = await self.graph.ainvoke(
            state,
            config={"callbacks": callbacks} if callbacks else None,
        )
        return result
