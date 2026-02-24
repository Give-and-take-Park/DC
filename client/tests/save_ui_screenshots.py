#!/usr/bin/env python
"""
UI 스크린샷 일괄 저장 스크립트 (사용자 조작 불필요)

실행:
    cd client
    python tests/save_ui_screenshots.py

저장 위치: client/ui_screenshots/
  01_login_dialog.png
  02_home_page.png
  03_dc_bias_page.png
  04_capacitance_page.png
"""

import random
import sys
from pathlib import Path
from unittest.mock import patch

_CLIENT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_CLIENT_DIR))

from PyQt6.QtWidgets import QApplication

from app.config.settings import Settings
from app.instruments.base import Characteristic, MeasurementResult
from app.instruments.drivers.lcr_meter.base_lcr import BaseLCRMeter
from app.ui.login_dialog import LoginDialog
from app.ui.main_window import MainWindow
from app.ui.pages.dc_bias_page import DCBiasMeasurementPage
from app.ui.pages.measurement_page import MeasurementPage


# ── 모의 계측기 ──────────────────────────────────────────────────────────
class _MockLCRMeter(BaseLCRMeter):
    _C0 = 100e-9
    _V_KNEE = 7.0
    _N = 1.9

    def __init__(self) -> None:
        super().__init__(resource_name="MOCK::GPIB0::20::INSTR")
        self._dc_bias: float = 0.0
        self._frequency: float = 1000.0
        self._ac_level: float = 1.0

    def connect(self) -> None: pass
    def disconnect(self) -> None: pass
    def identify(self) -> str: return "Keysight E4980A (PREVIEW)"

    def configure(self, frequency=1000.0, ac_level=1.0, dc_bias=0.0, **kwargs):
        self._frequency, self._ac_level, self._dc_bias = frequency, ac_level, dc_bias

    def measure(self, **kwargs) -> list:
        if "dc_bias" in kwargs:
            self._dc_bias = float(kwargs["dc_bias"])
        bias_factor = 1.0 / (1.0 + (abs(self._dc_bias) / self._V_KNEE) ** self._N)
        cp = self._C0 * bias_factor * random.gauss(1.0, 0.002)
        d_val = 0.018 + 0.0008 * abs(self._dc_bias)
        raw = f"+{cp:.6e},+{d_val:.6e}"
        return [
            MeasurementResult(Characteristic.CAPACITANCE, cp, "F", raw),
            MeasurementResult(Characteristic.DF, d_val, "", raw),
        ]

    def set_frequency(self, f): self._frequency = f
    def set_ac_level(self, l): self._ac_level = l
    def set_dc_bias(self, v): self._dc_bias = v
    def disable_dc_bias(self): self._dc_bias = 0.0


# ── 모의 API 클라이언트 ──────────────────────────────────────────────────
class _MockAPIClient:
    def __init__(self, settings=None): self._token = ""
    def set_token(self, t): self._token = t
    def _auth_headers(self): return {}
    def login(self, u, p): return {"access_token": "preview.mock", "token_type": "bearer", "username": u}
    def send_measurements(self, p): return {"session_id": 9999}
    def get_instruments(self): return []
    def check_server(self): return True


# ── 스크린샷 헬퍼 ───────────────────────────────────────────────────────
def _grab(widget, output_dir: Path, name: str) -> Path:
    """위젯을 렌더링하고 PNG로 저장한다."""
    widget.show()
    QApplication.processEvents()
    QApplication.processEvents()
    pixmap = widget.grab()
    path = output_dir / f"{name}.png"
    pixmap.save(str(path))
    print(f"  저장: {path.name}  ({pixmap.width()}×{pixmap.height()})")
    return path


# ── 메인 ────────────────────────────────────────────────────────────────
def main() -> None:
    app = QApplication(sys.argv)

    output_dir = _CLIENT_DIR / "ui_screenshots"
    output_dir.mkdir(exist_ok=True)
    print(f"스크린샷 저장 디렉터리: {output_dir}\n")

    saved: list[Path] = []
    settings = Settings()

    # ── 1. 로그인 다이얼로그 ─────────────────────────────────────────
    print("[1/4] 로그인 다이얼로그")
    with patch("app.ui.login_dialog.APIClient", _MockAPIClient):
        login = LoginDialog(settings)
    saved.append(_grab(login, output_dir, "01_login_dialog"))
    login.hide()

    # ── 2. 홈 페이지 (카드 그리드) ──────────────────────────────────
    print("[2/4] 홈 페이지")
    mock_api = _MockAPIClient()
    mock_api.set_token("preview.mock.jwt.token")
    settings.operator = "preview"

    window = MainWindow(settings=settings, api_client=mock_api, username="preview")
    window.resize(1200, 760)
    saved.append(_grab(window, output_dir, "02_home_page"))

    mock_instrument = _MockLCRMeter()

    # ── 3. DC Bias 측정 페이지 ───────────────────────────────────────
    print("[3/4] DC Bias 측정 페이지")
    window._navigate_to_measurement("DC_BIAS", "DC 바이어스")
    dc_page = window._stack.currentWidget()
    if isinstance(dc_page, DCBiasMeasurementPage):
        dc_page.set_instrument(mock_instrument)
    QApplication.processEvents()
    saved.append(_grab(window, output_dir, "03_dc_bias_page"))

    # ── 4. 일반 측정 페이지 (정전용량) ──────────────────────────────
    print("[4/4] 정전용량 측정 페이지")
    window._navigate_home()
    window._navigate_to_measurement("CAPACITANCE", "정전용량")
    cap_page = window._stack.currentWidget()
    if isinstance(cap_page, MeasurementPage):
        cap_page.set_instrument(mock_instrument)
    QApplication.processEvents()
    saved.append(_grab(window, output_dir, "04_capacitance_page"))

    window.hide()
    print(f"\n완료: {len(saved)}개 이미지가 {output_dir} 에 저장되었습니다.")
    app.quit()


if __name__ == "__main__":
    main()
