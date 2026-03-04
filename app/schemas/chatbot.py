"""
챗봇 API 요청/응답 스키마

/api/v1/chatbot 엔드포인트에서 사용하는 Pydantic 모델
"""
from pydantic import BaseModel


class ChatbotRequest(BaseModel):
    """챗봇 요청"""
    tripId: int
    content: str        # 사용자 메시지
    userJWT: str        # 백엔드 API 인증용 JWT


class ChatbotResponse(BaseModel):
    """챗봇 응답"""
    tripId: int
    content: str        # 챗봇 응답 메시지
