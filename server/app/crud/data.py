from sqlalchemy.orm import Session
from sqlalchemy import func
from app.models.data import RawData, NormalizedData
from app.schemas.data import DataIngestionRequest
from typing import Dict, Any


def create_raw(db: Session, payload: DataIngestionRequest) -> RawData:
    obj = RawData(client_id=payload.client_id, raw_payload=payload.payload)
    db.add(obj)
    db.commit()
    db.refresh(obj)
    return obj


def create_normalized(db: Session, raw_id: int, data: Dict[str, Any]) -> NormalizedData:
    obj = NormalizedData(raw_data_id=raw_id, **data)
    db.add(obj)
    db.commit()
    db.refresh(obj)
    return obj


def get_summary(db: Session) -> Dict[str, Any]:
    total = db.query(func.count(NormalizedData.id)).scalar()
    return {"total_records": total}


def get_records(db: Session, page: int, size: int):
    total = db.query(func.count(NormalizedData.id)).scalar()
    items = (
        db.query(NormalizedData)
        .order_by(NormalizedData.normalized_at.desc())
        .offset((page - 1) * size)
        .limit(size)
        .all()
    )
    return {"total": total, "page": page, "size": size, "items": items}
