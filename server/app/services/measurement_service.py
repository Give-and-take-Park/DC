from sqlalchemy.orm import Session
from app.schemas.measurement import MeasurementSessionCreate, MeasurementSessionOut
from app.schemas.instrument import InstrumentCreate
from app.models.instrument import InstrumentType
from app.crud import instrument as crud_instrument
from app.crud import measurement as crud_measurement
from app.services.normalizer import normalize_unit


class MeasurementService:
    def __init__(self, db: Session):
        self.db = db

    def ingest(self, payload: MeasurementSessionCreate) -> MeasurementSessionOut:
        # 계측기 조회 또는 자동 등록
        instrument = crud_instrument.get_or_create(
            self.db,
            payload.instrument.model,
            InstrumentCreate(
                name=payload.instrument.model,
                model=payload.instrument.model,
                instrument_type=InstrumentType(payload.instrument.type),
                gpib_address=payload.instrument.gpib_address,
            ),
        )

        # 측정 세션 생성
        session = crud_measurement.create_session(
            self.db,
            client_id=payload.client_id,
            session_name=payload.session_name,
            operator=payload.operator,
        )

        # 각 측정값 저장
        for m in payload.measurements:
            raw = crud_measurement.create_raw(
                self.db,
                session_id=session.id,
                instrument_id=instrument.id,
                raw_response=m.raw_response,
            )
            # 단위 정규화
            normalized_value, normalized_unit = normalize_unit(
                m.characteristic.value, m.value, m.unit
            )
            crud_measurement.create_mlcc(
                self.db,
                session_id=session.id,
                raw_id=raw.id,
                instrument_id=instrument.id,
                data={
                    "characteristic": m.characteristic,
                    "value": normalized_value,
                    "unit": normalized_unit,
                    "frequency": m.frequency,
                    "dc_bias": m.dc_bias,
                    "temperature": m.temperature,
                },
            )

        return MeasurementSessionOut(
            session_id=session.id,
            client_id=payload.client_id,
            measurements_saved=len(payload.measurements),
        )
