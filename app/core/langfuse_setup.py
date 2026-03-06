"""
Langfuse 트레이싱 초기화 모듈

주요 기능:
- Langfuse 클라이언트 초기화 (환경변수 기반)
- LangChain/LangGraph용 CallbackHandler 팩토리
- 키 미설정 시 자동 비활성화 (graceful degradation)
"""
import logging
import os
from typing import Optional

from app.core.config import settings

logger = logging.getLogger(__name__)

_langfuse_initialized: bool = False


def init_langfuse() -> bool:
    """앱 시작 시 호출. 키 미설정 시 False 반환.

    Langfuse SDK는 환경변수(LANGFUSE_SECRET_KEY, LANGFUSE_PUBLIC_KEY,
    LANGFUSE_HOST)를 자동으로 읽어 초기화합니다.
    이 함수는 키 존재 여부를 사전 검증하고, 상태 플래그를 관리합니다.
    """
    global _langfuse_initialized

    if not settings.langfuse_enabled:
        logger.info("Langfuse 비활성화 (langfuse_enabled=False)")
        return False

    if not settings.langfuse_secret_key or not settings.langfuse_public_key:
        logger.warning("Langfuse API 키 미설정 — 트레이싱 비활성화")
        return False

    # Langfuse SDK가 환경변수를 올바르게 인식하도록 보장
    os.environ.setdefault("LANGFUSE_SECRET_KEY", settings.langfuse_secret_key)
    os.environ.setdefault("LANGFUSE_PUBLIC_KEY", settings.langfuse_public_key)
    os.environ.setdefault("LANGFUSE_HOST", settings.langfuse_host)

    _langfuse_initialized = True
    logger.info("Langfuse 초기화 완료: %s", settings.langfuse_host)
    return True


def get_langfuse_handler(**kwargs):
    """LangChain/LangGraph 실행 시 사용할 CallbackHandler 생성.

    Langfuse 미초기화 시 None 반환하여 기존 동작에 영향 없음.

    Args:
        **kwargs: CallbackHandler에 전달할 추가 인자
            (session_id, user_id, tags 등)

    Returns:
        CallbackHandler 또는 None
    """
    if not _langfuse_initialized:
        return None

    try:
        from langfuse.langchain import CallbackHandler
        from langfuse import get_client

        # 현재 @observe 컨텍스트의 trace_id를 가져와 동일 트레이스에 연결
        client = get_client()
        trace_id = client.get_current_trace_id()
        if trace_id:
            kwargs.setdefault("trace_id", trace_id)

        return CallbackHandler(**kwargs)
    except Exception as e:
        logger.warning("Langfuse CallbackHandler 생성 실패: %s", e)
        return None


def is_langfuse_enabled() -> bool:
    """Langfuse 트레이싱 활성화 여부 반환."""
    return _langfuse_initialized


def flush_langfuse() -> None:
    """Langfuse 버퍼를 flush합니다. 앱 종료 시 호출."""
    if not _langfuse_initialized:
        return

    try:
        from langfuse import get_client
        client = get_client()
        client.flush()
        logger.info("Langfuse flush 완료")
    except Exception as e:
        logger.warning("Langfuse flush 실패: %s", e)
