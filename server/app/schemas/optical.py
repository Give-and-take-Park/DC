from pydantic import BaseModel
from typing import Optional
from datetime import datetime


class OpticalUploadResponse(BaseModel):
    """이미지 업로드 성공 응답"""
    id: int
    original_filename: str
    file_size: Optional[int] = None   # bytes
    uploaded_at: datetime
    status: str = "uploaded"


class OpticalAnalysisOut(BaseModel):
    """광학 이미지 목록 조회 응답"""
    id: int
    operator: Optional[str] = None
    session_name: Optional[str] = None
    original_filename: str
    file_size: Optional[int] = None
    description: Optional[str] = None
    uploaded_at: datetime

    class Config:
        from_attributes = True
