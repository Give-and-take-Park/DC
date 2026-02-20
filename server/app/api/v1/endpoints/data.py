from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.schemas.data import DataIngestionRequest, DataIngestionResponse
from app.services.data_service import DataService

router = APIRouter()


@router.post("", response_model=DataIngestionResponse, status_code=status.HTTP_201_CREATED)
def ingest_data(
    payload: DataIngestionRequest,
    db: Session = Depends(get_db),
):
    """클라이언트 PC에서 전송된 데이터를 수신, 정규화 후 저장"""
    service = DataService(db)
    return service.ingest(payload)
