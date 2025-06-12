from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime

class ChatMessage(BaseModel):
    sender: str
    message: str
    timestamp: Optional[datetime] = None

class ChatHistory(BaseModel):
    user_id: str
    messages: List[ChatMessage] 