"""
InfoDeliveryAgent: 정보 전달 에이전트

Tavily를 사용하여 일반 여행 정보를 검색하고,
LLM으로 충분성을 판단하여 필요 시 추가 검색을 수행합니다.

흐름:
1. 사용자 질문을 검색 쿼리로 변환
2. Tavily로 웹 검색
3. LLM이 정보 충분성 판단 (self-eval)
4. 불충분 → 추가 검색 쿼리 생성 → 재검색 (최대 MAX_SEARCH_ATTEMPTS)
5. 충분 → 최종 응답 생성
"""
import logging
from typing import Optional

from pydantic import BaseModel, Field

from app.core.Agents.Chat.ChatState import ChatState
from app.core.Agents.Chat.InfoAgent.TavilySearchTool import TavilySearchTool
from app.core.LLMClient.BaseLlmClient import BaseLLMClient
from app.core.models.LlmClientDataclass.ChatMessageDataclass import (
    ChatMessage,
    MessageData,
)

logger = logging.getLogger(__name__)

MAX_SEARCH_ATTEMPTS = 3

SUFFICIENCY_SYSTEM_PROMPT = (
    "당신은 여행 정보 품질 평가 전문가입니다. "
    "사용자의 질문과 검색 결과를 비교하여 정보가 충분한지 판단합니다.\n"
    "JSON 형식으로만 응답하세요."
)

DELIVERY_SYSTEM_PROMPT = (
    "당신은 친절한 여행 정보 전문가입니다. "
    "검색 결과를 바탕으로 사용자의 질문에 정확하고 유용하게 답변합니다.\n"
    "- 핵심 정보를 명확하게 전달하세요.\n"
    "- 출처가 있으면 언급하세요.\n"
    "- 한국어로 친근하게 답변하세요.\n"
    "- 확실하지 않은 정보는 그렇다고 밝히세요."
)


class SufficiencyResult(BaseModel):
    """정보 충분성 평가 결과"""
    is_sufficient: bool = Field(description="정보가 충분한지 여부")
    reason: str = Field(default="", description="판단 근거")
    follow_up_query: Optional[str] = Field(
        default=None,
        description="추가 검색이 필요한 경우의 검색 쿼리",
    )


class InfoDeliveryAgent:
    """정보 전달 에이전트

    Tavily 웹 검색 + LLM 충분성 루프로
    사용자의 일반 여행 정보 질문에 답변합니다.
    """

    def __init__(
        self,
        llm_client: BaseLLMClient,
        tavily_tool: Optional[TavilySearchTool] = None,
    ):
        self.llm_client = llm_client
        self.tavily_tool = tavily_tool or TavilySearchTool()

    async def deliver(self, state: ChatState) -> dict:
        """정보 전달 수행

        충분성 루프:
        1. Tavily 검색 → LLM 충분성 판단
        2. 불충분 시 추가 쿼리로 재검색 (최대 MAX_SEARCH_ATTEMPTS)
        3. 충분 시 최종 응답 생성

        Args:
            state: 현재 대화 상태

        Returns:
            dict: ChatState 업데이트
                (search_results, info_sufficient, info_search_attempts, response)
        """
        user_message = state.get("current_user_message", "")
        attempts = state.get("info_search_attempts", 0)
        accumulated_results: list[dict] = list(state.get("search_results", []))

        current_query = user_message
        is_sufficient = False

        while attempts < MAX_SEARCH_ATTEMPTS:
            attempts += 1

            # 1. Tavily 검색
            search_response = await self.tavily_tool.search(
                query=current_query,
                search_depth="advanced" if attempts > 1 else "basic",
                include_answer=True,
            )

            search_text = self.tavily_tool.format_results_as_text(search_response)

            # 검색 결과를 누적
            for r in search_response.results:
                accumulated_results.append({
                    "title": r.title,
                    "url": r.url,
                    "content": r.content,
                    "score": r.score,
                    "query": current_query,
                })

            # 2. 충분성 판단
            sufficiency = await self._evaluate_sufficiency(
                user_message=user_message,
                search_text=search_text,
            )

            if sufficiency.is_sufficient:
                is_sufficient = True
                break

            # 3. 추가 검색 쿼리 생성
            if sufficiency.follow_up_query:
                current_query = sufficiency.follow_up_query
                logger.info(
                    f"정보 불충분 (시도 {attempts}/{MAX_SEARCH_ATTEMPTS}), "
                    f"추가 검색: '{current_query}'"
                )
            else:
                logger.info(
                    f"정보 불충분하나 추가 쿼리 없음 (시도 {attempts}/{MAX_SEARCH_ATTEMPTS})"
                )
                break

        # 4. 최종 응답 생성
        all_search_text = self._compile_search_texts(accumulated_results)
        response = await self._generate_response(
            user_message=user_message,
            search_text=all_search_text,
        )

        return {
            "search_results": accumulated_results,
            "info_sufficient": is_sufficient,
            "info_search_attempts": attempts,
            "response": response,
        }

    async def _evaluate_sufficiency(
        self,
        user_message: str,
        search_text: str,
    ) -> SufficiencyResult:
        """LLM으로 정보 충분성 평가"""
        prompt = ChatMessage(content=[
            MessageData(
                role="system",
                content=SUFFICIENCY_SYSTEM_PROMPT,
            ),
            MessageData(
                role="user",
                content=(
                    f"사용자 질문: {user_message}\n\n"
                    f"검색 결과:\n{search_text}\n\n"
                    f"위 검색 결과가 사용자의 질문에 충분히 답변할 수 있는지 평가하세요.\n"
                    f"불충분하면 추가로 검색할 쿼리를 제안하세요."
                ),
            ),
        ])

        try:
            result = await self.llm_client.call_llm_structured(
                prompt, SufficiencyResult
            )
            return result
        except Exception as e:
            logger.error(f"충분성 평가 실패: {e}")
            # 평가 실패 시 충분한 것으로 간주 (무한 루프 방지)
            return SufficiencyResult(
                is_sufficient=True,
                reason=f"충분성 평가 실패: {e}",
            )

    async def _generate_response(
        self,
        user_message: str,
        search_text: str,
    ) -> str:
        """검색 결과를 바탕으로 최종 응답 생성"""
        prompt = ChatMessage(content=[
            MessageData(
                role="system",
                content=DELIVERY_SYSTEM_PROMPT,
            ),
            MessageData(
                role="user",
                content=(
                    f"사용자 질문: {user_message}\n\n"
                    f"검색 결과:\n{search_text}\n\n"
                    f"위 정보를 바탕으로 사용자의 질문에 답변해주세요."
                ),
            ),
        ])

        try:
            return await self.llm_client.call_llm(prompt)
        except Exception as e:
            logger.error(f"응답 생성 LLM 호출 실패: {e}")
            if search_text:
                return (
                    f"검색 결과를 바탕으로 답변드립니다:\n\n{search_text[:1000]}"
                )
            return "죄송합니다. 정보를 찾는 데 문제가 발생했습니다."

    @staticmethod
    def _compile_search_texts(results: list[dict]) -> str:
        """누적된 검색 결과를 하나의 텍스트로 통합"""
        if not results:
            return "검색 결과 없음"

        lines = []
        for i, r in enumerate(results, 1):
            title = r.get("title", "")
            content = r.get("content", "")[:300]
            url = r.get("url", "")
            lines.append(f"[{i}] {title}")
            if url:
                lines.append(f"    URL: {url}")
            lines.append(f"    {content}")

        return "\n\n".join(lines)
