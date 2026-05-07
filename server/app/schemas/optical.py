from pydantic import BaseModel
from typing import Optional
from datetime import datetime


class OpticalUploadResponse(BaseModel):
    """ZIP 업로드 성공 응답"""
    id: int
    original_filename: str
    file_size: Optional[int] = None
    lot_no: Optional[str] = None
    uploaded_at: datetime
    status: str = "uploaded"


class OpticalAnalysisOut(BaseModel):
    """광학 이미지 목록 조회 응답"""
    id: int
    operator: Optional[str] = None
    lot_no: Optional[str] = None
    session_name: Optional[str] = None
    original_filename: str
    file_size: Optional[int] = None
    description: Optional[str] = None
    status: str = "uploaded"
    uploaded_at: datetime
    analyzed_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class OpticalAnalyzeRequest(BaseModel):
    """분석 요청 바디"""
    record_id: int


class OpticalAnalyzeResponse(BaseModel):
    """분석 완료 응답 — 분석이 끝난 후에 반환됩니다."""
    record_id: int
    status: str
    result_filename: Optional[str] = None
