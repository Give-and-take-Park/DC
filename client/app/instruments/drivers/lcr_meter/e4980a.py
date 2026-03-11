from typing import List
from app.instruments.base import Characteristic, MeasurementResult
from app.instruments.drivers.lcr_meter.base_lcr import BaseLCRMeter
from app.instruments.registry import InstrumentRegistry


@InstrumentRegistry.register("E4980A")
class KeysightE4980A(BaseLCRMeter):
    """Keysight E4980A Precision LCR Meter GPIB 드라이버 (20 Hz – 2 MHz)

    지원 측정 함수:
      CPD — Cp–D 모드 : 병렬 등가 정전용량(Cp, F) + 손실계수(D, 무차원)
      CSD — Cs–D 모드 : 직렬 등가 정전용량(Cs, F) + 손실계수(D, 무차원)

    MLCC DC Bias 특성 평가의 IEC/JIS 표준은 CPD 모드를 사용한다.
    ESR(직렬 등가 저항 Rs) 측정이 필요하면 CSRS 모드를 별도 사용한다.
    """

    # ── 연결 / 해제 ─────────────────────────────────────────────
    def connect(self) -> None:
        try:
            import pyvisa
            rm = pyvisa.ResourceManager()
            self._resource = rm.open_resource(self.resource_name)
            self._resource.timeout = 10_000  # 10 s (저주파 측정 여유 확보)
        except Exception as e:
            raise ConnectionError(f"E4980A 연결 실패 ({self.resource_name}): {e}")

    def disconnect(self) -> None:
        if self._resource:
            self._resource.close()
            self._resource = None

    def identify(self) -> str:
        """*IDN? — IEEE 488.2 식별 쿼리"""
        return self._resource.query("*IDN?").strip()

    # ── 파라미터 설정 ────────────────────────────────────────────
    def setup_sweep(self, mode: str = "CPD") -> None:
        """스윕 시작 전 1회 호출 — 스윕 내내 변하지 않는 파라미터를 설정한다.

          :FUNC:IMP:TYPE <mode> — 측정 함수 (CPD / CSD)
          :BIAS:STATe ON        — DC 바이어스 출력 활성화
          :INIT:CONT ON         — 연속 측정 모드 활성화 (FETC?가 항상 최신값 반환)
                                   ※ 루프마다 재전송하면 트리거가 리셋되므로 1회만 전송
        주파수는 행별로 달라질 수 있으므로 configure()에서 행마다 전송한다.
        """
        self._resource.write(f":FUNC:IMP:TYPE {mode}")  # 측정 함수 (CPD / CSD)
        self._resource.write(":BIAS:STATe ON")           # DC 바이어스 출력 ON
        self._resource.write(":INIT:CONT ON")            # 연속 측정 모드 활성화

    def configure(
        self,
        frequency: float = 1000.0,
        ac_level: float = 1.0,
        dc_bias: float = 0.0,
        mode: str = "CPD",
        **kwargs,
    ) -> None:
        """스윕 루프 내 각 행마다 호출 — 행별로 달라지는 파라미터를 전송한다.

          :FREQ <freq>   — 측정 주파수 (20 Hz – 2 MHz, 행별 지정)
          :VOLT <level>  — AC 신호 레벨 (5 mV – 2 V rms)
          :BIAS:VOLT <v> — DC 바이어스 전압 (0 – ±40 V)
        """
        self._resource.write(f":FREQ {frequency}")       # 주파수 (Hz) — 행별 설정
        self._resource.write(f":VOLT {ac_level}")        # AC 레벨 (V rms)
        self._resource.write(f":BIAS:VOLT {dc_bias}")    # DC 바이어스 전압 (V)

    # ── 측정 ────────────────────────────────────────────────────
    def measure(self, **kwargs) -> List[MeasurementResult]:
        """현재 설정 조건으로 C, D 값을 측정하여 반환한다.

        :FETC? — 연속 측정 버퍼에서 최신 결과를 읽는다.
        응답 형식: "+C.CCCCCe-XX,+D.DDDDDe-XX"
          - 첫 번째 값: Cp 또는 Cs (단위: F, 모드에 따라 결정)
          - 두 번째 값: D  (손실계수, 무차원)

        DC Bias 스윕 시 :BIAS:VOLT 변경 후 지연(≥ 1 측정 주기)을 두어야
        버퍼가 새 바이어스 조건의 측정값으로 갱신된다.
        """
        raw = self._resource.query(":FETC?").strip()
        parts = raw.split(",")
        if len(parts) < 2:
            raise ValueError(f"예상치 못한 GPIB 응답: '{raw}'")

        cap_val = float(parts[0])  # Cp 또는 Cs (F)
        d_val   = float(parts[1])  # D  (무차원, 손실계수)

        return [
            MeasurementResult(
                characteristic=Characteristic.CAPACITANCE,
                value=cap_val,
                unit="F",
                raw_response=raw,
            ),
            MeasurementResult(
                characteristic=Characteristic.DF,
                value=d_val,
                unit="",
                raw_response=raw,
            ),
        ]

    # ── 개별 파라미터 변경 ───────────────────────────────────────
    def set_frequency(self, frequency: float) -> None:
        """:FREQ — 측정 주파수 변경 (Hz)"""
        self._resource.write(f":FREQ {frequency}")

    def set_ac_level(self, level: float) -> None:
        """:VOLT — AC 신호 레벨 변경 (V rms)"""
        self._resource.write(f":VOLT {level}")

    def set_dc_bias(self, bias: float) -> None:
        """:BIAS:VOLT — DC 바이어스 전압 변경 (V).

        configure() 이후 :BIAS:STATe는 ON 상태이므로 전압만 갱신한다.
        변경 후 충분한 지연을 두면 :FETC?로 갱신된 측정값을 얻는다.
        """
        self._resource.write(f":BIAS:VOLT {bias}")

    # ── DC 바이어스 해제 ─────────────────────────────────────────
    def disable_dc_bias(self) -> None:
        """DC 바이어스를 0 V로 복귀하고 출력을 비활성화한다.

        :BIAS:VOLT 0      — 전압을 0 V 로 설정
        :BIAS:STATe OFF   — DC 바이어스 출력 차단

        스윕 완료·중단 시 반드시 호출하여 DUT 보호.
        """
        self._resource.write(":BIAS:VOLT 0")
        self._resource.write(":BIAS:STATe OFF")
