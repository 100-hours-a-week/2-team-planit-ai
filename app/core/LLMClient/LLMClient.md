# LLMClient

## 📁 개요

LLM(대규모 언어 모델) 서버와의 통신을 담당하는 **클라이언트 모듈**입니다. 추상 기본 클래스를 통해 공통 인터페이스를 정의하고, vLLM 서버 및 OpenAI API를 지원하는 두 가지 구현체를 제공합니다. 모든 클라이언트는 `httpx` 기반 비동기 통신을 사용합니다.

---

## 📄 파일

### `BaseLlmClient.py`

LLM 클라이언트의 **추상 기본 클래스**를 정의합니다.

#### 🏗️ 클래스: `BaseLLMClient(ABC)`

**설명**: 모든 LLM 클라이언트가 구현해야 하는 공통 인터페이스와 유틸리티 메서드를 제공하는 추상 클래스입니다.

##### 📌 필드 (Attributes)

| 필드명 | 타입 | 기본값 | 설명 |
|--------|------|--------|------|
| `base_url` | `str` | - | LLM 서버 기본 URL |
| `timeout` | `int` | `settings.llm_client_timeout` | 요청 타임아웃 (초) |
| `max_retries` | `int` | `settings.llm_client_max_retries` | 최대 재시도 횟수 |
| `max_tokens` | `int` | `settings.llm_client_max_tokens` | 최대 토큰 수 |
| `temperature` | `float` | `settings.llm_client_temperature` | 생성 온도 |
| `top_p` | `float` | `settings.llm_client_top_p` | Top-p 샘플링 값 |

##### 🔧 메서드 (Methods)

**`call_llm(prompt: ChatMessage) -> str`** *(추상, 비동기)*

- **설명**: 비스트리밍 LLM 호출. 전체 응답을 문자열로 반환합니다.

---

**`call_llm_stream(prompt: ChatMessage) -> AsyncIterator[str]`** *(추상, 비동기)*

- **설명**: 스트리밍 LLM 호출. SSE 방식으로 응답을 청크 단위로 yield합니다.

---

**`call_llm_structured(prompt: ChatMessage, model: Type[T]) -> T`** *(추상, 비동기)*

- **설명**: 구조화된 출력 LLM 호출. Pydantic 모델 타입을 받아 JSON Schema 기반으로 파싱된 객체를 반환합니다.

---

**`messageDataToDict(messageData: MessageData) -> Dict[str, str]`**

- **설명**: `MessageData` 객체를 딕셔너리로 변환합니다.

---

**`dictToMessageData(dict: Dict[str, str]) -> MessageData`**

- **설명**: 딕셔너리를 `MessageData` 객체로 변환합니다.

---

**`chatMessageToDictList(chatMessage: ChatMessage) -> List[Dict[str, str]]`**

- **설명**: `ChatMessage`의 메시지 목록을 딕셔너리 리스트로 변환합니다. API 요청 시 사용됩니다.

---

**`dictListToChatMessage(messages: List[Dict[str, str]]) -> ChatMessage`**

- **설명**: 딕셔너리 리스트를 `ChatMessage` 객체로 변환합니다.

---

**`stripJsonCodeFence(content: str) -> str`**

- **설명**: LLM 응답에서 JSON 코드 블록 (```` ```json ... ``` ````)을 제거하여 순수 JSON 문자열을 반환합니다.

---

### `OpenAiApiClient.py`

OpenAI API 호환 서버를 위한 **구현 클라이언트**입니다.

#### 🏗️ 클래스: `OpenAiApiClient(BaseLLMClient)`

**설명**: OpenAI API를 `httpx` 기반 비동기 HTTP로 호출하는 클라이언트입니다. Bearer 토큰 인증을 사용합니다.

##### 📌 필드 (Attributes)

| 필드명 | 타입 | 기본값 | 설명 |
|--------|------|--------|------|
| `api_key` | `Optional[str]` | `settings.openai_api_key` | OpenAI API 키 |
| `model` | `Optional[str]` | `settings.openai_model` | 사용할 모델명 |

*(상속 필드: `base_url`, `timeout`, `max_retries`, `max_tokens`, `temperature`, `top_p`)*

##### 🔧 메서드 (Methods)

**`call_llm_stream(prompt: ChatMessage) -> AsyncIterator[str]`** *(비동기)*

- **설명**: OpenAI SSE 스트리밍 API 호출. `data: {json}` 형식의 라인을 읽어 content를 yield합니다.
- **엔드포인트**: `{base_url}/chat/completions`
- **재시도**: 지수 백오프 (`2^attempt`초)

---

**`call_llm(prompt: ChatMessage) -> str`** *(비동기)*

- **설명**: OpenAI 비스트리밍 API 호출. 전체 응답을 문자열로 반환합니다.
- **재시도**: 지수 백오프

---

**`call_llm_structured(prompt: ChatMessage, model: Type[T]) -> T`** *(비동기)*

- **설명**: JSON Schema 기반 구조화된 출력 호출. `response_format`에 `json_schema`를 설정하여 Pydantic 모델로 파싱합니다.
- **특이사항**: `_enforce_no_additional_props()`로 스키마에 `additionalProperties: false`를 강제합니다.

---

#### 🔧 모듈 레벨 함수

**`_enforce_no_additional_props(schema: dict) -> dict`**

- **설명**: JSON Schema의 모든 object 타입에 `additionalProperties: false`를 재귀적으로 적용합니다. OpenAI Strict Mode 호환을 위해 사용됩니다.

