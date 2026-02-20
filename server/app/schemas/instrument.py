from pydantic import BaseModel
from typing import Optional
from app.models.instrument import InstrumentType


class InstrumentBase(BaseModel):
    name: str
    model: str
    manufacturer: Optional[str] = None
    instrument_type: InstrumentType
    gpib_address: Optional[int] = None
    description: Optional[str] = None


class InstrumentCreate(InstrumentBase):
    pass


class InstrumentOut(InstrumentBase):
    id: int

    class Config:
        from_attributes = True
