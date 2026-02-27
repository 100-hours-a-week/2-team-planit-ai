"""
LangchainClient: LangChain ChatOpenAI 기반 구조화 출력 클라이언트

주요 기능:
- LangChain의 with_structured_output을 사용하여 Pydantic 모델로 직접 파싱
- vLLM OpenAI 호환 API 지원
- 기존 BaseLLMClient 계층과 독립적으로 동작
"""
import logging
from typing import Type, TypeVar

from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage
from pydantic import BaseModel

from app.core.config import settings
from app.core.models.LlmClientDataclass.ChatMessageDataclass import ChatMessage
from app.core.langfuse_setup import get_langfuse_handler

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)


class LangchainClient:
    """LangChain ChatOpenAI 기반 구조화 출력 클라이언트 (vLLM 백엔드)"""

    def __init__(
        self,
        base_url: str = settings.vllm_base_url,
        model: str = settings.vllm_model,
        api_key: str = "EMPTY",
        temperature: float | None = settings.llm_client_temperature,
        max_tokens: int = settings.vllm_client_max_tokens,
    ):
        """
        Args:
            base_url: vLLM 서버 베이스 URL (기본: settings.vllm_base_url)
            model: 모델 이름 (기본: settings.vllm_model)
            api_key: API 키 (vLLM은 "EMPTY" 사용)
            temperature: 생성 온도 (기본: settings.llm_client_temperature)
            max_tokens: 최대 토큰 수 (기본: settings.llm_client_max_tokens)
        """
        self.llm = ChatOpenAI(
            base_url=f"{base_url.rstrip('/')}/v1",
            api_key=api_key,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            streaming=True,
        )

    async def call_structured(self, prompt: ChatMessage, model: Type[T]) -> T:
        """
        구조화 출력으로 LLM 호출

        Args:
            prompt: ChatMessage (system/user 메시지 리스트)
            model: 출력 Pydantic 모델 클래스

        Returns:
            파싱된 Pydantic 모델 인스턴스
        """
        structured_llm = self.llm.with_structured_output(model, include_raw=True)
        messages = self._convert_messages(prompt)

        # Langfuse CallbackHandler 주입
        callbacks = []
        handler = get_langfuse_handler(tags=["langchain-structured"])
        if handler:
            callbacks.append(handler)

        try:
            result = await structured_llm.ainvoke(
                messages,
                config={"callbacks": callbacks} if callbacks else None,
            )
        except Exception as e:
            # 예외 체인에서 잘린 응답 추출 시도
            self._log_truncated_response(e)
            raise

        if result.get("parsing_error"):
            raw_msg = result.get("raw")
            raw_content = getattr(raw_msg, "content", None) if raw_msg else None
            logger.error("LLM 응답 파싱 실패. 잘린 원본 응답:\n%s", raw_content or "추출 불가")
            raise result["parsing_error"]

        return result["parsed"]

    @staticmethod
    def _log_truncated_response(error: Exception) -> None:
        """예외 체인을 순회하며 잘린 LLM 응답을 로깅"""
        exc = error
        while exc is not None:
            # openai.LengthFinishReasonError 등에서 completion 추출
            if hasattr(exc, "completion"):
                completion = exc.completion
                if hasattr(completion, "choices") and completion.choices:
                    choice = completion.choices[0]
                    msg = getattr(choice, "message", None)
                    if msg:
                        content = getattr(msg, "content", None)
                        tool_calls = getattr(msg, "tool_calls", None)
                        logger.error(
                            "토큰 제한으로 잘린 LLM 응답:\ncontent=%s\ntool_calls=%s",
                            content,
                            tool_calls,
                        )
                        return
            exc = getattr(exc, "__cause__", None) or getattr(exc, "__context__", None)

        logger.error("잘린 응답을 추출할 수 없습니다. 에러: %s", error)

    @staticmethod
    def _convert_messages(prompt: ChatMessage) -> list:
        """ChatMessage를 LangChain 메시지 리스트로 변환"""
        messages = []
        for msg in prompt.content:
            if msg.role == "system":
                messages.append(SystemMessage(content=msg.content))
            else:
                messages.append(HumanMessage(content=msg.content))
        return messages
