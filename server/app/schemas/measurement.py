from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime
from app.models.measurement import CharacteristicType, ModuleType


class MeasurementIn(BaseModel):
    characteristic: CharacteristicType
    value: float
    unit: str
    frequency: Optional[float] = None
    dc_bias: Optional[float] = None
    temperature: Optional[float] = None
    raw_response: str


class InstrumentRef(BaseModel):
    model: str
    gpib_address: Optional[int] = None
    type: str


class MeasurementSessionCreate(BaseModel):
    client_id: str
    module_type: ModuleType = ModuleType.dc_bias   # 측정 모듈 구분
    session_name: Optional[str] = None
    operator: Optional[str] = None
    instrument: InstrumentRef
    measurements: List[MeasurementIn]


class MlccMeasurementOut(BaseModel):
    id: int
    session_id: int
    characteristic: CharacteristicType
    value: float
    unit: str
    frequency: Optional[float]
    dc_bias: Optional[float]
    temperature: Optional[float]
    measured_at: datetime

    class Config:
        from_attributes = True


class MeasurementSessionOut(BaseModel):
    session_id: int
    client_id: str
    module_type: ModuleType
    measurements_saved: int
