from typing import List
from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.schemas.instrument import InstrumentCreate, InstrumentOut
from app.crud import instrument as crud_instrument

router = APIRouter()


@router.get("", response_model=List[InstrumentOut])
def list_instruments(db: Session = Depends(get_db)):
    """등록된 계측기 목록 조회"""
    return crud_instrument.list_all(db)


@router.post("", response_model=InstrumentOut, status_code=status.HTTP_201_CREATED)
def register_instrument(
    data: InstrumentCreate,
    db: Session = Depends(get_db),
):
    """계측기 수동 등록"""
    return crud_instrument.create(db, data)
