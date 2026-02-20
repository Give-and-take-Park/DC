from typing import List, Optional
from sqlalchemy.orm import Session
from app.models.instrument import Instrument
from app.schemas.instrument import InstrumentCreate


def get_by_model(db: Session, model: str) -> Optional[Instrument]:
    return db.query(Instrument).filter(Instrument.model == model).first()


def create(db: Session, data: InstrumentCreate) -> Instrument:
    obj = Instrument(**data.model_dump())
    db.add(obj)
    db.commit()
    db.refresh(obj)
    return obj


def get_or_create(db: Session, model: str, data: InstrumentCreate) -> Instrument:
    existing = get_by_model(db, model)
    if existing:
        return existing
    return create(db, data)


def list_all(db: Session) -> List[Instrument]:
    return db.query(Instrument).all()
