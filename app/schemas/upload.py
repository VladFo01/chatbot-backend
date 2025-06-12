from pydantic import BaseModel
from typing import Optional

class UploadResponse(BaseModel):
    file_id: str
    filename: str
    status: str

class ProcessingStatus(BaseModel):
    file_id: str
    status: str
    detail: Optional[str] = None 