---

### `VllmClient.py`

vLLM 서버를 위한 **구현 클라이언트**입니다.

#### 🏗️ 클래스: `VllmClient(BaseLLMClient)`

**설명**: vLLM 서버를 `httpx` 기반 비동기 HTTP로 호출하는 클라이언트입니다. 인증 없이 직접 서버에 연결합니다.

##### 📌 필드 (Attributes)

| 필드명 | 타입 | 기본값 | 설명 |
|--------|------|--------|------|
| `base_url` | `str` | `settings.vllm_base_url` | vLLM 서버 URL (trailing slash 제거) |

*(상속 필드: `timeout`, `max_retries`, `max_tokens`, `temperature`, `top_p`)*

##### 🔧 메서드 (Methods)

**`call_llm_stream(prompt: ChatMessage) -> AsyncIterator[str]`** *(비동기)*

- **설명**: vLLM SSE 스트리밍 API 호출. 델타 방식으로 content를 yield합니다.
- **엔드포인트**: `{base_url}/v1/chat/completions`
- **재시도**: 지수 백오프, HTTP 503 시 자동 재시도
- **특이사항**: vLLM의 누적 문자열 반환 방식을 처리하기 위해 `content_len` 슬라이싱 사용

---

**`call_llm(prompt: ChatMessage) -> str`** *(비동기)*

- **설명**: vLLM 비스트리밍 API 호출. 전체 응답을 문자열로 반환합니다.
- **재시도**: 지수 백오프, HTTP 503 시 자동 재시도

---

**`call_llm_structured(prompt: ChatMessage, model: Type[T]) -> T`** *(비동기)*

- **설명**: vLLM Guided Decoding을 사용한 구조화된 출력 호출. `response_format`에 `json_schema`를 설정하여 Pydantic 모델로 파싱합니다.
- **재시도**: 지수 백오프, HTTP 503 시 자동 재시도

---

### `LangchainClient.py`

LangChain `ChatOpenAI` 기반 **구조화 출력 전용 클라이언트**입니다. `BaseLLMClient` 계층과 독립적으로 동작합니다.

#### 🏗️ 클래스: `LangchainClient`

**설명**: LangChain의 `with_structured_output`을 사용하여 Pydantic 모델로 직접 파싱하는 클라이언트입니다. vLLM OpenAI 호환 API를 백엔드로 사용합니다.

##### 📌 필드 (Attributes)

| 필드명 | 타입 | 기본값 | 설명 |
|--------|------|--------|------|
| `base_url` | `str` | `settings.vllm_base_url` | vLLM OpenAI 호환 API 베이스 URL |
| `model` | `str` | `settings.vllm_model` | vLLM 모델 이름 |
| `api_key` | `str` | `"EMPTY"` | API 키 (vLLM은 "EMPTY" 사용) |
| `temperature` | `float \| None` | `settings.llm_client_temperature` | 생성 온도 |
| `max_tokens` | `int` | `settings.llm_client_max_tokens` | 최대 토큰 수 |

##### 🔧 메서드 (Methods)

**`call_structured(prompt: ChatMessage, model: Type[T]) -> T`** *(비동기)*

- **설명**: LangChain의 `with_structured_output`을 사용하여 구조화된 출력을 Pydantic 모델로 파싱합니다.
- **특이사항**: `BaseLLMClient`를 상속하지 않고 독립적으로 동작. LangChain의 structured output 기능에 의존합니다.

---

**`_convert_messages(prompt: ChatMessage) -> list`** *(정적 메서드)*

- **설명**: `ChatMessage`를 LangChain 메시지 리스트(`SystemMessage`, `HumanMessage`)로 변환합니다.

---

## 🔗 의존성

- `app.core.config`: `settings` 객체 (환경 변수 기반 설정)
- `app.core.models.LlmClientDataclass.ChatMessageDataclass`: `ChatMessage`, `MessageData` 데이터 모델
- `httpx`: 비동기 HTTP 클라이언트
- `langchain_openai`: `ChatOpenAI` (LangchainClient)
- `langchain_core`: `SystemMessage`, `HumanMessage` (LangchainClient)
- `abc`: 추상 클래스 정의

## 🔗 파일 간 관계

```
BaseLLMClient (추상 기본 클래스)
├── OpenAiApiClient  - OpenAI API 호환 서버용
└── VllmClient       - vLLM 서버용

LangchainClient (독립 클래스, vLLM 백엔드)
└── LangChain ChatOpenAI 기반 구조화 출력 전용
```

- `BaseLlmClient.py`는 추상 인터페이스와 유틸리티 메서드를 정의합니다.
- `OpenAiApiClient.py`와 `VllmClient.py`는 각각 `BaseLLMClient`를 상속하여 구현합니다.
- 두 구현체 모두 동일한 3개의 추상 메서드(`call_llm`, `call_llm_stream`, `call_llm_structured`)를 구현하며, 공통 유틸리티 메서드를 상속받습니다.
- `OpenAiApiClient`는 Bearer 토큰 인증을 사용하고, `VllmClient`는 인증 없이 직접 연결합니다.
- `LangchainClient`는 `BaseLLMClient` 계층과 독립적으로 동작하며, vLLM 서버를 LangChain `ChatOpenAI`를 통해 사용합니다. 구조화 출력(`with_structured_output`)이 필요한 경우에 사용합니다.
