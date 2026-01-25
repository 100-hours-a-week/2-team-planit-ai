from pydantic import BaseModel, Field
from typing import List, Optional, Union
from app.schemas.persona import ItineraryRequest
from typing import TypedDict

class QAItem(BaseModel):
    id: int = Field(..., description="질문 ID")
    question: str = Field(..., description="질문 내용")
    answer: Optional[Union[str, List[str]]] = Field(None, description="답변 내용")

class Persona(BaseModel):
    summary: str = Field(..., description="한 줄로 요약된 여행 페르소나")

