from pydantic import BaseModel
from typing import List

class MessageData(BaseModel):
    role: str
    content: str

class ChatMessgage(BaseModel):
    content: List[MessageData]