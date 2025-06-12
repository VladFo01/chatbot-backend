from pydantic import BaseModel
from typing import Optional
from datetime import datetime

class UploadResponse(BaseModel):
    file_id: str
    filename: str
    status: str

class ProcessingStatus(BaseModel):
    file_id: str
    status: str
    processing_step: Optional[str] = None
    chunks_count: Optional[int] = None
    text_length: Optional[int] = None
    error: Optional[str] = None
    uploaded_at: Optional[datetime] = None
    processed_at: Optional[datetime] = None

 