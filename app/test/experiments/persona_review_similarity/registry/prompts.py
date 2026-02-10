"""
Prompt Registry for Persona Generation Strategies.

Updated to match TravelPersonaAgent structure:
- ItineraryRequest: tripId, travelCity, totalBudget, travelTheme, wantedPlace, etc.
- QAItem: id, question, answer
"""

from dataclasses import dataclass
from typing import Callable, Dict, List, Optional, Any

from app.core.models.PersonaAgentDataclass.persona import QAItem
from app.schemas.persona import ItineraryRequest


@dataclass
class PromptConfig:
    """Configuration for a persona generation prompt."""

    name: str
    description: str
    generator: Callable[..., str]


PROMPT_REGISTRY: Dict[str, PromptConfig] = {}


def register_prompt(name: str, description: str = ""):
    """Decorator to register a new persona generation prompt."""

    def decorator(func: Callable[..., str]):
        PROMPT_REGISTRY[name] = PromptConfig(
            name=name, description=description, generator=func
        )
        return func

    return decorator


def _format_itinerary_request(itinerary_request: Any) -> str:
    """Format ItineraryRequest to XML string (matching TravelPersonaAgent)."""
    if itinerary_request is None:
        return ""

    lines = []
    if hasattr(itinerary_request, 'travelCity'):
        lines.append(f"    <travelCity>{itinerary_request.travelCity}</travelCity>")
    if hasattr(itinerary_request, 'totalBudget'):
        lines.append(f"    <totalBudget>{itinerary_request.totalBudget}</totalBudget>")
    if hasattr(itinerary_request, 'travelTheme'):
        themes = ", ".join(itinerary_request.travelTheme) if itinerary_request.travelTheme else ""
        lines.append(f"    <travelTheme>{themes}</travelTheme>")
    if hasattr(itinerary_request, 'wantedPlace'):
        places = ", ".join(itinerary_request.wantedPlace) if itinerary_request.wantedPlace else ""
        lines.append(f"    <wantedPlace>{places}</wantedPlace>")
    if hasattr(itinerary_request, 'arrivalDate'):
        lines.append(f"    <arrivalDate>{itinerary_request.arrivalDate}</arrivalDate>")
    if hasattr(itinerary_request, 'departureDate'):
        lines.append(f"    <departureDate>{itinerary_request.departureDate}</departureDate>")

    return "\n".join(lines)


def _format_qa_items(qa_items: List[QAItem]) -> str:
    """Format QA items to XML string (matching TravelPersonaAgent)."""
    lines = []
    for item in qa_items:
        if item.answer:
            lines.append("    <qa>")
            lines.append(f"        <question>{item.question}</question>")
            lines.append(f"        <answer>{item.answer}</answer>")
            lines.append("    </qa>")
    return "\n".join(lines)


