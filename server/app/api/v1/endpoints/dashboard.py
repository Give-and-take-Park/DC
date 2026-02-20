from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.services.data_service import DataService

router = APIRouter()


@router.get("/summary")
def get_summary(db: Session = Depends(get_db)):
    """대시보드 요약 통계 조회"""
    service = DataService(db)
    return service.get_summary()


@router.get("/records")
def get_records(
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
):
    """정규화된 데이터 목록 페이지네이션 조회"""
    service = DataService(db)
    return service.get_records(page=page, size=size)
