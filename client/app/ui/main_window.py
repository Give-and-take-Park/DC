from pathlib import Path

from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QHBoxLayout, QLabel, QPushButton,
    QStackedWidget, QStatusBar, QApplication,
)
import threading

from PyQt6.QtCore import Qt, QTimer, pyqtSignal, pyqtSlot
from PyQt6.QtGui import QFont, QIcon

from app.config.settings import Settings
from app.core.api_client import APIClient
from app.ui.pages.home_page import HomePage
from app.ui.pages.measurement_page import MeasurementPage
from app.ui.pages.dc_bias_page import DCBiasMeasurementPage


class MainWindow(QMainWindow):
    """메인 윈도우 — 헤더 + QStackedWidget + 상태바"""

    window_closed = pyqtSignal()        # 창이 닫힐 때 main.py 이벤트 루프에 통보
    _server_ok    = pyqtSignal(bool)   # 백그라운드 서버 체크 결과 → UI 갱신용

    def __init__(self, settings: Settings, api_client: APIClient, username: str = ""):
        super().__init__()
        self.settings = settings
        self.api_client = api_client
        self.username = username
        self.is_logout: bool = False   # 로그아웃으로 닫힌 경우 True
        self._measurement_pages: dict[str, int] = {}  # characteristic → stack index

        self.setWindowTitle("RIMS")
        self.setMinimumSize(960, 640)
        self.resize(1200, 760)

        _icon = Path(__file__).parent / "styles" / "icon.ico"
        if _icon.exists():
            self.setWindowIcon(QIcon(str(_icon)))

        self._load_stylesheet()
        self._init_ui()
        self._server_ok.connect(self._apply_server_status)
        self._start_status_timer()

    # ── 스타일시트 ───────────────────────────────────────────────
    def _load_stylesheet(self) -> None:
        qss_path = Path(__file__).parent / "styles" / "clean_light.qss"
        if qss_path.exists():
            QApplication.instance().setStyleSheet(qss_path.read_text(encoding="utf-8"))

    # ── UI 초기화 ────────────────────────────────────────────────
    def _init_ui(self) -> None:
        central = QWidget()
        self.setCentralWidget(central)

        from PyQt6.QtWidgets import QVBoxLayout
        main_layout = QVBoxLayout(central)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # 헤더
        header = self._build_header()
        main_layout.addWidget(header)

        # 콘텐츠 영역 (QStackedWidget)
        self._stack = QStackedWidget()
        main_layout.addWidget(self._stack)

        # HomePage (index 0)
        self._home_page = HomePage()
        self._home_page.card_clicked.connect(self._navigate_to_measurement)
        self._stack.addWidget(self._home_page)

        # 상태바
        self._build_statusbar()

    def _build_header(self) -> QWidget:
        header = QWidget()
        header.setObjectName("header")
        header.setMinimumHeight(72)

        layout = QHBoxLayout(header)
        layout.setContentsMargins(28, 0, 28, 0)
        layout.setSpacing(20)

        # 타이틀 (좌)
        title_label = QLabel(
            "<span style='font-size:35px; font-weight:bold; color:#FFFFFF;'>RIMS</span>"
            "<span style='font-size:20px; font-weight:normal; color:#FFFFFF;'>"
            "&nbsp;&nbsp;Raffaello Inspection &amp; Metrology System</span>"
        )
        title_label.setObjectName("header-title")
        layout.addWidget(title_label)

        layout.addStretch()

        layout.addStretch()

        # 사용자 이름 (우)
        user_label = QLabel(self.username)
        user_label.setObjectName("header-instrument")
        layout.addWidget(user_label)

        # 홈으로 버튼 — 측정 페이지 진입 시에만 표시
        self._home_btn = QPushButton("🏠  홈으로")
        self._home_btn.setObjectName("header-btn")
        self._home_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._home_btn.clicked.connect(self._navigate_home)
        self._home_btn.setVisible(False)
        layout.addWidget(self._home_btn)

        # 로그아웃 버튼 (우)
        logout_btn = QPushButton("로그아웃")
        logout_btn.setObjectName("header-btn")
        logout_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        logout_btn.clicked.connect(self._on_logout)
        layout.addWidget(logout_btn)

        return header

    def _build_statusbar(self) -> None:
        status_bar = QStatusBar()
        self.setStatusBar(status_bar)

        self._server_status_label = QLabel("● 서버: 확인 중")
        self._server_status_label.setStyleSheet("color: #CBD5E1; font-size: 13px;")

        self._gpib_status_label = QLabel("● GPIB: 미연결")
        self._gpib_status_label.setStyleSheet("color: #CBD5E1; font-size: 13px;")

        self._session_label = QLabel("")
        self._session_label.setStyleSheet("color: #94A3B8; font-size: 13px;")

        status_bar.addWidget(self._server_status_label)
        status_bar.addWidget(self._gpib_status_label)
        status_bar.addPermanentWidget(self._session_label)

    # ── 네비게이션 ───────────────────────────────────────────────
    @pyqtSlot(str, str)
    def _navigate_to_measurement(self, characteristic: str, title: str) -> None:
        if characteristic not in self._measurement_pages:
            if characteristic == "DC_BIAS":
                page = DCBiasMeasurementPage(
                    settings=self.settings,
                    api_client=self.api_client,
                )
            else:
                page = MeasurementPage(
                    characteristic=characteristic,
                    title=title,
                    settings=self.settings,
                    api_client=self.api_client,
                )
            page.back_requested.connect(self._navigate_home)
            page.status_message.connect(self.statusBar().showMessage)
            page.instrument_connected.connect(self._on_instrument_connected)
            idx = self._stack.addWidget(page)
            self._measurement_pages[characteristic] = idx

        self._stack.setCurrentIndex(self._measurement_pages[characteristic])
        self._home_btn.setVisible(True)

        # DC-bias 페이지 진입 시 GPIB 자동 스캔
        if characteristic == "DC_BIAS":
            page = self._stack.widget(self._measurement_pages[characteristic])
            QTimer.singleShot(0, page.start_gpib_scan)

    @pyqtSlot()
    def _navigate_home(self) -> None:
        self._stack.setCurrentIndex(0)
        self._home_btn.setVisible(False)

    # ── 계측기 연결 상태 갱신 ────────────────────────────────────
    @pyqtSlot(str)
    def _on_instrument_connected(self, model_name: str) -> None:
        """측정 페이지에서 계측기 연결 성공 시 상태바를 갱신한다."""
        self._gpib_status_label.setText(f"● GPIB: {model_name}")
        self._gpib_status_label.setStyleSheet("color: #4ADE80; font-size: 13px;")

    # ── 창 닫기 이벤트 ───────────────────────────────────────────
    def closeEvent(self, event) -> None:  # type: ignore[override]
        self._status_timer.stop()
        self.window_closed.emit()
        super().closeEvent(event)

    # ── 로그아웃 ─────────────────────────────────────────────────
    def _on_logout(self) -> None:
        self.is_logout = True
        self.close()

    # ── 상태 타이머 ──────────────────────────────────────────────
    def _start_status_timer(self) -> None:
        self._status_timer = QTimer(self)
        self._status_timer.timeout.connect(self._update_server_status)
        self._status_timer.start(15_000)  # 15초마다 체크
        # 초기 확인을 2초 후로 지연 — 페이드인 애니메이션 완료 후 실행
        QTimer.singleShot(2000, self._update_server_status)

    @pyqtSlot()
    def _update_server_status(self) -> None:
        """서버 상태 확인을 백그라운드 스레드에서 실행한다 (UI 스레드 블로킹 방지)."""
        threading.Thread(target=self._check_server_bg, daemon=True).start()

    def _check_server_bg(self) -> None:
        ok = self.api_client.check_server()
        self._server_ok.emit(ok)

    @pyqtSlot(bool)
    def _apply_server_status(self, ok: bool) -> None:
        if ok:
            self._server_status_label.setText("● 서버: 연결됨")
            self._server_status_label.setStyleSheet("color: #4ADE80; font-size: 13px;")
        else:
            self._server_status_label.setText("● 서버: 오프라인")
            self._server_status_label.setStyleSheet("color: #F87171; font-size: 13px;")
