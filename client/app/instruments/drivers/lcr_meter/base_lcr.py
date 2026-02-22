from app.instruments.base import BaseInstrument, InstrumentType, Characteristic


class BaseLCRMeter(BaseInstrument):
    """LCR 미터 공통 인터페이스"""

    instrument_type = InstrumentType.LCR_METER
    supported_characteristics = [
        Characteristic.CAPACITANCE,
        Characteristic.ESR,
        Characteristic.DF,
        Characteristic.IMPEDANCE,
        Characteristic.Q_FACTOR,
    ]

    def set_frequency(self, frequency: float) -> None:
        """측정 주파수 설정 (Hz)"""
        raise NotImplementedError

    def set_ac_level(self, level: float) -> None:
        """AC 신호 레벨 설정 (V)"""
        raise NotImplementedError

    def set_dc_bias(self, bias: float) -> None:
        """DC 바이어스 전압 설정 (V)"""
        raise NotImplementedError

    def disable_dc_bias(self) -> None:
        """DC 바이어스 출력을 0 V로 복귀하고 비활성화한다."""
        raise NotImplementedError
