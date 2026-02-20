from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional


class Characteristic(str, Enum):
    CAPACITANCE = "capacitance"
    ESR = "esr"
    DF = "df"
    IMPEDANCE = "impedance"
    Q_FACTOR = "q_factor"
    DC_BIAS = "dc_bias"


class InstrumentType(str, Enum):
    LCR_METER = "lcr_meter"
    DC_SOURCE = "dc_source"
    OSCILLOSCOPE = "oscilloscope"
    MULTIMETER = "multimeter"


@dataclass
class MeasurementResult:
    characteristic: Characteristic
    value: float
    unit: str
    raw_response: str
    frequency: Optional[float] = None
    dc_bias: Optional[float] = None
    temperature: Optional[float] = None


class BaseInstrument(ABC):
    """모든 계측기 드라이버의 추상 베이스 클래스"""

    instrument_type: InstrumentType
    supported_characteristics: List[Characteristic] = []

    def __init__(self, resource_name: str):
        self.resource_name = resource_name
        self._resource = None

    @abstractmethod
    def connect(self) -> None:
        """계측기에 연결한다."""
        ...

    @abstractmethod
    def disconnect(self) -> None:
        """연결을 해제한다."""
        ...

    @abstractmethod
    def identify(self) -> str:
        """*IDN? 응답 문자열을 반환한다."""
        ...

    @abstractmethod
    def configure(self, **kwargs) -> None:
        """측정 파라미터를 설정한다."""
        ...

    @abstractmethod
    def measure(self, **kwargs) -> List[MeasurementResult]:
        """측정을 실행하고 결과 목록을 반환한다."""
        ...

    def __enter__(self):
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.disconnect()
