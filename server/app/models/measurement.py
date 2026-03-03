import enum
from sqlalchemy import Column, Integer, String, Enum as SAEnum, DateTime, Double, ForeignKey, Text
from sqlalchemy.sql import func
from app.db.base import Base


class ModuleType(str, enum.Enum):
    """클라이언트 측정 모듈 구분 (화면 카드와 1:1 매핑)"""
    dc_bias   = "dc_bias"     # DC Bias 전압 스윕 측정
    halt_8585 = "halt_8585"   # HALT / 85°C 85%RH 신뢰성 시험 측정


class CharacteristicType(str, enum.Enum):
    """측정 물리 특성 (모듈 공통)"""
    capacitance = "capacitance"
    esr         = "esr"
    df          = "df"
    impedance   = "impedance"
    q_factor    = "q_factor"
    dc_bias     = "dc_bias"


class MeasurementSession(Base):
    """측정 세션 (1회 측정 작업 단위)"""
    __tablename__ = "measurement_sessions"

    id           = Column(Integer, primary_key=True, index=True)
    client_id    = Column(String(100), nullable=False, index=True)
    module_type  = Column(SAEnum(ModuleType), nullable=False,
                          default=ModuleType.dc_bias, index=True)
    session_name = Column(String(200), nullable=True)
    started_at   = Column(DateTime(timezone=True), server_default=func.now())
    ended_at     = Column(DateTime(timezone=True), nullable=True)
    operator     = Column(String(100), nullable=True)
    notes        = Column(Text, nullable=True)


class RawMeasurement(Base):
    """계측기 원시 GPIB 응답 (감사/재처리용)"""
    __tablename__ = "raw_measurements"

    id            = Column(Integer, primary_key=True, index=True)
    session_id    = Column(Integer, ForeignKey("measurement_sessions.id"),
                           nullable=False, index=True)
    instrument_id = Column(Integer, ForeignKey("instruments.id"),
                           nullable=True, index=True)
    raw_response  = Column(Text, nullable=False)
    measured_at   = Column(DateTime(timezone=True), server_default=func.now())


class MlccMeasurement(Base):
    """정규화된 MLCC 특성값"""
    __tablename__ = "mlcc_measurements"

    id                 = Column(Integer, primary_key=True, index=True)
    raw_measurement_id = Column(Integer, ForeignKey("raw_measurements.id"),
                                nullable=True, index=True)
    session_id         = Column(Integer, ForeignKey("measurement_sessions.id"),
                                nullable=False, index=True)
    instrument_id      = Column(Integer, ForeignKey("instruments.id"),
                                nullable=True, index=True)
    characteristic     = Column(SAEnum(CharacteristicType), nullable=False)
    value              = Column(Double, nullable=False)
    unit               = Column(String(20), nullable=False)
    frequency          = Column(Double, nullable=True)   # Hz
    dc_bias            = Column(Double, nullable=True)   # V
    temperature        = Column(Double, nullable=True)   # °C
    measured_at        = Column(DateTime(timezone=True), server_default=func.now())
