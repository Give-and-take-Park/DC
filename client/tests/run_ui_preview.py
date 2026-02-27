#!/usr/bin/env python
"""
UI 미리보기 실행기 — 서버·GPIB 없이 클라이언트 GUI를 확인합니다.

실행 방법:
    cd client
    python tests/run_ui_preview.py

동작 요약:
    - LoginDialog : 임의 사용자명/비밀번호로 로그인 가능 (서버 미사용)
    - MainWindow  : 카드 클릭 → 측정 페이지 전환 정상 동작
    - 로그아웃    : 로그아웃 버튼 클릭 시 로그인 다이얼로그로 복귀 (main.py 동일 흐름)
    - 계측기 연결 : 각 측정 페이지의 "계측기 연결" 버튼 클릭 시 모의 E4980A 자동 주입
    - 카드 클릭   : 페이지 생성 직후 모의 계측기 자동 주입 (버튼 클릭 불필요)
    - DC Bias 스윕: X5R 100 nF 시뮬레이션 데이터로 테이블 채움
    - 일반 측정   : "측정 시작" 버튼 시 시뮬레이션 값 표시
    - 서버 전송   : 가짜 성공 응답 (실제 네트워크 미사용)
    - 상태바      : "서버: 연결됨" 녹색 표시 (모의 check_server)
"""

import random
import sys
from pathlib import Path
from unittest.mock import patch

# ── client/ 디렉터리를 모듈 검색 경로에 추가 ────────────────────────────
_CLIENT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_CLIENT_DIR))

# pylint: disable=wrong-import-position
from PyQt6.QtCore import QEventLoop
from PyQt6.QtWidgets import QApplication

from app.config.settings import Settings
from app.instruments.base import Characteristic, MeasurementResult
from app.instruments.drivers.lcr_meter.base_lcr import BaseLCRMeter
from app.ui.login_dialog import LoginDialog
from app.ui.main_window import MainWindow
from app.ui.pages.dc_bias_page import DCBiasMeasurementPage
from app.ui.pages.measurement_page import MeasurementPage


