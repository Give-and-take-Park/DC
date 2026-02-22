from typing import List
from app.instruments.base import Characteristic, MeasurementResult
from app.instruments.drivers.lcr_meter.base_lcr import BaseLCRMeter
from app.instruments.registry import InstrumentRegistry


@InstrumentRegistry.register("E4980A")
class KeysightE4980A(BaseLCRMeter):
    """Keysight E4980A Precision LCR Meter GPIB 드라이버 (20 Hz – 2 MHz)

    측정 함수: CPD (Cp–D) 모드
      - Cp : 병렬 등가 정전용량 (F)
      - D  : 손실계수 (dissipation factor, 무차원)
              D = ESR × ω × Cp = 1 / Q

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
    def configure(
        self,
        frequency: float = 1000.0,
        ac_level: float = 1.0,
        dc_bias: float = 0.0,
        **kwargs,
    ) -> None:
        """측정 파라미터를 E4980A로 전송하고 DC 바이어스 출력을 활성화한다.

        전송되는 SCPI 커맨드 (순서 중요):

          :FUNC:IMP:TYPE CPD   — 측정 함수: Cp–D 모드
                                  (FETC? 응답: Cp[F], D[무차원])
          :FREQ <freq>         — 측정 주파수 (20 Hz – 2 MHz)
          :VOLT <level>        — AC 신호 레벨 (5 mV – 2 V rms)
          :BIAS:VOLT <v>       — DC 바이어스 전압 (0 – ±40 V)
          :BIAS:STATe ON       — DC 바이어스 출력 활성화
                                  ※ 이 커맨드 없이는 BIAS:VOLT 설정이 무시됨
          :INIT:CONT ON        — 연속 측정 초기화 활성화
                                  ※ FETC?가 항상 최신값을 반환하도록 보장
                                    (이전 세션에서 단일 트리거 모드였을 경우 대비)
        """
        self._resource.write(":FUNC:IMP:TYPE CPD")   # 측정 함수 → Cp-D
        self._resource.write(f":FREQ {frequency}")    # 주파수 (Hz)
        self._resource.write(f":VOLT {ac_level}")     # AC 레벨 (V rms)
        self._resource.write(f":BIAS:VOLT {dc_bias}") # DC 바이어스 전압 (V)
        self._resource.write(":BIAS:STATe ON")        # DC 바이어스 출력 ON
        self._resource.write(":INIT:CONT ON")         # 연속 측정 모드 활성화

    # ── 측정 ────────────────────────────────────────────────────
    def measure(self, **kwargs) -> List[MeasurementResult]:
        """현재 설정 조건으로 Cp, D 값을 측정하여 반환한다.

        :FETC? — 연속 측정 버퍼에서 최신 결과를 읽는다.
        응답 형식: "+C.CCCCCe-XX,+D.DDDDDe-XX"
          - 첫 번째 값: Cp (단위: F)
          - 두 번째 값: D  (손실계수, 무차원)

        DC Bias 스윕 시 :BIAS:VOLT 변경 후 지연(≥ 1 측정 주기)을 두어야
        버퍼가 새 바이어스 조건의 측정값으로 갱신된다.
        기본 지연 100 ms 는 ≥ 10 Hz 측정에서 안전하다.
        """
        raw = self._resource.query(":FETC?").strip()
        parts = raw.split(",")
        if len(parts) < 2:
            raise ValueError(f"예상치 못한 GPIB 응답: '{raw}'")

        cp_val = float(parts[0])   # Cp (F)
        d_val  = float(parts[1])   # D  (무차원, 손실계수)

        return [
            MeasurementResult(
                characteristic=Characteristic.CAPACITANCE,
                value=cp_val,
                unit="F",
                raw_response=raw,
            ),
            MeasurementResult(
                characteristic=Characteristic.DF,   # D (손실계수) — Rp 아님, ESR 아님
                value=d_val,
                unit="",                            # 무차원
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
        변경 후 충분한 지연(delay_ms)을 두면 :FETC?로 갱신된 측정값을 얻는다.
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
