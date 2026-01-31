from pydantic import BaseModel
from typing import List

class MessageData(BaseModel):
    role: str
    content: str

class ChatMessage(BaseModel):
    content: List[MessageData]
    