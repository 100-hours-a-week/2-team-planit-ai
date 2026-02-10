from abc import ABC, abstractmethod 
import re
from typing import AsyncIterator, Type, List, Dict, TypeVar
from app.core.config import settings
from app.core.models.LlmClientDataclass.ChatMessageDataclass import MessageData, ChatMessage

T = TypeVar('T')

class BaseLLMClient(ABC):
    def __init__(
        self, 
        base_url: str,
        timeout: int = settings.llm_client_timeout,
        max_retries: int = settings.llm_client_max_retries,
        max_tokens: int = settings.vllm_client_max_tokens,
        temperature: float = settings.llm_client_temperature,
        top_p: float = settings.llm_client_top_p,
    ) -> None:
        self.base_url = base_url
        self.timeout = timeout
        self.max_retries = max_retries
        self.max_tokens = max_tokens
        self.temperature = temperature
        self.top_p = top_p

    @abstractmethod
    async def call_llm_stream(self, prompt: ChatMessage) -> AsyncIterator[str]:
        pass

    @abstractmethod
    async def call_llm(self, prompt: ChatMessage) -> str:
        pass

    @abstractmethod
    async def call_llm_structured(self, prompt: ChatMessage, model: Type[T]) -> T:
        pass

    def messageDataToDict(self, messageData: MessageData) -> Dict[str, str]:
        return {"role": messageData.role, "content": messageData.content}
    
    def dictToMessageData(self, dict: Dict[str, str]) -> MessageData:
        return MessageData(role=dict["role"], content=dict["content"])  

    def chatMessageToDictList(self, chatMessage: ChatMessage) -> List[Dict[str, str]]:
        return [self.messageDataToDict(message) for message in chatMessage.content]
    
    def dictListToChatMessage(self, messages: List[Dict[str, str]]) -> ChatMessage:
        return ChatMessage(content=[self.dictToMessageData(message) for message in messages])

    def stripJsonCodeFence(self, content: str) -> str:
        """
        JSON 코드 블록을 제거하는 함수
        """
        stripped = content.strip()
        if "```" not in stripped:
            return stripped

        fenced_match = re.search(r"```(?:json)?\s*(.*?)\s*```", stripped, re.IGNORECASE | re.DOTALL)
        if fenced_match:
            return fenced_match.group(1).strip()

        if stripped.startswith("```"):
            first_newline = stripped.find("\n")
            if first_newline == -1:
                return ""
            stripped = stripped[first_newline + 1:]
            last_fence = stripped.rfind("```")
            if last_fence != -1:
                stripped = stripped[:last_fence]
            return stripped.strip()

        return stripped