# ── 모의(Mock) 계측기 ────────────────────────────────────────────────────
class _MockLCRMeter(BaseLCRMeter):
    """X5R 100 nF MLCC의 DC 바이어스 특성을 시뮬레이션하는 모의 LCR 미터.

    C(V) = C0 / (1 + (|V| / V_knee)^n)  — 일반적인 X5R 직류 바이어스 감소 곡선
    """

    _C0 = 100e-9
    _V_KNEE = 7.0
    _N = 1.9
    _D_BASE = 0.018
    _D_SLOPE = 0.0008

    def __init__(self) -> None:
        super().__init__(resource_name="MOCK::GPIB0::20::INSTR")
        self._dc_bias: float = 0.0
        self._frequency: float = 1000.0
        self._ac_level: float = 1.0

    # ── BaseInstrument 추상 메서드 구현 ───────────────────────────────
    def connect(self) -> None:
        pass

    def disconnect(self) -> None:
        pass

    def identify(self) -> str:
        return "Keysight Technologies,E4980A,MY00000001,A.01.00 (PREVIEW)"

    def configure(
        self,
        frequency: float = 1000.0,
        ac_level: float = 1.0,
        dc_bias: float = 0.0,
        **kwargs,
    ) -> None:
        self._frequency = frequency
        self._ac_level = ac_level
        self._dc_bias = dc_bias

    def measure(self, **kwargs) -> list:
        """X5R 100 nF DC 바이어스 특성을 시뮬레이션한다."""
        if "dc_bias" in kwargs:
            self._dc_bias = float(kwargs["dc_bias"])
        if "frequency" in kwargs:
            self._frequency = float(kwargs["frequency"])

        bias_factor = 1.0 / (1.0 + (abs(self._dc_bias) / self._V_KNEE) ** self._N)
        cp = self._C0 * bias_factor * random.gauss(1.0, 0.002)
        d_val = self._D_BASE + self._D_SLOPE * abs(self._dc_bias)
        raw = f"+{cp:.6e},+{d_val:.6e}"

        return [
            MeasurementResult(
                characteristic=Characteristic.CAPACITANCE,
                value=cp,
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

    # ── BaseLCRMeter 추가 메서드 ──────────────────────────────────────
    def set_frequency(self, frequency: float) -> None:
        self._frequency = frequency

    def set_ac_level(self, level: float) -> None:
        self._ac_level = level

    def set_dc_bias(self, bias: float) -> None:
        self._dc_bias = bias

    def disable_dc_bias(self) -> None:
        self._dc_bias = 0.0


# ── 모의 API 클라이언트 ──────────────────────────────────────────────────
class _MockAPIClient:
    """서버 통신 없이 성공 응답을 반환하는 모의 APIClient.

    LoginDialog.__init__ 내부의 ``APIClient(settings)`` 호출이
    patch("app.ui.login_dialog.APIClient", _MockAPIClient) 에 의해
    이 클래스로 대체된다.
    """

    def __init__(self, settings=None) -> None:
        self._token: str = ""

    def set_token(self, token: str) -> None:
        self._token = token

    def _auth_headers(self) -> dict:
        return {}

    def login(self, username: str, password: str) -> dict:
        """임의 사용자명/비밀번호를 모두 허용한다."""
        return {
            "access_token": "preview.mock.jwt.token",
            "token_type": "bearer",
            "username": username,
        }

    def send_measurements(self, payload: dict) -> dict:
        return {"session_id": 9999, "status": "preview — not sent to server"}

    def get_instruments(self) -> list:
        return []

    def check_server(self) -> bool:
        return True   # 상태바에 "● 서버: 연결됨" 표시


# ── 미리보기 진입점 ──────────────────────────────────────────────────────
def main() -> None:
    app = QApplication(sys.argv)
    # main.py와 동일: 로그아웃 후 로그인 다이얼로그 재표시를 위해 자동 종료 비활성화
    app.setQuitOnLastWindowClosed(False)
    settings = Settings()

    while True:
        # ── 1. LoginDialog: APIClient → _MockAPIClient 교체 ─────────────
        with patch("app.ui.login_dialog.APIClient", _MockAPIClient):
            login_dialog = LoginDialog(settings)
            login_dialog.setWindowTitle("MLCC Data Collector — 로그인  [UI PREVIEW]")
            if login_dialog.exec() != LoginDialog.DialogCode.Accepted:
                break

        # ── 2. 모의 APIClient로 MainWindow 생성 ──────────────────────────
        mock_api = _MockAPIClient()
        mock_api.set_token(login_dialog.token)
        settings.operator = login_dialog.username

        window = MainWindow(
            settings=settings,
            api_client=mock_api,
            username=login_dialog.username,
        )
        window.setWindowTitle(
            "MLCC Data Collector  [UI PREVIEW — 서버·GPIB 미사용]"
        )

        # ── 3. 모의 계측기 인스턴스 생성 ────────────────────────────────
        _mock_instrument = _MockLCRMeter()

        def _inject_instrument_into(page) -> None:
            """측정 페이지에 모의 계측기를 주입하고 페이지 버튼도 패치한다."""
            page.set_instrument(_mock_instrument)

            # 페이지 내 "계측기 연결" 버튼도 mock으로 교체
            try:
                page._instr_connect_btn.clicked.disconnect()
                page._instr_connect_btn.clicked.connect(
                    lambda: page.set_instrument(_mock_instrument)
                )
            except Exception:
                pass

        # ── 4. 카드 클릭 후 페이지 생성 시 모의 계측기 자동 주입 ────────
        # Qt 시그널 연결 순서가 보장된다:
        #   ① _navigate_to_measurement (MainWindow에서 먼저 연결 — 페이지 생성)
        #   ② _inject_on_navigate      (여기서 두 번째로 연결 — 계측기 주입)
        def _inject_on_navigate(characteristic: str, _title: str) -> None:
            current = window._stack.currentWidget()
            if isinstance(current, (MeasurementPage, DCBiasMeasurementPage)):
                _inject_instrument_into(current)

        window._home_page.card_clicked.connect(_inject_on_navigate)

        # ── 5. 상태바 초기 안내 메시지 ──────────────────────────────────
        window.statusBar().showMessage(
            "[PREVIEW MODE]  서버·GPIB 미연결 — X5R 100 nF 시뮬레이션 데이터 사용  |  "
            "카드를 클릭하면 모의 계측기가 자동으로 연결됩니다.",
            0,
        )

        # ── 6. 로컬 이벤트 루프 — main.py와 동일한 창 생명주기 관리 ─────
        loop = QEventLoop()
        window.window_closed.connect(loop.quit)
        window.show()
        loop.exec()

        # 로그아웃이 아니라 창을 직접 닫은 경우 → 미리보기 종료
        if not window.is_logout:
            break

    sys.exit(0)


if __name__ == "__main__":
    main()
