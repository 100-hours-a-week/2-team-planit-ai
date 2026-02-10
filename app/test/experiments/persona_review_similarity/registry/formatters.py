"""
Formatter Registry for Review Preprocessing Methods.

Updated to use production PoiData directly:
- Formatters receive PoiData objects instead of (reviews, metadata)
- LLM/rule-based variants split into separate formatters
- 7 total formatters: R1_Raw, R2_키워드추출_LLM, R2_키워드추출_규칙,
  R3_감성속성_LLM, R3_감성속성_규칙, R4_구조화요약, R5_임베딩최적화
"""

from dataclasses import dataclass
from typing import Callable, Dict, List, Optional, Any
import asyncio

from app.core.models.PoiAgentDataclass.poi import PoiData


@dataclass
class FormatterConfig:
    """Configuration for a review formatter."""

    name: str
    description: str
    formatter: Callable[..., str]
    requires_llm: bool = False


FORMATTER_REGISTRY: Dict[str, FormatterConfig] = {}


def register_formatter(name: str, description: str = "", requires_llm: bool = False):
    """Decorator to register a new review formatter."""

    def decorator(func: Callable[..., str]):
        FORMATTER_REGISTRY[name] = FormatterConfig(
            name=name, description=description, formatter=func, requires_llm=requires_llm
        )
        return func

    return decorator


# ============================================================
# R1: Raw - raw_text 또는 review_summary 그대로
# ============================================================
@register_formatter("R1_Raw", description="PoiData.raw_text 또는 review_summary 원문 그대로")
def raw_formatter(poi: PoiData, **kwargs) -> str:
    """
    Use raw_text or review_summary directly from PoiData.
    """
    if not poi.raw_text:
        raise ValueError(f"POI {poi.id} has no raw_text")
    return poi.raw_text


# ============================================================
# R2a: 키워드 추출 - LLM 버전
# ============================================================
@register_formatter(
    "R2_키워드추출_LLM", description="LLM으로 핵심 키워드만 추출", requires_llm=True
)
def keyword_formatter_llm(poi: PoiData, llm_client=None, **kwargs) -> str:
    """
    Extract keywords from POI using LLM.
    Output: "맛있는, 분위기 좋은, 고급"
    """
    review_text = poi.review_summary or poi.raw_text or poi.name
    description = poi.description or "없음"
    editorial_summary = poi.editorial_summary or "없음"
    generated_summary = poi.generative_summary or "없음"

    prompt = f"""다음 장소 정보에서 핵심 키워드만 추출하세요.
긍정적/부정적 형용사와 명사 위주로 쉼표로 구분하여 나열하세요.

장소명: {poi.name}
카테고리: {poi.category.value if poi.category else "unknown"}
리뷰: {review_text}
소개: {description}
설명: {editorial_summary}
요약: {generated_summary}

출력 형식: 키워드1, 키워드2, 키워드3, ...
"""
    from app.core.models.LlmClientDataclass.ChatMessageDataclass import ChatMessage, MessageData

    messages = ChatMessage(content=[MessageData(role="user", content=prompt)])
    response = asyncio.run(llm_client.call_llm(messages))
    return response.strip()

# ============================================================
# R3a: 감성+속성 - LLM 버전
# ============================================================
@register_formatter(
    "R3_감성속성_LLM", description="LLM으로 감성 태그 + 속성 정리", requires_llm=True
)
def sentiment_attribute_formatter_llm(poi: PoiData, llm_client=None, **kwargs) -> str:
    """
    Format POI with sentiment tags and attributes using LLM.
    Output: "[긍정] 맛, 분위기 / [부정] 가격 / [카테고리] restaurant"
    """
    review_text = poi.review_summary or poi.raw_text or poi.name

    prompt = f"""다음 장소 리뷰를 분석하여 감성별로 속성을 정리하세요.

장소명: {poi.name}
리뷰: {review_text}

출력 형식:
[긍정] 속성1, 속성2 / [부정] 속성3 / [중립] 속성4
"""
    from app.core.models.LlmClientDataclass.ChatMessageDataclass import ChatMessage, MessageData

    messages = ChatMessage(content=[MessageData(role="user", content=prompt)])
    response = asyncio.run(llm_client.call_llm(messages))

    return response.strip()

# ============================================================
# R4: 구조화 요약 (Structured Summary) - PoiData 메타데이터 활용
# ============================================================
@register_formatter("R4_구조화요약", description="PoiData 필드를 구조화하여 통합")
def structured_summary_formatter(poi: PoiData, **kwargs) -> str:
    """
    Structured format using PoiData fields.
    Output: "restaurant | 평점 4.5 | MODERATE | 에디토리얼: ... | 리뷰: ..."
    """
    parts = []

    # 카테고리/타입
    parts.append(poi.primary_type or poi.category.value)

    # 평점
    if poi.google_rating:
        rating_str = f"평점 {poi.google_rating}"
        if poi.user_rating_count:
            rating_str += f"({poi.user_rating_count}명)"
        parts.append(rating_str)

    # 가격
    if poi.price_range:
        parts.append(poi.price_range)
    elif poi.price_level:
        parts.append(poi.price_level)

    # Editorial Summary
    if poi.editorial_summary:
        parts.append(f"소개: {poi.editorial_summary}")

    # Generative Summary
    if poi.generative_summary:
        parts.append(f"AI요약: {poi.generative_summary}")

    # Review Summary
    if poi.review_summary:
        parts.append(f"리뷰: {poi.review_summary}")

    return " | ".join(parts)


