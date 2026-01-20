import asyncio
import json
from typing import AsyncIterator, Type, TypeVar, Optional
import httpx
from pydantic import BaseModel
from app.core.LLMClient.BaseLlmClient import BaseLLMClient, T
from app.core.config import settings

class OpenAiApiClient(BaseLLMClient):
    """
    OpenAI API 클라이언트 (httpx 기반 async 스트리밍 지원)
    """

    def __init__(
        self,
        base_url: str = settings.openai_base_url,
        model: Optional[str] = settings.openai_model,
        timeout: int = settings.llm_client_timeout,
        max_retries: int = settings.llm_client_max_retries,
        max_tokens: int = settings.llm_client_max_tokens,
        temperature: float = settings.llm_client_temperature,
        top_p: float = settings.llm_client_top_p,
        api_key: Optional[str] = settings.openai_api_key,
    ) -> None:
        super().__init__(
            base_url=base_url,
            timeout=timeout,
            max_retries=max_retries,
            max_tokens=max_tokens,
            temperature=temperature,
            top_p=top_p,
        )
        self.api_key = api_key
        self.model = model

    async def call_llm_stream(self, prompt: str) -> AsyncIterator[str]:
        """
        스트리밍 OpenAI API 호출 (async)
        """
        request_data = {
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
            "max_completion_tokens": self.max_tokens,
            "top_p": self.top_p,
            "stream": True,
        }
        if self.temperature is not None:
            request_data["temperature"] = self.temperature

        for attempt in range(self.max_retries):
            try:
                async with httpx.AsyncClient(
                    timeout=self.timeout,
                    headers={
                        "Authorization": f"Bearer {settings.openai_api_key}",
                        "Content-Type": "application/json",
                    },
                ) as client:
                    async with client.stream(
                        "POST",
                        f"{self.base_url}/chat/completions",
                        json=request_data,
                    ) as response:
                        if response.status_code != 200:
                            error_detail = await response.aread()
                            yield f"OpenAI API 오류 (HTTP {response.status_code}): {error_detail.decode()}"
                            return

                        async for line in response.aiter_lines():
                            if not line or not line.startswith("data: "):
                                continue

                            data_str = line[6:]
                            if data_str.strip() == "[DONE]":
                                return

                            try:
                                data = json.loads(data_str)
                            except json.JSONDecodeError:
                                continue

                            if "choices" in data and data["choices"]:
                                choice = data["choices"][0]
                                if "delta" in choice and "content" in choice["delta"]:
                                    content = choice["delta"]["content"]
                                    if content:
                                        yield content
                        return

            except (httpx.RequestError, httpx.TimeoutException) as e:
                if attempt == self.max_retries - 1:
                    yield f"OpenAI API 요청 실패: {str(e)}"
                    return
                await asyncio.sleep(2 ** attempt)
                continue

    def call_llm(self, prompt: str) -> str:
        """
        비스트리밍 OpenAI API 호출 (sync)
        """
        import time
        request_data = {
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
            "max_completion_tokens": self.max_tokens,
            "top_p": self.top_p,
            "stream": False,
        }
        if self.temperature is not None:
            request_data["temperature"] = self.temperature

        for attempt in range(self.max_retries):
            try:
                with httpx.Client(
                    timeout=self.timeout,
                    headers={
                        "Authorization": f"Bearer {settings.openai_api_key}",
                        "Content-Type": "application/json",
                    },
                ) as client:
                    response = client.post(
                        f"{self.base_url}/chat/completions",
                        json=request_data,
                    )
                    
                    if response.status_code != 200:
                        return f"OpenAI API 오류 (HTTP {response.status_code}): {response.text}"

                    data = response.json()
                    if "choices" in data and data["choices"]:
                        return data["choices"][0]["message"]["content"]
                    return ""

            except (httpx.RequestError, httpx.TimeoutException) as e:
                if attempt == self.max_retries - 1:
                    return f"OpenAI API 요청 실패: {str(e)}"
                time.sleep(2 ** attempt)
                continue
