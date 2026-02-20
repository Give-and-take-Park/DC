import enum
from sqlalchemy import Column, Integer, String, Enum as SAEnum
from app.db.base import Base


class InstrumentType(str, enum.Enum):
    lcr_meter = "lcr_meter"
    dc_source = "dc_source"
    oscilloscope = "oscilloscope"
    multimeter = "multimeter"


class Instrument(Base):
    """등록된 계측기 정보"""
    __tablename__ = "instruments"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(200), nullable=False)
    model = Column(String(100), nullable=False, index=True)
    manufacturer = Column(String(100), nullable=True)
    instrument_type = Column(SAEnum(InstrumentType), nullable=False)
    gpib_address = Column(Integer, nullable=True)
    description = Column(String(500), nullable=True)