# ============================================================
# R5: 임베딩 최적화 (Embedding Optimized) - 페르소나와 유사한 형태
# ============================================================
@register_formatter("R5_임베딩최적화", description="페르소나 스타일과 유사한 자연어 형태")
def embedding_optimized_formatter(poi: PoiData, **kwargs) -> str:
    """
    Natural language format optimized for embedding similarity with personas.
    Converts PoiData into persona-like descriptive text.
    """
    sentences = []

    # 장소 유형 설명
    type_str = poi.primary_type or poi.category.value
    type_map = {
        "restaurant": "음식점",
        "cafe": "카페",
        "tourist_attraction": "관광명소",
        "park": "공원",
        "museum": "박물관",
        "shopping_mall": "쇼핑몰",
        "hotel": "호텔",
        "spa": "스파",
        "hiking_area": "등산/산책 코스",
        "amusement_park": "테마파크",
        "amusement_center": "레저/오락 시설",
        "bar": "바/펍",
        "night_club": "클럽/나이트라이프",
        "market": "전통시장",
        "aquarium": "아쿠아리움",
        "sports_complex": "스포츠/레저 시설",
    }
    korean_type = type_map.get(type_str, type_str)
    sentences.append(f"{korean_type}입니다")

    # 평점 기반 분위기
    if poi.google_rating:
        if poi.google_rating >= 4.5:
            sentences.append("평점이 매우 높고 인기 있는 곳입니다")
        elif poi.google_rating >= 4.0:
            sentences.append("평점이 좋은 곳입니다")

    # 가격대
    if poi.price_level:
        price_map = {
            "PRICE_LEVEL_FREE": "무료로 이용 가능합니다",
            "PRICE_LEVEL_INEXPENSIVE": "가격이 저렴합니다",
            "PRICE_LEVEL_MODERATE": "가격이 적당합니다",
            "PRICE_LEVEL_EXPENSIVE": "가격이 비싼 편입니다",
            "PRICE_LEVEL_VERY_EXPENSIVE": "고급 장소입니다",
        }
        if poi.price_level in price_map:
            sentences.append(price_map[poi.price_level])

    # 요약 정보
    if poi.editorial_summary:
        sentences.append(poi.editorial_summary)

    if poi.generative_summary:
        sentences.append(poi.generative_summary)

    # 리뷰 요약
    if poi.review_summary:
        sentences.append(f"방문자 리뷰: {poi.review_summary}")

    return ". ".join(sentences)


def get_formatter(name: str) -> Optional[FormatterConfig]:
    """Get a registered formatter by name."""
    return FORMATTER_REGISTRY.get(name)


def list_formatters() -> List[str]:
    """List all registered formatter names."""
    return list(FORMATTER_REGISTRY.keys())


# ============================================================
# R6: XML로 구조화된 내용
# ============================================================
@register_formatter("R6_XML로구조화된내용", description="XML로 구조화된 내용")
def xml_structured_content_formatter(poi: PoiData, **kwargs) -> str:
    parts = []

    # 장소명
    if poi.name:
        parts.append(f"<name>{poi.name}</name>")

    # 카테고리
    if poi.primary_type:
        parts.append(f"<primary_type>{poi.primary_type}</primary_type>")

    # 타입
    if poi.types:
        parts.append(f"<type>{', '.join(poi.types)}</type>")

    # 주소
    if poi.address:
        parts.append(f"<address>{poi.address}</address>")

    # 평점
    if poi.google_rating:
        parts.append(f"<google_rating>{poi.google_rating or '정보없음'}</google_rating>")

    # 리뷰 수
    if poi.user_rating_count:
        parts.append(f"<user_rating_count>{poi.user_rating_count or '정보없음'}</user_rating_count>")

    # 가격대
    if poi.price_level:
        parts.append(f"<price_level>{poi.price_level or '정보없음'} / {poi.price_range or '정보없음'}</price_level>")

    # editorial_summary
    if poi.editorial_summary:
        parts.append(f"<editorial_summary>{poi.editorial_summary or '정보없음'}</editorial_summary>")

    # generative_summary
    if poi.generative_summary:
        parts.append(f"<generative_summary>{poi.generative_summary or '정보없음'}</generative_summary>")

    # review_summary
    if poi.review_summary:
        parts.append(f"<review_summary>{poi.review_summary or '정보없음'}</review_summary>")
    return "\n".join(parts)


# ============================================================
# R7: 간단한 XML로 구조화된 내용
# ============================================================
@register_formatter("R7_간단한XML로구조화된내용", description="간단한 XML로 구조화된 내용")
def simple_xml_structured_content_formatter(poi: PoiData, **kwargs) -> str:
    parts = []

    # 장소명
    if poi.name:
        parts.append(f"<name>{poi.name}</name>")

    # 타입
    if poi.types:
        parts.append(f"<type>{', '.join(poi.types)}</type>")

    # 가격대
    if poi.price_level:
        parts.append(f"<price_level>{poi.price_level or '정보없음'} / {poi.price_range or '정보없음'}</price_level>")

    # editorial_summary
    if poi.editorial_summary:
        parts.append(f"<editorial_summary>{poi.editorial_summary or '정보없음'}</editorial_summary>")

    # generative_summary
    if poi.generative_summary:
        parts.append(f"<generative_summary>{poi.generative_summary or '정보없음'}</generative_summary>")

    # review_summary
    if poi.review_summary:
        parts.append(f"<review_summary>{poi.review_summary or '정보없음'}</review_summary>")
    return "\n".join(parts)


