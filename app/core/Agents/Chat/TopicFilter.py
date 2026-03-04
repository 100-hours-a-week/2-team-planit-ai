"""
TopicFilter: 여행 관련 주제 필터 (vLLM structured output)

사용자 메시지가 여행 관련 주제인지 이진 판별하는 경량 필터입니다.
- 여행, 관광, 맛집, 일정, 숙소, 교통 등 → on_topic
- 환전, 날씨, 문화 등 여행 부가 질문 → on_topic
- 완전히 무관한 주제 (스포츠, 주식 등) → off_topic
"""
import logging
from typing import List, Optional

from pydantic import BaseModel, Field

from app.core.LLMClient.BaseLlmClient import BaseLLMClient
from app.core.models.LlmClientDataclass.ChatMessageDataclass import (
    ChatMessage,
    MessageData,
)

try:
    from langfuse import observe
except ImportError:
    def observe(**kwargs):
        def decorator(fn):
            return fn
        return decorator

logger = logging.getLogger(__name__)

# ─── 시스템 프롬프트 ──────────────────────────────────

TOPIC_FILTER_SYSTEM_PROMPT = """당신은 여행 챗봇의 주제 필터입니다.
사용자 메시지가 여행 관련 주제인지 판별하세요.

## 여행 관련 (is_on_topic = true)
- 여행지, 관광지, 맛집, 카페, 숙소 추천
- 여행 일정 수정/추가/삭제
- 교통, 이동 수단, 경로
- 환전, 비자, 날씨, 문화, 에티켓 등 여행 부가 정보
- 여행 준비물, 팁, 주의사항
- 특정 도시/나라에 대한 질문

## 여행 무관 (is_on_topic = false)
- 스포츠 경기 결과, 주식, 코딩, 수학 등
- 일상 대화 (인사, 감사 등은 문맥에 따라 판단)

대화 맥락을 고려하여 판단하세요. 이전 대화가 여행 관련이었다면, 후속 질문도 여행 관련일 가능성이 높습니다."""


# ─── Pydantic 출력 모델 ──────────────────────────────

class TopicFilterResult(BaseModel):
    """주제 필터링 결과"""
    is_on_topic: bool = Field(
        description="여행 관련 주제이면 true, 아니면 false"
    )
    confidence: float = Field(
        ge=0.0, le=1.0,
        description="판단 확신도 (0.0~1.0)"
    )
    reasoning: str = Field(
        description="판단 근거 (한 문장)"
    )


# ─── TopicFilter 클래스 ─────────────────────────────

class TopicFilter:
    """여행 관련 주제 필터

    VllmClient.call_llm_structured()를 사용하여
    경량 프롬프트로 빠르게 주제를 판별합니다.
    """

    def __init__(self, llm_client: BaseLLMClient):
        """
        Args:
            llm_client: vLLM 클라이언트 (call_llm_structured 지원)
        """
        self.llm_client = llm_client

    @observe(name="topic-filter")
    async def filter(
        self,
        user_message: str,
        recent_messages: Optional[List[dict]] = None,
    ) -> TopicFilterResult:
        """주제 필터링 실행

        Args:
            user_message: 현재 사용자 메시지
            recent_messages: 최근 대화 히스토리 (컨텍스트, 최대 3턴 권장)
                            [{"role": "user"/"assistant", "content": "..."}]

        Returns:
            TopicFilterResult: 필터링 결과 (is_on_topic, confidence, reasoning)
        """
        # 사용자 프롬프트 구성
        user_prompt = self._build_user_prompt(user_message, recent_messages)

        prompt = ChatMessage(content=[
            MessageData(role="system", content=TOPIC_FILTER_SYSTEM_PROMPT),
            MessageData(role="user", content=user_prompt),
        ])

        try:
            result = await self.llm_client.call_llm_structured(
                prompt=prompt,
                model=TopicFilterResult,
            )
            logger.debug(
                f"TopicFilter 결과: is_on_topic={result.is_on_topic}, "
                f"confidence={result.confidence:.2f}, "
                f"reasoning={result.reasoning}"
            )
            return result

        except Exception as e:
            logger.error(f"TopicFilter LLM 호출 실패: {e}")
            # LLM 실패 시 안전하게 on_topic으로 처리 (사용자 요청을 무시하지 않기 위해)
            return TopicFilterResult(
                is_on_topic=True,
                confidence=0.0,
                reasoning=f"LLM 호출 실패로 기본값(on_topic) 적용: {str(e)}",
            )

    def _build_user_prompt(
        self,
        user_message: str,
        recent_messages: Optional[List[dict]] = None,
    ) -> str:
        """사용자 프롬프트 구성

        Args:
            user_message: 현재 사용자 메시지
            recent_messages: 최근 대화 히스토리

        Returns:
            str: 구성된 프롬프트 텍스트
        """
        parts = []

        # 최근 대화 컨텍스트 추가 (최대 3턴 = 6메시지)
        if recent_messages:
            context_messages = recent_messages[-6:]  # 최대 3턴
            if context_messages:
                parts.append("## 최근 대화 맥락")
                for msg in context_messages:
                    role = "사용자" if msg.get("role") == "user" else "어시스턴트"
                    parts.append(f"- {role}: {msg.get('content', '')}")
                parts.append("")

        parts.append(f"## 현재 사용자 메시지\n{user_message}")
        parts.append("\n위 메시지가 여행 관련 주제인지 판별하세요.")

        return "\n".join(parts)
