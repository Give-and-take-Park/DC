from typing import List
from app.instruments.base import BaseInstrument, Characteristic, InstrumentType, MeasurementResult
from app.instruments.registry import InstrumentRegistry


@InstrumentRegistry.register("B2901A")
class KeysightB2901A(BaseInstrument):
    """Keysight B2901A SMU (DC Source/Measure Unit) GPIB 드라이버"""

    instrument_type = InstrumentType.DC_SOURCE
    supported_characteristics = [Characteristic.DC_BIAS]

    def connect(self) -> None:
        try:
            import pyvisa
            rm = pyvisa.ResourceManager()
            self._resource = rm.open_resource(self.resource_name)
            self._resource.timeout = 5000
        except Exception as e:
            raise ConnectionError(f"B2901A 연결 실패 ({self.resource_name}): {e}")

    def disconnect(self) -> None:
        if self._resource:
            self._resource.close()
            self._resource = None

    def identify(self) -> str:
        return self._resource.query("*IDN?").strip()

    def configure(
        self,
        voltage: float = 0.0,
        current_limit: float = 0.1,
        **kwargs,
    ) -> None:
        """전압 소스 모드로 설정하고 출력을 켠다."""
        self._resource.write(":SOUR:FUNC:MODE VOLT")
        self._resource.write(f":SOUR:VOLT:LEV {voltage}")
        self._resource.write(f":SENS:CURR:PROT {current_limit}")
        self._resource.write(":OUTP ON")

    def measure(self, **kwargs) -> List[MeasurementResult]:
        """출력 전압을 측정하여 반환한다."""
        raw = self._resource.query(":MEAS:VOLT?").strip()
        voltage = float(raw)
        return [
            MeasurementResult(
                characteristic=Characteristic.DC_BIAS,
                value=voltage,
                unit="V",
                raw_response=raw,
            )
        ]