# ============================================================
# P1: 현재 방식 (Current Style) - TravelPersonaAgent와 동일한 프롬프트
# ============================================================
@register_prompt(
    "P1_현재방식", description="TravelPersonaAgent 스타일 1문장 요약"
)
def current_style_prompt(
    itinerary_request: ItineraryRequest,
    qa_items: List[QAItem] = [],
) -> str:
    """
    Current production prompt style matching TravelPersonaAgent.
    Output: "편안한 힐링을 최우선으로 하는 단기 여행자..."
    """
    pre_survey = _format_itinerary_request(itinerary_request)
    qa_answers = _format_qa_items(qa_items)

    return f"""<role>
여행 일정 관련 질문에서 사용자의 페르소나(성향과 우선순위)를 예측하는 전문가 어시스턴트 역할을 맡습니다. 당신은 사용자 입력에 담긴 감정, 여행의 의미, 제약 조건, 성공 기준, 관심사 키워드를 빠르게 해석하여, 기획자나 일정 생성기에 바로 활용 가능한 한 문장짜리 페르소나 요약을 한국어로 제공합니다.
</role>

<input>
    <ItineraryRequest>
{pre_survey}
    </ItineraryRequest>

    <Answers>
{qa_answers}
    </Answers>
</input>

<instructions>
다음 절차와 규칙을 반드시 따르세요:
1. 각 변수에서 추출할 신호:
   - 감정: 감정의 방향(긍정/부정)과 강도 — 페르소나의 톤(예: '활동적/차분/조심스러운').
   - 여행의 의미: 주된 목적(예: 힐링/모험/가족중심 등).
   - 제약: 절대적 제약(예산, 기간, 건강, 동행자 등)을 우선순위에 반영하여 현실적 페르소나로 조정.
   - 성공 기준: 사용자가 무엇을 성공으로 보는지(휴식, 체험, 사진 등)를 페르소나의 핵심 목표로 반영.
   - 관심 키워드: 구체적 선호를 보여주는 증거로, 핵심 2~3개만 요약해 문장에 포함.

2. 종합 방법:
   - 감정 + 여행의 의미를 결합해 페르소나의 전반적 성향(예: '휴식 지향의 차분한 여행자', '모험과 사진을 즐기는 활동가')을 만듭니다.
   - 제약은 반드시 반영하여 현실적인 우선순위를 명시하세요(예: '예산 제한으로 소도시 숙박 선호'와 같이).
   - 성공 기준은 문장에서 목적어로 명확히 표현하세요.
   - 관심 키워드는 괄호나 짧은 쉼표 구분으로 2~3개만 포함해 구체성을 줍니다.
   - 우선순위 표기: 가장 중요한 항목을 문장 앞쪽에 배치합니다(예: 목적/제약/성공기준/관심키워드 순 등).

3. 출력 규칙(엄격):
   - 항상 출력은 <final_response> (최종 페르소나, 정확히 한 문장).
   - <final_response> 내부의 문장은 한국어로 자연스럽고, 단 한 문장으로 끝나야 합니다. 추가 XML 태그나 다른 형식의 출력은 넣지 마세요.
   - 문장이 너무 길어질 경우 쉼표로 구분하되, 문장 개수는 하나로 유지합니다.
   - 사용자가 명시적으로 JSON 출력을 요청한 경우에만 JSON 형식({{ "final_response": "..." }})로 출력하세요. 그 요청이 없으면 반드시 XML(<final_response>)로 출력합니다.

4. 모호성/상충 처리:
   - 입력들 사이에 모순이 있으면(예: '모험'을 원하지만 '심한 활동 금지' 제약이 있음) 그 모순을 반영해 우선순위를 정하고, 문장 안에 간단히 표시합니다(예: "모험 성향이나 건강 제약으로 활동은 제한적...").
   - 관심 키워드가 과다하면 핵심 2~3개만 선택해 포함하세요.

5. 스타일 가이드:
   - 어투: 간결하고 전문적이며 공손한 한국어.
   - 표현: 페르소나 유형(예: '힐링 지향의 가족 단위 여행자') + 우선순위(제약과 성공 기준) + 핵심 관심키워드(2~3개)를 한 문장에 담습니다.
   - 예시적 표현: "편안한 힐링을 최우선으로 하는 부부 여행자, 예산과 시간 제약이 있어 근교 숙박 위주를 선호하며 성공 기준은 충분한 휴식(온천, 조용한 카페)입니다." — 위 문장은 예시일 뿐, 실제 응답은 입력에 맞춰 축약하고 하나의 문장으로 만드세요.

6. 검증:
   - 최종 문장이 입력 요소를 반영하는지 스스로 점검하세요

Remember to follow these instructions precisely. Do not add extra steps or information beyond what has been requested.
</instructions>
<response_style>
간결하고 실용적인 한국어 문장. 분석적이되 사용자에게 바로 유용한 페르소나 형태로 표현하세요. 톤은 중립적이며 이해하기 쉬워야 합니다.
</response_style>
<examples>
Example 1 — 명확한 입력
(final_response must use the required XML tags when the agent runs; here we show content only.)
<final_response>
편안한 힐링을 최우선으로 하는 단기 여행자(예산 제한 있음), 충분한 휴식이 성공 기준이며 온천과 조용한 카페 체험을 선호합니다.
</final_response>

Example 2 — 제약과 욕구가 충돌하는 입력
<final_response>
모험과 사진 촬영을 중시하는 성향이지만 무릎 건강 제약으로 활동은 낮은 난이도로 제한되며, 경치 좋은 가벼운 트레킹과 포인트별 사진 촬영을 성공 기준으로 삼습니다.
</final_response>

</examples>
<reminder>
- 반드시 입력의 다섯 요소를 먼저 파악하고 그 순서대로 반영할 것.
- 최종 응답은 정확히 한 문장(한국어)으로 구성할 것.
- 예시와 실제 응답에서 변수 이름 사용해 입력을 참조하되, 예시에서는 실제 값으로 대체하여 보여줄 것.
</reminder>
<output_format>
출력은 반드시 다음 형식으로만 제공합니다(다른 XML/JSON 태그를 추가하지 마세요):

<final_response>
[최종 페르소나 한 문장 — 한국어로 자연스럽게 작성]
</final_response>

</output_format>"""


