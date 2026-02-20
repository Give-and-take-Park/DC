from typing import Any, Dict, Optional
from sqlalchemy.orm import Session
from sqlalchemy import func
from app.models.measurement import MeasurementSession, RawMeasurement, MlccMeasurement


def create_session(
    db: Session,
    client_id: str,
    session_name: Optional[str],
    operator: Optional[str],
) -> MeasurementSession:
    obj = MeasurementSession(
        client_id=client_id,
        session_name=session_name,
        operator=operator,
    )
    db.add(obj)
    db.commit()
    db.refresh(obj)
    return obj


def create_raw(
    db: Session,
    session_id: int,
    instrument_id: Optional[int],
    raw_response: str,
) -> RawMeasurement:
    obj = RawMeasurement(
        session_id=session_id,
        instrument_id=instrument_id,
        raw_response=raw_response,
    )
    db.add(obj)
    db.commit()
    db.refresh(obj)
    return obj


def create_mlcc(
    db: Session,
    session_id: int,
    raw_id: int,
    instrument_id: Optional[int],
    data: Dict[str, Any],
) -> MlccMeasurement:
    obj = MlccMeasurement(
        session_id=session_id,
        raw_measurement_id=raw_id,
        instrument_id=instrument_id,
        **data,
    )
    db.add(obj)
    db.commit()
    db.refresh(obj)
    return obj


def get_summary(db: Session) -> Dict[str, Any]:
    total_measurements = db.query(func.count(MlccMeasurement.id)).scalar()
    total_sessions = db.query(func.count(MeasurementSession.id)).scalar()
    return {
        "total_measurements": total_measurements,
        "total_sessions": total_sessions,
    }


def get_records(
    db: Session,
    page: int,
    size: int,
    characteristic: Optional[str] = None,
) -> Dict[str, Any]:
    q = db.query(MlccMeasurement)
    if characteristic:
        q = q.filter(MlccMeasurement.characteristic == characteristic)
    total = q.count()
    items = (
        q.order_by(MlccMeasurement.measured_at.desc())
        .offset((page - 1) * size)
        .limit(size)
        .all()
    )
    return {"total": total, "page": page, "size": size, "items": items}
