from typing import List
from app.instruments.base import Characteristic, MeasurementResult
from app.instruments.drivers.lcr_meter.base_lcr import BaseLCRMeter
from app.instruments.registry import InstrumentRegistry


@InstrumentRegistry.register("E4980A")
class KeysightE4980A(BaseLCRMeter):
    """Keysight E4980A Precision LCR Meter GPIB 드라이버 (20 Hz – 2 MHz)"""

    def connect(self) -> None:
        try:
            import pyvisa
            rm = pyvisa.ResourceManager()
            self._resource = rm.open_resource(self.resource_name)
            self._resource.timeout = 5000  # ms
        except Exception as e:
            raise ConnectionError(f"E4980A 연결 실패 ({self.resource_name}): {e}")

    def disconnect(self) -> None:
        if self._resource:
            self._resource.close()
            self._resource = None

    def identify(self) -> str:
        return self._resource.query("*IDN?").strip()

    def configure(
        self,
        frequency: float = 1000.0,
        ac_level: float = 1.0,
        dc_bias: float = 0.0,
        **kwargs,
    ) -> None:
        """Cp-Rp モード で測定パラメータを設定する."""
        self._resource.write(f"FREQ {frequency}")
        self._resource.write(f"VOLT {ac_level}")
        self._resource.write(f"BIAS:VOLT {dc_bias}")
        self._resource.write("FUNC:IMP:TYPE CPRP")  # Cp-Rp 모드

    def measure(self, **kwargs) -> List[MeasurementResult]:
        """FETC? 로 Cp, Rp 값을 읽어 MeasurementResult 목록으로 반환한다."""
        raw = self._resource.query("FETC?").strip()
        parts = raw.split(",")
        if len(parts) < 2:
            raise ValueError(f"예상치 못한 GPIB 응답: '{raw}'")

        cap_val = float(parts[0])
        esr_val = float(parts[1])

        return [
            MeasurementResult(
                characteristic=Characteristic.CAPACITANCE,
                value=cap_val,
                unit="F",
                raw_response=raw,
            ),
            MeasurementResult(
                characteristic=Characteristic.ESR,
                value=esr_val,
                unit="Ω",
                raw_response=raw,
            ),
        ]

    def set_frequency(self, frequency: float) -> None:
        self._resource.write(f"FREQ {frequency}")

    def set_ac_level(self, level: float) -> None:
        self._resource.write(f"VOLT {level}")

    def set_dc_bias(self, bias: float) -> None:
        self._resource.write(f"BIAS:VOLT {bias}")
