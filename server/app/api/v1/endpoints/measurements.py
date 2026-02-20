from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.schemas.measurement import MeasurementSessionCreate, MeasurementSessionOut
from app.services.measurement_service import MeasurementService

router = APIRouter()


@router.post("", response_model=MeasurementSessionOut, status_code=status.HTTP_201_CREATED)
def ingest_measurements(
    payload: MeasurementSessionCreate,
    db: Session = Depends(get_db),
):
    """클라이언트에서 전송된 MLCC 측정 데이터를 수신·정규화·저장"""
    service = MeasurementService(db)
    return service.ingest(payload)
