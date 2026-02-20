from pydantic import BaseModel
from typing import Any, Dict, List, Optional
from datetime import datetime


class DataIngestionRequest(BaseModel):
    client_id: str
    payload: Dict[str, Any]


class DataIngestionResponse(BaseModel):
    id: int
    client_id: str
    received_at: datetime

    class Config:
        from_attributes = True


class NormalizedDataOut(BaseModel):
    id: int
    raw_data_id: int
    client_id: str
    value: Optional[float]
    label: Optional[str]
    normalized_at: datetime

    class Config:
        from_attributes = True


class PaginatedResponse(BaseModel):
    total: int
    page: int
    size: int
    items: List[NormalizedDataOut]
