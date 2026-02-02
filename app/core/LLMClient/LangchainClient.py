"""
LangchainClient: LangChain ChatOpenAI 기반 구조화 출력 클라이언트

주요 기능:
- LangChain의 with_structured_output을 사용하여 Pydantic 모델로 직접 파싱
- vLLM OpenAI 호환 API 지원
- 기존 BaseLLMClient 계층과 독립적으로 동작
"""
from typing import Type, TypeVar

from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage
from pydantic import BaseModel

from app.core.config import settings
from app.core.models.LlmClientDataclass.ChatMessageDataclass import ChatMessage

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
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
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
        structured_llm = self.llm.with_structured_output(model)
        messages = self._convert_messages(prompt)
        return await structured_llm.ainvoke(messages)

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
