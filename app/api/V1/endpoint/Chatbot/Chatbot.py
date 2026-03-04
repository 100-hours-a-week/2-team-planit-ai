"""
챗봇 엔드포인트: /api/v1/chatbot
"""
from fastapi import APIRouter, Depends

from app.schemas.chatbot import ChatbotRequest, ChatbotResponse
from app.api.deps import get_chatbot_service
from app.service.Chatbot.ChatbotService import ChatbotService

router = APIRouter(prefix="/chatbot", tags=["Chatbot"])


@router.post("", response_model=ChatbotResponse)
async def chatbot_endpoint(
    request: ChatbotRequest,
    service: ChatbotService = Depends(get_chatbot_service),
):
    """챗봇 메시지 처리

    사용자 메시지를 받아 Orchestrator를 통해 처리하고,
    일정 변경이 필요하면 백엔드 PATCH API를 호출한 뒤 응답을 반환합니다.
    """
    return await service.chat(request)
