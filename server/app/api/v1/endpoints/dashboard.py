from typing import Optional
from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from pathlib import Path
from app.db.session import get_db
from app.crud import measurement as crud_measurement

router = APIRouter()

_TEMPLATES_DIR = Path(__file__).resolve().parent.parent.parent.parent.parent.parent / "web" / "templates"
templates = Jinja2Templates(directory=str(_TEMPLATES_DIR))


@router.get("/summary")
def get_summary(db: Session = Depends(get_db)):
    """MLCC 측정 대시보드 요약 통계"""
    return crud_measurement.get_summary(db)


@router.get("/records")
def get_records(
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    characteristic: Optional[str] = Query(None, description="capacitance|esr|df|impedance|q_factor|dc_bias"),
    db: Session = Depends(get_db),
):
    """MLCC 측정 데이터 목록 페이지네이션 조회"""
    return crud_measurement.get_records(db, page=page, size=size, characteristic=characteristic)
