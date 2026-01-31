# LlmClientDataclass

## 📁 개요

이 폴더는 **LLM 클라이언트에서 사용하는 데이터 모델**을 정의합니다. 채팅 메시지 형식을 표준화하여 다양한 LLM 클라이언트에서 일관된 인터페이스로 사용할 수 있도록 합니다.

---

## 📄 파일 목록

### `ChatMessageDataclass.py`

#### 📝 파일 설명

LLM API 호출에 사용되는 **채팅 메시지 데이터 구조**를 정의합니다. Pydantic BaseModel을 상속받아 타입 검증과 직렬화를 지원합니다.

---

#### 🏗️ 클래스: `MessageData`

**설명**: 단일 채팅 메시지를 나타내는 데이터 모델입니다.

##### 📌 필드 (Attributes)

| 필드명 | 타입 | 필수 | 설명 |
|--------|------|------|------|
| `role` | `str` | ✅ | 메시지 발신자 역할 (예: `"user"`, `"assistant"`, `"system"`) |
| `content` | `str` | ✅ | 메시지 내용 |

##### 💡 사용 예시

```python
message = MessageData(role="user", content="서울 맛집 추천해주세요")
```

---

#### 🏗️ 클래스: `ChatMessage`

**설명**: 여러 메시지로 구성된 채팅 대화를 나타내는 데이터 모델입니다.

##### 📌 필드 (Attributes)

| 필드명 | 타입 | 필수 | 설명 |
|--------|------|------|------|
| `content` | `List[MessageData]` | ✅ | 메시지 리스트 (대화 기록) |

##### 💡 사용 예시

```python
chat = ChatMessage(content=[
    MessageData(role="system", content="당신은 여행 도우미입니다."),
    MessageData(role="user", content="제주도 여행 일정 추천해주세요")
])
```

---

## 🔗 의존성

- `pydantic.BaseModel`: 데이터 검증 및 직렬화
- `typing.List`: 타입 힌트
