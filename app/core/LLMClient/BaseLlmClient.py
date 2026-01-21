from abc import ABC, abstractmethod 
from typing import AsyncIterator, Type, TypeVar
from pydantic import BaseModel
from app.core.config import settings

T = TypeVar("T", bound=BaseModel)

class BaseLLMClient(ABC):
    def __init__(
        self, 
        base_url: str,
        timeout: int = settings.llm_client_timeout,
        max_retries: int = settings.llm_client_max_retries,
        max_tokens: int = settings.llm_client_max_tokens,
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
    def call_llm_stream(self, prompt: str) -> AsyncIterator[str]:
        pass

    @abstractmethod
    def call_llm(self, prompt: str) -> str:
        pass