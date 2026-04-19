#!/usr/bin/env python
"""
UI 미리보기 실행기 — 서버·GPIB 없이 클라이언트 GUI를 확인합니다.

실행 방법:
    cd client
    python tests/run_ui_preview.py

동작 요약:
    - LoginDialog : Knox ID 입력 후 즉시 진입 (서버 미사용)
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
from PyQt6.QtCore import QPropertyAnimation
from PyQt6.QtWidgets import QApplication

from app.config.settings import Settings
from app.instruments.base import Characteristic, MeasurementResult
from app.instruments.drivers.lcr_meter.base_lcr import BaseLCRMeter
from app.ui.login_dialog import LoginDialog
from app.ui.main_window import MainWindow
from app.ui.pages.dc_bias_page import DCBiasMeasurementPage
from app.ui.pages.measurement_page import MeasurementPage
from app.ui.pages.optical_page import OpticalAnalysisPage


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

    def log_access(self, username: str) -> None:
        """접속 로그 전송 모의 — 아무 작업도 하지 않는다."""
        pass

    def send_measurements(self, payload: dict) -> dict:
        return {"session_id": 9999, "status": "preview — not sent to server"}

    def upload_optical(self, file_path: str, **kwargs) -> dict:
        """광학 이미지 업로드 모의 — 실제 전송 없이 성공 응답 반환."""
        from pathlib import Path
        return {
            "id": 1,
            "original_filename": Path(file_path).name,
            "file_size": 0,
            "uploaded_at": "2026-01-01T00:00:00Z",
            "status": "preview — not sent to server",
        }

    def get_instruments(self) -> list:
        return []

    def check_server(self) -> bool:
        return True   # 상태바에 "● 서버: 연결됨" 표시


# ── 미리보기 진입점 ──────────────────────────────────────────────────────
def _show_login_preview(settings: Settings, geometry=None) -> None:
    """미리보기용 로그인 다이얼로그를 표시하고 MainWindow로 페이드 전환한다."""
    app = QApplication.instance()
    mock_api = _MockAPIClient()

    with patch("app.ui.login_dialog.APIClient", _MockAPIClient):
        dialog = LoginDialog(settings)
    app._preview_dialog = dialog  # GC 방지
    dialog.setWindowTitle("RIMS  [UI PREVIEW]")

    if geometry is not None:
        dialog.setGeometry(geometry)

    def _on_login_ready(username: str) -> None:
        settings.operator = username
        _mock_instrument = _MockLCRMeter()

        window = MainWindow(settings, api_client=mock_api, username=username)
        app._preview_window = window  # GC 방지
        window.setWindowTitle("RIMS  [UI PREVIEW — 서버·GPIB 미사용]")
        window.setGeometry(dialog.geometry())

        # LoginDialog 페이드아웃(300ms)과 동시에 크로스페이드
        window.setWindowOpacity(0.0)
        window.show()
        fade_in = QPropertyAnimation(window, b"windowOpacity", window)
        fade_in.setDuration(300)
        fade_in.setStartValue(0.0)
        fade_in.setEndValue(1.0)
        fade_in.start()
        # dialog.hide()는 dialog 자체 fade 완료 후 호출됨

        def _inject_instrument_into(page) -> None:
            page.set_instrument(_mock_instrument)
            try:
                page._instr_connect_btn.clicked.disconnect()
                page._instr_connect_btn.clicked.connect(
                    lambda: page.set_instrument(_mock_instrument)
                )
            except Exception:
                pass

        def _inject_on_navigate(characteristic: str, _title: str) -> None:
            current = window._stack.currentWidget()
            if isinstance(current, (MeasurementPage, DCBiasMeasurementPage)):
                _inject_instrument_into(current)
            # OpticalAnalysisPage는 계측기 불필요 — 별도 주입 없음

        window._home_page.card_clicked.connect(_inject_on_navigate)

        window.statusBar().showMessage(
            "[PREVIEW MODE]  서버·GPIB 미연결 — X5R 100 nF 시뮬레이션 데이터 사용  |  "
            "카드를 클릭하면 모의 계측기가 자동으로 연결됩니다.",
            0,
        )

        def _on_closed() -> None:
            if window.is_logout:
                _show_login_preview(settings, geometry=window.geometry())
            else:
                QApplication.instance().quit()

        window.window_closed.connect(_on_closed)

    dialog.login_ready.connect(_on_login_ready)
    dialog.rejected.connect(QApplication.instance().quit)

    # 로그인 다이얼로그 페이드인
    dialog.setWindowOpacity(0.0)
    dialog.show()
    fade_in_dlg = QPropertyAnimation(dialog, b"windowOpacity", dialog)
    fade_in_dlg.setDuration(280)
    fade_in_dlg.setStartValue(0.0)
    fade_in_dlg.setEndValue(1.0)
    fade_in_dlg.start()


def main() -> None:
    app = QApplication(sys.argv)
    # 로그아웃 후 로그인 다이얼로그 재표시를 위해 자동 종료 비활성화
    app.setQuitOnLastWindowClosed(False)
    settings = Settings()

    _show_login_preview(settings)
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
