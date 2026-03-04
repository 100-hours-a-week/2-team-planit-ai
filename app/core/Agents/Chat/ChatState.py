"""
ChatState: 대화형 챗봇 시스템의 LangGraph 상태 모델

대화 컨텍스트, 사용자 의도, 현재 일정 데이터 등을 관리합니다.
오케스트레이터 및 모든 하위 에이전트가 공유하는 상태입니다.

ReActChatState: ReAct 패턴 기반 오케스트레이터용 상태 모델
"""
from typing import List, Optional, TypedDict
from enum import Enum

from langgraph.graph import MessagesState

from app.schemas.Itinerary import ItineraryResponse


class UserIntent(str, Enum):
    """사용자 의도 분류"""
    INFO_RECOMMEND = "info_recommend"       # 여행지/맛집 추천
    INFO_DELIVERY = "info_delivery"         # 일반 정보 전달
    SCHEDULE_EDIT = "schedule_edit"         # 일정 수정
    SCHEDULE_DELETE = "schedule_delete"     # 일정 삭제
    SCHEDULE_ADD = "schedule_add"           # 일정 추가
    OFF_TOPIC = "off_topic"                # 관련 없는 주제
    UNRESOLVABLE = "unresolvable"          # 처리 불가


class MessageRole(str, Enum):
    """메시지 역할"""
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"


class ChatMessage(TypedDict):
    """대화 메시지 단위"""
    role: str       # MessageRole 값
    content: str    # 메시지 내용


class TargetEventInfo(TypedDict, total=False):
    """수정 대상 이벤트 식별 정보 (TargetIdentifier 출력)"""
    day: int                        # 몇 일차 (1-indexed)
    event_index: Optional[int]      # 이벤트 순서 (1-indexed). None이면 전체일
    action: str                     # "edit" | "delete" | "add"
    detail: str                     # 사용자 요청 상세 ("맛집으로 변경" 등)
    is_resolvable: bool             # 처리 가능 여부
    reject_reason: Optional[str]    # 처리 불가 시 사유
    target_scope: str               # "single" | "all_day"
    requested_place: Optional[str]  # 사용자가 요청한 구체적 장소 이름


class ChatState(TypedDict, total=False):
    """대화형 챗봇 LangGraph 상태

    오케스트레이터 → 하위 에이전트 전체에서 공유됩니다.
    """
    # 대화 컨텍스트
    session_id: str                         # 대화 세션 ID
    messages: List[ChatMessage]             # 대화 히스토리
    current_user_message: str               # 현재 사용자 입력

    # 주제 필터링 결과
    is_on_topic: bool                       # 관련 주제 여부

    # 의도 분류
    user_intent: str                        # UserIntent 값

    # 일정 데이터 (외부 백엔드에서 전달받음)
    current_itinerary: Optional[ItineraryResponse]  # 현재 일정

    # 백엔드 연동
    user_jwt: Optional[str]                         # 백엔드 API 인증용 JWT
    backend_itinerary_data: Optional[dict]           # 원본 백엔드 GET 응답 (dayId, activityId 매핑용)

    # 일정 변경 브랜치
    target_event: Optional[TargetEventInfo]         # 수정 대상 식별 결과
    resolved_place: Optional[dict]                  # PlaceResolver 검증 결과
    modified_itinerary: Optional[ItineraryResponse] # 변경된 일정
    consistency_feedback: Optional[str]              # 정합성 검사 피드백
    consistency_valid: bool                          # 정합성 통과 여부
    consistency_attempts: int                        # 정합성 재시도 횟수

    # 정보 소개 브랜치
    search_results: List[dict]              # 검색 결과 목록
    info_sufficient: bool                   # 정보 충분성 여부
    info_search_attempts: int               # 정보 검색 시도 횟수

    # Human-in-the-loop
    needs_clarification: bool               # 추가 정보 필요 여부
    clarification_question: Optional[str]    # 사용자에게 할 질문
    user_clarification: Optional[str]        # 사용자의 보충 답변 (resume 시 주입)

    # 최종 응답
    response: str                           # 최종 응답 텍스트


class ReActChatState(MessagesState):
    """ReAct 에이전트 상태 (MessagesState 확장)

    MessagesState가 제공하는 messages 필드 (LangChain BaseMessage 리스트)에
    도메인 컨텍스트를 추가합니다.

    messages: ReAct 에이전트 루프의 메시지 (System, Human, AI, Tool)
    """
    session_id: str
    current_itinerary: Optional[ItineraryResponse]
    user_jwt: Optional[str]
    backend_itinerary_data: Optional[dict]
    response: str

