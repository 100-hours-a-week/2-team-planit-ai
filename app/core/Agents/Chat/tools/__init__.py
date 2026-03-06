"""
tools: ReAct 에이전트 도구 팩토리

create_tools() 함수가 클로저 패턴으로 도구 함수들을 생성합니다.
state_container(dict)를 캡처하여 도구가 current_itinerary 등에 접근할 수 있게 합니다.
"""
from typing import Optional

from app.core.Agents.Chat.tools.itinerary_tools import create_itinerary_tools
from app.core.Agents.Chat.tools.search_tools import create_search_tools
from app.core.Agents.Chat.tools.backend_tools import create_backend_tools

from app.core.Agents.Chat.ScheduleChange.PlaceResolver import PlaceResolver
from app.core.Agents.Chat.ScheduleChange.EventEditAgent import EventEditAgent
from app.core.Agents.Chat.ScheduleChange.ConsistencyChecker import ConsistencyChecker
from app.core.Agents.Chat.InfoAgent.PlaceSearchAgent import PlaceSearchAgent
from app.core.Agents.Chat.InfoAgent.TavilySearchTool import TavilySearchTool
from app.core.BackendClient import BackendClient


def create_tools(
    state_container: dict,
    place_resolver: PlaceResolver,
    event_edit_agent: EventEditAgent,
    consistency_checker: ConsistencyChecker,
    place_search: PlaceSearchAgent,
    tavily_tool: TavilySearchTool,
    backend_client: Optional[BackendClient] = None,
) -> list:
    """ReAct 에이전트용 도구 리스트 생성

    클로저 패턴으로 state_container를 캡처하여
    도구 함수들이 현재 일정 데이터에 접근할 수 있게 합니다.

    Args:
        state_container: 요청별 상태 컨테이너 (current_itinerary 등)
        place_resolver: 장소 검증 모듈
        event_edit_agent: 이벤트 수정 에이전트
        consistency_checker: 정합성 검사 모듈
        place_search: 멀티소스 장소 검색 에이전트
        tavily_tool: Tavily 검색 도구
        backend_client: 백엔드 API 클라이언트

    Returns:
        list: LangChain @tool 데코레이터가 적용된 도구 함수 리스트
    """
    tools = []

    tools.extend(create_itinerary_tools(
        state_container=state_container,
        place_resolver=place_resolver,
        event_edit_agent=event_edit_agent,
        consistency_checker=consistency_checker,
        backend_client=backend_client,
    ))

    tools.extend(create_search_tools(
        tavily_tool=tavily_tool,
        place_search=place_search,
    ))

    tools.extend(create_backend_tools(
        state_container=state_container,
        backend_client=backend_client,
    ))

    return tools