# ============================================================
# P2: 키워드 중심 (Keyword-Centric)
# ============================================================
@register_prompt("P2_키워드중심", description="구조화된 키워드 리스트 형태")
def keyword_style_prompt(
    itinerary_request: ItineraryRequest,
    qa_items: List[QAItem] = [],
) -> str:
    """
    Keyword-focused prompt for structured output.
    Output: "선호: 온천, 카페 / 제약: 예산 50만원 / 테마: 힐링, 휴식"
    """
    pre_survey = _format_itinerary_request(itinerary_request)
    qa_answers = _format_qa_items(qa_items)

    return f"""다음 사전 설문과 Q&A에서 여행자의 핵심 정보를 **키워드와 리스트** 형태로 추출하세요.

## 사전 설문
<pre_survey>
{pre_survey}
</pre_survey>

## Q&A 답변
<qa_answers>
{qa_answers}
</qa_answers>

## 출력 형식 (정확히 이 형식으로)
도시: [여행 도시]
테마: [쉼표로 구분된 여행 테마]
선호: [쉼표로 구분된 선호 장소/활동]
제약: [예산, 일정 등 제약 조건]
우선순위: [가장 중요한 여행 목적]"""


# ============================================================
# P3: 리뷰 스타일 (Review Style)
# ============================================================
@register_prompt("P3_리뷰스타일", description="가상의 리뷰 작성 스타일로 페르소나 표현")
def review_style_prompt(
    itinerary_request: ItineraryRequest,
    qa_items: List[QAItem] = [],
) -> str:
    """
    Prompt that generates persona in review-like language.
    Output: "조용하고 힐링되는 곳을 찾았어요. 가격도 적당하고..."
    """
    pre_survey = _format_itinerary_request(itinerary_request)
    qa_answers = _format_qa_items(qa_items)

    return f"""다음 사전 설문과 Q&A를 바탕으로, 이 여행자가 **이상적인 장소를 찾았을 때 작성할 것 같은 가상의 리뷰**를 작성하세요.

## 사전 설문
<pre_survey>
{pre_survey}
</pre_survey>

## Q&A 답변
<qa_answers>
{qa_answers}
</qa_answers>

## 지침
- 실제 구글 리뷰처럼 자연스럽게 작성
- 여행자의 선호, 제약, 만족 포인트를 리뷰에 녹여내기
- 2-3문장으로 작성
- 구체적인 장소명 대신 "이 곳", "여기" 등 사용

## 출력 형식
[가상 리뷰 텍스트]"""


# ============================================================
# P4: 임베딩 최적화 (Embedding Optimized)
# ============================================================
@register_prompt("P4_임베딩최적화", description="POI 리뷰와 유사한 문체로 페르소나 표현")
def embedding_optimized_prompt(
    itinerary_request: ItineraryRequest,
    qa_items: List[QAItem] = [],
) -> str:
    """
    Prompt optimized for embedding similarity with POI reviews.
    Uses similar vocabulary and sentence structure as Google reviews.
    """
    pre_survey = _format_itinerary_request(itinerary_request)
    qa_answers = _format_qa_items(qa_items)

    return f"""다음 여행자 정보를 바탕으로, 이 여행자가 **좋아할 장소의 특징**을 구글 리뷰 스타일로 설명하세요.

## 사전 설문
<pre_survey>
{pre_survey}
</pre_survey>

## 지침
- "~한 곳이 좋아요", "~하면 좋겠어요" 같은 리뷰 문체 사용
- 분위기, 가격, 서비스 등 리뷰에서 자주 언급되는 요소 포함
- 구체적인 선호 사항을 자연스럽게 표현
- 3-4문장으로 작성

## 출력 형식
[리뷰 스타일 선호도 설명]"""


