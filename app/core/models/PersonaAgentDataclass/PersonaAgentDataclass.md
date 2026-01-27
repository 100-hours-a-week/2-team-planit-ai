# PersonaAgentDataclass

## 📁 개요

이 폴더는 **페르소나 에이전트에서 사용하는 데이터 모델**을 정의합니다. 사용자의 여행 성향 설문 응답과 생성된 페르소나 정보를 구조화합니다.

---

## 📄 파일 목록

### `persona.py`

#### 📝 파일 설명

페르소나 에이전트의 **입출력 데이터 구조**를 정의합니다. 사용자 설문 응답(Q&A)과 생성된 페르소나 요약 정보를 모델링합니다.

---

#### 🏗️ 클래스: `QAItem`

**설명**: 사전 설문의 단일 질문-답변 쌍을 나타내는 데이터 모델입니다.

##### 📌 필드 (Attributes)

| 필드명 | 타입 | 필수 | 기본값 | 설명 |
|--------|------|------|--------|------|
| `id` | `int` | ✅ | - | 질문 ID (고유 식별자) |
| `question` | `str` | ✅ | - | 질문 내용 |
| `answer` | `Optional[Union[str, List[str]]]` | ❌ | `None` | 답변 내용 (단일 텍스트 또는 다중 선택) |

##### 💡 사용 예시

```python
# 단일 답변
qa1 = QAItem(id=1, question="여행 스타일은?", answer="힐링")

# 다중 답변
qa2 = QAItem(id=2, question="선호하는 음식은?", answer=["한식", "일식", "양식"])
```

---

#### 🏗️ 클래스: `Persona`

**설명**: LLM이 생성한 여행 페르소나 정보를 나타내는 데이터 모델입니다.

##### 📌 필드 (Attributes)

| 필드명 | 타입 | 필수 | 설명 |
|--------|------|------|------|
| `summary` | `str` | ✅ | 한 줄로 요약된 여행 페르소나 |

##### 💡 사용 예시

```python
persona = Persona(summary="20대 직장인, 혼자 떠나는 힐링 여행, 맛집 탐방과 카페 투어를 즐기며 예산은 50만원 이내")
```

---

## 🔗 의존성

- `pydantic.BaseModel`, `pydantic.Field`: 데이터 검증 및 메타데이터
- `typing.List`, `typing.Optional`, `typing.Union`: 타입 힌트
- `app.schemas.persona.ItineraryRequest`: 여행 일정 요청 스키마 (현재 미사용)
