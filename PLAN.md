# 구현 계획 (Implementation Plan)

> 이 문서는 PlanIt_Agent 프로젝트의 구현 순서를 정의합니다.

---

## 📋 구현 순서 개요

구현은 **의존성**을 기준으로 아래 순서로 진행합니다:
1. **기반 인프라** → 2. **LLM Client** → 3. **개별 Agent** → 4. **Graph (Agent 통합)** → 5. **API 엔드포인트**

---

## Phase 1: 기반 인프라 (Foundation)

### 1.1 FastAPI 기본 구조 구성
- **파일**: `app/main.py`, `main.py`, `app/core/config.py`
- **설명**: FastAPI 앱 인스턴스 생성 및 설정
- **산출물**: 
  - FastAPI 앱 초기화
  - CORS 설정
  - 환경변수 설정 (pydantic-settings)

### 1.2 Health Check API 구현
- **파일**: `app/api/` (새 파일 생성)
- **설명**: 서버 상태 확인용 엔드포인트
- **산출물**: `GET /health` 엔드포인트

---

## Phase 2: LLM Client 구성

> **이유**: 모든 Agent가 LLM Client를 사용하므로, Agent 구현 전에 완료해야 함

### 2.1 Base LLM Client 구현
- **파일**: `app/core/llm/base_client.py`
- **설명**: LLM 클라이언트의 공통 인터페이스 정의
- **산출물**:
  - 추상 클래스 정의
  - `generate()`, `stream()` 등 공통 메서드 시그니처
  - 에러 핸들링 기본 구조

### 2.2 VLLM Client 구현
- **파일**: `app/core/llm/vllm_client.py`
- **설명**: VLLM 서버와 통신하는 구체적 클라이언트
- **산출물**:
  - BaseLlmClient 상속 구현
  - VLLM API 호출 로직
  - 응답 파싱 및 에러 처리

---

## Phase 3: 개별 Agent 구현

> **구현 순서 원칙**: 
> - 다른 Agent에 의존하지 않는 Agent 먼저 구현
> - 같은 Graph에 속하는 Agent는 묶어서 구현

### 3.1 Travel Persona Agent
- **파일**: `app/core/agents/persona/travel_persona_agent.py`
- **Schema**: `app/schemas/persona.py`
- **설명**: 사용자의 여행 성향/페르소나를 분석하는 Agent
- **의존성**: LLM Client만 필요
- **우선순위**: ⭐ 높음 (독립적, 다른 Flow의 입력이 됨)

### 3.2 POI 관련 Agent (POI Graph용)
구현 순서: `WebSearch` → `InfoSummarize` → `PoiGraph`

#### 3.2.1 Poi Web Search Agent
- **파일**: `app/core/agents/poi/web_search_agent.py`
- **설명**: POI 정보를 웹에서 검색하는 Agent
- **의존성**: LLM Client

#### 3.2.2 Info Summarize Agent
- **파일**: `app/core/agents/poi/info_summarize_agent.py`
- **설명**: 검색된 POI 정보를 요약하는 Agent
- **의존성**: LLM Client, (Web Search 결과 활용)

#### 3.2.3 Poi Graph (통합)
- **파일**: `app/core/agents/poi/poi_graph.py`
- **설명**: Web Search Agent + Info Summarize Agent를 조합한 Graph
- **의존성**: Poi Web Search Agent, Info Summarize Agent

### 3.3 Itinerary Plan 관련 Agent (Itinerary Plan Graph용)
구현 순서: `Schedule` → `ConstraintValid` → `DistanceCalculate` → `ItineraryPlanGraph`

#### 3.3.1 Schedule Agent
- **파일**: `app/core/agents/itinerary/schedule_agent.py`
- **설명**: 일정 스케줄링을 담당하는 Agent
- **의존성**: LLM Client

#### 3.3.2 Constraint Valid Agent
- **파일**: `app/core/agents/itinerary/constraint_valid_agent.py`
- **설명**: 일정 제약 조건 검증을 담당하는 Agent
- **의존성**: LLM Client

#### 3.3.3 Distance Calculate Agent
- **파일**: `app/core/agents/itinerary/distance_calculate_agent.py`
- **설명**: POI 간 거리 계산을 담당하는 Agent
- **의존성**: 외부 API (Google Maps 등) 또는 계산 로직

#### 3.3.4 Itinerary Plan Graph (통합)
- **파일**: `app/core/agents/itinerary/itinerary_plan_graph.py`
- **Schema**: `app/schemas/itinerary.py`
- **설명**: Schedule + ConstraintValid + DistanceCalculate Agent를 조합한 Graph
- **의존성**: 위 3개 Agent

---

## Phase 4: API 엔드포인트 연결

> Agent/Graph 구현 완료 후 API 노출

### 4.1 Persona API
- **엔드포인트**: `POST /api/v1/persona`
- **연결**: Travel Persona Agent

### 4.2 POI API
- **엔드포인트**: `POST /api/v1/poi/search`
- **연결**: Poi Graph

### 4.3 Itinerary API
- **엔드포인트**: `POST /api/v1/itinerary`
- **연결**: Itinerary Plan Graph

---

## 📊 의존성 다이어그램

```
Phase 1: Foundation
├── FastAPI 기본 구조
└── Health Check API

Phase 2: LLM Client
├── BaseLlmClient
└── VllmClient (depends: BaseLlmClient)

Phase 3: Agents
├── Travel Persona Agent (depends: VllmClient)
├── POI Group
│   ├── Poi Web Search Agent (depends: VllmClient)
│   ├── Info Summarize Agent (depends: VllmClient)
│   └── Poi Graph (depends: Web Search + Info Summarize)
└── Itinerary Group
    ├── Schedule Agent (depends: VllmClient)
    ├── Constraint Valid Agent (depends: VllmClient)
    ├── Distance Calculate Agent
    └── Itinerary Plan Graph (depends: Schedule + Constraint + Distance)

Phase 4: API Endpoints
├── /health
├── /api/v1/persona (depends: Persona Agent)
├── /api/v1/poi/search (depends: Poi Graph)
└── /api/v1/itinerary (depends: Itinerary Plan Graph)
```

---

## ⏱️ 예상 마일스톤

| Phase | 항목 | 예상 소요 |
|-------|------|----------|
| 1 | 기반 인프라 | 0.5일 |
| 2 | LLM Client | 1일 |
| 3.1 | Travel Persona Agent | 0.5일 |
| 3.2 | POI 관련 Agent + Graph | 2일 |
| 3.3 | Itinerary 관련 Agent + Graph | 2일 |
| 4 | API 엔드포인트 연결 | 0.5일 |
| **Total** | | **~6.5일** |

---

## 📝 참고사항

1. **테스트**: 각 Phase 완료 시 단위 테스트 작성 권장
2. **Schema**: Agent 구현 시 입출력 Schema 먼저 정의
3. **환경 변수**: `.env` 파일에 VLLM 서버 URL, host, port 등 설정 필요
4. **패키지 설치**: `pydantic-settings` 패키지 필요 (`uv add pydantic-settings`)
