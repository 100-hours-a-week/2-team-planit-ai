import asyncio
import json
import httpx
from typing import AsyncIterator, Optional, Type, TypeVar
from app.core.LLMClient.BaseLlmClient import BaseLLMClient
from app.core.config import settings
from app.core.models.LlmClientDataclass.ChatMessageDataclass import ChatMessgage

T = TypeVar('T')

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
    ):
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

    async def call_llm_stream(self, prompt: ChatMessgage) -> AsyncIterator[str]:
        """
        스트리밍 OpenAI API 호출 (async)
        """
        request_data = {
            "model": self.model,
            "messages": self.chatMessageToDictList(prompt),
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

    async def call_llm(self, prompt: ChatMessgage) -> str:
        """
        비스트리밍 OpenAI API 호출 (sync)
        """
        import time
        request_data = {
            "model": self.model,
            "messages": self.chatMessageToDictList(prompt),
            "max_completion_tokens": self.max_tokens,
            "top_p": self.top_p,
            "stream": False,
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
                    response = await client.post(
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
                await asyncio.sleep(2 ** attempt)
                continue

    async def call_llm_structured(self, prompt: ChatMessgage, model: Type[T]) -> T:
        """
        vLLM의 Guided Decoding 기능을 사용하여 구조화된 출력을 받아옴
        """
        request_data = {
            "model": self.model,
            "messages": self.chatMessageToDictList(prompt),
            "max_completion_tokens": self.max_tokens,
            "top_p": self.top_p,
            "stream": False,
            "response_format": {
              "type": "json_schema",
              "json_schema": {
                  "name": model.__name__,
                  "schema": _enforce_no_additional_props(model.model_json_schema()),
                  "strict": True,
              },
          },
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
                    response = await client.post(
                        f"{self.base_url}/chat/completions",
                        json=request_data,
                    )

                    if response.status_code == 503:
                        await asyncio.sleep(2 ** attempt)
                        continue

                    if response.status_code != 200:
                        raise Exception(f"LLM 서버 오류 (HTTP {response.status_code}): {response.text}")

                    data = response.json()
                    if "choices" in data and data["choices"]:
                        content = data["choices"][0]["message"]["content"]
                        try:
                            content = self.stripJsonCodeFence(content)
                            return model.model_validate_json(content)
                        except Exception as e:
                            raise Exception(f"JSON 파싱 오류: {str(e)}\nContent: {content}")
                    
                    raise Exception("LLM 응답에 choices가 없습니다.")

            except (httpx.RequestError, httpx.TimeoutException) as e:
                if attempt == self.max_retries - 1:
                    raise Exception(f"LLM 서버 요청 실패: {str(e)}")
                await asyncio.sleep(2 ** attempt)
                continue
    
def _enforce_no_additional_props(schema: dict) -> dict:
    if schema.get("type") == "object":
        schema.setdefault("additionalProperties", False)
        for prop in schema.get("properties", {}).values():
            _enforce_no_additional_props(prop)
    if "items" in schema:
        _enforce_no_additional_props(schema["items"])
    return schema