import asyncio
import json
from typing import AsyncIterator, Type, TypeVar
import httpx
from pydantic import BaseModel
from app.core.LLMClient.BaseLlmClient import BaseLLMClient, T
from app.core.config import settings


class VllmClient(BaseLLMClient):
    """
    LLM API 클라이언트 (httpx 기반 async 스트리밍 지원)
    LLM서버에서 비동기로 응답을 받아오는 함수

    Args:
        BaseLLMClient (_type_): _description_
    """
    def __init__(
        self,
        base_url: str = settings.vllm_base_url,
        timeout: int = settings.llm_client_timeout,
        max_retries: int = settings.llm_client_max_retries,
        max_tokens: int = settings.llm_client_max_tokens,
        temperature: float = settings.llm_client_temperature,
        top_p: float = settings.llm_client_top_p,

    ) -> None:
        super().__init__(
            base_url=base_url,
            timeout=timeout,
            max_retries=max_retries,
            max_tokens=max_tokens,
            temperature=temperature,
            top_p=top_p,
        )
        self.base_url = base_url.rstrip("/")

    async def call_llm_stream(self, prompt: str) -> AsyncIterator[str]:
        """
        스트리밍 LLM API 호출 (async)

        - /v1/chat/completions 엔드포인트로 SSE 스타일 스트림 요청
        - 'data: {json}\n\n' 형식의 라인을 읽어서 content만 yield
        - '[DONE]' 이 오면 종료
        """
        request_data = {
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": self.max_tokens,
            "top_p": self.top_p,
            "temperature": self.temperature,
            "stream": True,
        }

        # 지수 백오프를 포함한 재시도 루프
        for attempt in range(self.max_retries):
            try:
                async with httpx.AsyncClient(
                    timeout=self.timeout,
                    headers={
                        "Content-Type": "application/json",
                        "Accept": "text/event-stream, application/json",
                    },
                ) as client:
                    # 스트리밍 모드로 POST
                    async with client.stream(
                        "POST",
                        f"{self.base_url}/v1/chat/completions",
                        json=request_data,
                    ) as response:

                        # 200 OK가 아니라면 재시도 / 에러 처리
                        if response.status_code == 503:
                            # 서버 busy → 백오프 후 재시도
                            await asyncio.sleep(2 ** attempt)
                            continue

                        if response.status_code != 200:
                            # 즉시 에러 메시지 방출 후 종료
                            yield f"LLM 서버 오류 (HTTP {response.status_code})"
                            return

                        # 200 OK → 스트림 처리
                        content_len = 0  # 원래 코드와 동일한 방식 유지
                        async for line in response.aiter_lines():
                            # 없거나 SSE 형식: "data: {...}"
                            if not line or not line.startswith("data: "):
                                continue

                            data_str = line[6:]  # 'data: ' 제거

                            # 스트리밍 종료 신호
                            if data_str.strip() == "[DONE]":
                                return

                            # JSON 파싱
                            try:
                                data = json.loads(data_str)
                            except json.JSONDecodeError:
                                # 이상한 데이터가 오면 그냥 무시 (원한다면 로그 추가)
                                continue

                            # OpenAI 스타일: choices[0].delta.content
                            if "choices" in data and data["choices"]:
                                choice = data["choices"][0]
                                if "delta" in choice and "content" in choice["delta"]:
                                    # TODO: vLLM은 원래 "현재까지 생성된 전체 문자열"을 매번 반환하는 구조
                                    raw_content = choice["delta"]["content"]

                                    # 기존 코드에서 slice를 사용하던 패턴 유지
                                    content = raw_content[content_len:]
                                    content_len += len(content)

                                    if content:
                                        # 여기서 한 청크씩 밖으로 내보냄
                                        yield content

                        # 여기까지 오면 스트림이 자연스럽게 끝난 것
                        return

            except (httpx.RequestError, httpx.TimeoutException) as e:
                # 네트워크/타임아웃 에러 → 재시도 또는 마지막에는 에러 방출
                if attempt == self.max_retries - 1:
                    yield f"LLM 서버 요청 실패: {str(e)}"
                    return

                await asyncio.sleep(2 ** attempt)
                continue

    def call_llm(self, prompt: str) -> str:
        """
        비스트리밍 LLM API 호출 (sync)
        """
        import time
        request_data = {
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": self.max_tokens,
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
                        "Content-Type": "application/json",
                    },
                ) as client:
                    response = client.post(
                        f"{self.base_url}/v1/chat/completions",
                        json=request_data,
                    )

                    if response.status_code == 503:
                        time.sleep(2 ** attempt)
                        continue

                    if response.status_code != 200:
                        return f"LLM 서버 오류 (HTTP {response.status_code})"

                    data = response.json()
                    if "choices" in data and data["choices"]:
                        return data["choices"][0]["message"]["content"]
                    return ""

            except (httpx.RequestError, httpx.TimeoutException) as e:
                if attempt == self.max_retries - 1:
                    return f"LLM 서버 요청 실패: {str(e)}"
                time.sleep(2 ** attempt)
                continue