def get_prompt(name: str) -> Optional[PromptConfig]:
    """Get a registered prompt by name."""
    return PROMPT_REGISTRY.get(name)


def list_prompts() -> List[str]:
    """List all registered prompt names."""
    return list(PROMPT_REGISTRY.keys())


# ============================================================
# P5: XML로 구조화된 형태로 페르소나 표현
# ============================================================
@register_prompt("P5_XML로구조화된형태", description="XML로 구조화된 형태로 페르소나 표현")
def xml_structured_persona_prompt(
    itinerary_request: ItineraryRequest,
    qa_items: List[QAItem] = [],
) -> str:
    """
    Prompt optimized for embedding similarity with POI reviews.
    Uses similar vocabulary and sentence structure as Google reviews.
    """
    pre_survey = _format_itinerary_request(itinerary_request)
    qa_answers = _format_qa_items(qa_items)

    return f"""당신은 “사용자 여행 취향 프로필 XML 생성기”입니다.
입력으로는 오직 아래 3가지 정보만 주어집니다:
1) 여행지
2) 여행 테마
3) 비행기 일정(가는편/오는편)

목표:
- POI 임베딩(XML: name, primary_type, type, address, google_rating, user_rating_count, price_level, editorial_summary, generative_summary, review_summary)과 의미적으로 잘 맞도록,
- 사용자 취향을 “POI 필드들과 유사한 정보 밀도/키워드 스타일”로 XML로 출력하세요.
- 추가 정보를 입력으로 요구하지 마세요.

핵심 규칙:
- 출력은 반드시 XML 단일 문서만. 다른 텍스트/설명/마크다운 금지.
- 여행 테마 중심으로 취향을 키워드 풍부하게 확장(장소 카테고리/분위기/활동/가격대/혼잡도/실내·야외/사진·미식·문화 등).
- 비행 일정의 날짜로 “계절”을 추정하고, 계절에 따라 선호 장소(primary_type/type) 및 활동 성향을 반영.
- 값이 확실하지 않으면 unknown을 사용.
- 임베딩 매칭을 위해, 아래 필드들에는 “쉼표로 구체 키워드 나열”을 적극 사용.

[INPUT]
<trip_input>
  <destination>{itinerary_request.travelCity}</destination>
  <theme>{itinerary_request.travelTheme}</theme>
  <flight>
    <outbound>{itinerary_request.departureDate}</outbound>
    <inbound>{itinerary_request.arrivalDate}</inbound>
  </flight>
</trip_input>

[OUTPUT SCHEMA]
<final_response>
  <!-- POI의 primary_type/type과 가까운 “선호 카테고리/장소 유형”을 만들어낸다 -->
  <primary_type>...</primary_type>
  <type>...</type>

  <!-- POI의 price_level에 대응: 사용자의 가격 민감도/선호 가격대 -->
  <price_level>...</price_level>

  <!-- POI의 editorial_summary처럼: 한두 문장 요약(테마 중심) -->
  <editorial_summary>...</editorial_summary>

  <!-- POI의 generative_summary처럼: 키워드가 풍부한 상세 요약 -->
  <generative_summary>...</generative_summary>

  <!-- POI의 review_summary처럼: “리뷰에서 자주 나올 법한 선호 표현/키워드” -->
  <review_summary>...</review_summary>

  <!-- 비행 일정 기반 계절/날씨 맥락 -->
  <seasonal_context>
    <season>...</season>
    <weather_activity_bias>...</weather_activity_bias>
    <indoor_outdoor_balance>indoor|outdoor|mixed|unknown</indoor_outdoor_balance>
  </seasonal_context>

  <!-- POI 매칭에 직접 도움이 되는 사용자 의사결정 키워드 -->
  <decision_keywords>
    <must_have>...</must_have>
    <nice_to_have>...</nice_to_have>
    <avoid>...</avoid>
    <crowd_tolerance>low|medium|high|unknown</crowd_tolerance>
    <pace>slow|balanced|fast|unknown</pace>
  </decision_keywords>
</final_response>

[FIELD CONTENT GUIDELINES]
- <primary_type>: 예) cafe, restaurant, museum, park, viewpoint, shopping_mall, market, temple, hot_spring, hiking_area 처럼 “장소 1차 카테고리”를 5~12개 쉼표로 나열.
- <type>: 예) specialty_coffee, local_street_food, modern_art, history_museum, night_view, quiet_alley, nature_trail, rooftop_bar 등 “세부 유형” 8~20개 나열.
- <price_level>: cheap/mid/premium/mixed/unknown + 이유 키워드(가성비, 미슐랭, 로컬, 코스요리 등)를 함께 포함.
- <editorial_summary>: 테마 중심 1~2문장.
- <generative_summary>: 3~5문장. ‘무엇을 좋아하고/피하고/어떤 분위기/어떤 경험/어떤 소비/어떤 일정 템포’를 구체 키워드로 반복.
- <review_summary>: “분위기 좋은, 친절한, 웨이팅, 조용한, 뷰맛집, 로컬, 가성비, 인스타, 숨은맛집, 예약필수, 동선편함…” 같은 리뷰 언어 키워드 중심.
- <seasonal_context>: outbound/inbound 날짜로 계절 추정(봄/여름/가을/겨울). 계절에 맞춰 실내·야외 선호 및 활동을 조정.

이제 위 규칙대로, 반드시 XML만 출력하라."""

# ============================================================
# P6: 키워드 기반으로 페르소나 표현
# ============================================================
@register_prompt("P6_키워드기반", description="키워드 기반으로 페르소나 표현")
def xml_structured_persona_prompt(
    itinerary_request: ItineraryRequest,
    qa_items: List[QAItem] = [],
) -> str:
    """
    Prompt optimized for embedding similarity with POI reviews.
    Uses similar vocabulary and sentence structure as Google reviews.
    """
    pre_survey = _format_itinerary_request(itinerary_request)
    qa_answers = _format_qa_items(qa_items)

    return f"""당신은 여행 키워드 추출 전문가입니다.

여행자가 "{itinerary_request.travelCity}"(으)로 여행을 계획하고 있습니다.
다음 여행자 페르소나와 여행 기간을 분석하여, 해당 여행지에서 이 여행자가 좋아할 만한 POI 검색 키워드를 추출해주세요.

<destination>
{itinerary_request.travelCity}
</destination>

<travel_period>
시작일: {itinerary_request.departureDate}
종료일: {itinerary_request.arrivalDate}
</travel_period>

<travel_theme>
{itinerary_request.travelTheme}
</travel_theme>

지침:
- 반드시 "{itinerary_request.travelCity}" 여행지에 특화된 키워드를 생성할 것
- 페르소나의 여행 스타일, 취향, 예산, 동행인 등을 고려
- "{itinerary_request.travelCity}"의 유명 관광지, 로컬 맛집, 숨은 명소 등을 반영
- 여행 기간의 계절과 시기를 반드시 고려하여 키워드 생성:
  - 해당 시기에 가능한 계절 활동 (예: 3-4월 벚꽃, 10-11월 단풍, 7-8월 해수욕/물놀이, 12-2월 스키/온천)
  - 해당 기간에 열리는 축제나 이벤트
  - 해당 계절에 먹을 수 있는 제철 음식
  - 비수기/성수기 특성 고려
  - 해당 시기에 불가능한 활동은 제외 (예: 겨울에 해수욕, 여름에 스키)
- 5-10개의 검색 키워드 생성
- 맛집, 카페, 관광지, 쇼핑, 액티비티 등 다양한 카테고리 포함
- 모든 키워드에 여행지명을 포함할 것

응답 형식:
키워드1, 키워드2, 키워드3, 키워드4, ...."""

