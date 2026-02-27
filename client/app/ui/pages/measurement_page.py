from datetime import datetime
from typing import Optional, List

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QSplitter, QTableWidget, QTableWidgetItem, QGroupBox,
    QDoubleSpinBox, QFormLayout, QComboBox, QHeaderView,
    QGraphicsDropShadowEffect, QSizePolicy,
)
from PyQt6.QtCore import Qt, pyqtSignal, QThread, pyqtSlot, QObject
from PyQt6.QtGui import QFont, QColor

from app.config.settings import Settings
from app.core.api_client import APIClient
from app.core.measurement_engine import MeasurementEngine
from app.instruments.base import BaseInstrument


class _MeasurementWorker(QObject):
    """별도 QThread에서 측정을 실행하는 워커."""

    finished = pyqtSignal(list)   # List[MeasurementResult]
    error = pyqtSignal(str)

    def __init__(self, engine: MeasurementEngine, instrument: BaseInstrument,
                 client_id: str, session_name: Optional[str], measure_kwargs: dict):
        super().__init__()
        self._engine = engine
        self._instrument = instrument
        self._client_id = client_id
        self._session_name = session_name
        self._kwargs = measure_kwargs

    @pyqtSlot()
    def run(self) -> None:
        try:
            results = self._instrument.measure(**self._kwargs)
            self.finished.emit(results)
        except Exception as exc:
            self.error.emit(str(exc))


class MeasurementPage(QWidget):
    """측정 조건 설정 + 실시간 결과 + 이력 테이블을 포함한 측정 화면."""

    back_requested = pyqtSignal()
    status_message = pyqtSignal(str)
    instrument_connected = pyqtSignal(str)   # (model_name) → MainWindow 상태바 갱신

    # 테이블 열 순서
    _COLS = ["시간", "값", "단위", "주파수(Hz)", "DC Bias(V)", "상태"]

    def __init__(self, characteristic: str, title: str,
                 settings: Settings, api_client: APIClient, parent=None):
        super().__init__(parent)
        self.characteristic = characteristic
        self.title = title
        self.settings = settings
        self.api_client = api_client
        self._engine = MeasurementEngine(settings)
        self._instrument: Optional[BaseInstrument] = None
        self._thread: Optional[QThread] = None
        self._worker: Optional[_MeasurementWorker] = None

        self._init_ui()

    # ── UI 구성 ────────────────────────────────────────────────
    def _init_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # 페이지 헤더
        header = self._build_page_header()
        root.addWidget(header)

        # 메인 스플리터 (수직)
        v_splitter = QSplitter(Qt.Orientation.Vertical)
        v_splitter.setHandleWidth(1)

        # 상단: 조건 패널 + 실시간 패널 (수평)
        top_widget = QWidget()
        top_layout = QHBoxLayout(top_widget)
        top_layout.setContentsMargins(16, 16, 16, 16)
        top_layout.setSpacing(16)

        top_layout.addWidget(self._build_condition_panel(), 0)
        top_layout.addWidget(self._build_realtime_panel(), 1)

        v_splitter.addWidget(top_widget)
        v_splitter.addWidget(self._build_history_panel())
        v_splitter.setSizes([360, 260])
        v_splitter.setStretchFactor(0, 2)   # 측정 조건+실시간 패널: 창 확장 시 2배 비율
        v_splitter.setStretchFactor(1, 1)   # 이력 패널: 창 확장 시 1배 비율

        root.addWidget(v_splitter)

    def _build_page_header(self) -> QWidget:
        header = QWidget()
        header.setFixedHeight(48)
        header.setStyleSheet("background: #F4F6F9; border-bottom: 1px solid #E2E8F0;")
        layout = QHBoxLayout(header)
        layout.setContentsMargins(16, 0, 16, 0)

        back_btn = QPushButton("← 홈으로")
        back_btn.setObjectName("secondary")
        back_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        back_btn.clicked.connect(self.back_requested)

        title_label = QLabel(self.title)
        title_font = QFont("Segoe UI", 14)
        title_font.setBold(True)
        title_label.setFont(title_font)
        title_label.setStyleSheet("color: #1E3A5F;")

        layout.addWidget(back_btn)
        layout.addSpacing(16)
        layout.addWidget(title_label)
        layout.addStretch()
        return header

    def _build_condition_panel(self) -> QGroupBox:
        box = QGroupBox("측정 조건")
        box.setFixedWidth(260)   # 창 크기 변경 시에도 너비 고정
        form = QFormLayout(box)
        form.setSpacing(12)
        form.setContentsMargins(16, 24, 16, 16)

        # ── 계측기 ──────────────────────────────────────────────
        self._instr_status_label = QLabel("미연결")
        self._instr_status_label.setStyleSheet("color: #94A3B8; font-size: 12px;")
        form.addRow("계측기:", self._instr_status_label)

        self._instr_connect_btn = QPushButton("계측기 연결")
        self._instr_connect_btn.setObjectName("secondary")
        self._instr_connect_btn.setMinimumHeight(34)
        self._instr_connect_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._instr_connect_btn.clicked.connect(self._on_instrument_connect)
        form.addRow(self._instr_connect_btn)

        form.addRow(QLabel(""))  # 여백

        # ── 측정 조건 ────────────────────────────────────────────
        self._freq_spin = QDoubleSpinBox()
        self._freq_spin.setRange(20.0, 2_000_000.0)
        self._freq_spin.setValue(1000.0)
        self._freq_spin.setSuffix(" Hz")
        self._freq_spin.setDecimals(1)

        self._ac_spin = QDoubleSpinBox()
        self._ac_spin.setRange(0.005, 2.0)
        self._ac_spin.setValue(1.0)
        self._ac_spin.setSuffix(" V")
        self._ac_spin.setDecimals(3)

        self._bias_spin = QDoubleSpinBox()
        self._bias_spin.setRange(0.0, 40.0)
        self._bias_spin.setValue(0.0)
        self._bias_spin.setSuffix(" V")
        self._bias_spin.setDecimals(2)

        form.addRow("주파수:", self._freq_spin)
        form.addRow("AC Level:", self._ac_spin)
        form.addRow("DC Bias:", self._bias_spin)

        # ── 버튼 ─────────────────────────────────────────────────
        self._measure_btn = QPushButton("측정 시작")
        self._measure_btn.setObjectName("primary")
        self._measure_btn.setMinimumHeight(40)
        self._measure_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._measure_btn.clicked.connect(self._on_measure)

        self._send_btn = QPushButton("서버 전송")
        self._send_btn.setObjectName("secondary")
        self._send_btn.setMinimumHeight(36)
        self._send_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._send_btn.setEnabled(False)
        self._send_btn.clicked.connect(self._on_send)

        form.addRow(self._measure_btn)
        form.addRow(self._send_btn)
        return box

    def _build_realtime_panel(self) -> QWidget:
        panel = QWidget()
        panel.setObjectName("card")
        panel.setStyleSheet("QWidget#card { background: white; border-radius: 8px; border: 1px solid #E2E8F0; }")

        shadow = QGraphicsDropShadowEffect()
        shadow.setBlurRadius(12)
        shadow.setOffset(0, 2)
        shadow.setColor(QColor(0, 0, 0, 25))
        panel.setGraphicsEffect(shadow)

        layout = QVBoxLayout(panel)
        layout.setContentsMargins(32, 32, 32, 32)
        layout.setSpacing(8)

        label = QLabel("현재 측정값")
        label.setObjectName("section-title")
        layout.addWidget(label)

        self._value_label = QLabel("—")
        value_font = QFont("Segoe UI", 42)
        value_font.setBold(True)
        self._value_label.setFont(value_font)
        self._value_label.setStyleSheet("color: #1E3A5F;")
        self._value_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self._unit_label = QLabel("")
        self._unit_label.setObjectName("value-unit")
        self._unit_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self._char_label = QLabel(self.title)
        self._char_label.setStyleSheet("color: #94A3B8; font-size: 13px;")
        self._char_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        layout.addStretch()
        layout.addWidget(self._value_label)
        layout.addWidget(self._unit_label)
        layout.addWidget(self._char_label)
        layout.addStretch()

        self._measure_status_label = QLabel("")
        self._measure_status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._measure_status_label.setStyleSheet("color: #64748B; font-size: 11px;")
        layout.addWidget(self._measure_status_label)

        return panel

    def _build_history_panel(self) -> QWidget:
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(16, 8, 16, 16)
        layout.setSpacing(8)

        header_label = QLabel("측정 이력")
        header_font = QFont("Segoe UI", 11)
        header_font.setBold(True)
        header_label.setFont(header_font)
        header_label.setStyleSheet("color: #64748B;")
        layout.addWidget(header_label)

        self._table = QTableWidget(0, len(self._COLS))
        self._table.setHorizontalHeaderLabels(self._COLS)
        self._table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self._table.verticalHeader().setVisible(False)
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._table.setAlternatingRowColors(True)

        layout.addWidget(self._table)
        return panel

    # ── 이벤트 핸들러 ───────────────────────────────────────────
    def _on_measure(self) -> None:
        if self._instrument is None:
            self._measure_status_label.setText("계측기가 연결되지 않았습니다.")
            self._measure_status_label.setStyleSheet("color: #DC2626; font-size: 11px;")
            return

        if self._thread and self._thread.isRunning():
            return

        self._measure_btn.setEnabled(False)
        self._measure_btn.setText("측정 중...")
        self._send_btn.setEnabled(False)
        self._measure_status_label.setText("측정 실행 중…")
        self._measure_status_label.setStyleSheet("color: #2563EB; font-size: 11px;")

        kwargs = {
            "frequency": self._freq_spin.value(),
            "ac_level": self._ac_spin.value(),
            "dc_bias": self._bias_spin.value(),
        }

        self._thread = QThread()
        self._worker = _MeasurementWorker(
            self._engine, self._instrument,
            "gui-client", None, kwargs,
        )
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.run)
        self._worker.finished.connect(self._on_measure_done)
        self._worker.error.connect(self._on_measure_error)
        self._worker.finished.connect(self._thread.quit)
        self._worker.error.connect(self._thread.quit)
        self._thread.start()

    @pyqtSlot(list)
    def _on_measure_done(self, results: list) -> None:
        self._last_results = results
        if results:
            r = results[0]
            self._value_label.setText(self._format_value(r.value))
            self._unit_label.setText(r.unit)
            self._measure_status_label.setText(
                f"측정 완료 — {datetime.now().strftime('%H:%M:%S')}"
            )
            self._measure_status_label.setStyleSheet("color: #16A34A; font-size: 11px;")
            self._add_history_row(results)
            self._send_btn.setEnabled(True)

        self._measure_btn.setEnabled(True)
        self._measure_btn.setText("측정 시작")

    @pyqtSlot(str)
    def _on_measure_error(self, msg: str) -> None:
        self._measure_status_label.setText(f"오류: {msg}")
        self._measure_status_label.setStyleSheet("color: #DC2626; font-size: 11px;")
        self._measure_btn.setEnabled(True)
        self._measure_btn.setText("측정 시작")

    def _on_send(self) -> None:
        if not hasattr(self, "_last_results") or not self._last_results:
            return
        try:
            payload = self._engine._build_payload(
                self._instrument,
                "gui-client",
                None,
                self._last_results,
            )
            payload["operator"] = self.settings.operator
            self.api_client.send_measurements(payload)
            self._measure_status_label.setText("서버 전송 완료")
            self._measure_status_label.setStyleSheet("color: #16A34A; font-size: 11px;")
            self.status_message.emit("측정 데이터 서버 전송 완료")
        except Exception as exc:
            self._measure_status_label.setText(f"전송 실패: {exc}")
            self._measure_status_label.setStyleSheet("color: #DC2626; font-size: 11px;")

    # ── 헬퍼 ────────────────────────────────────────────────────
    def _on_instrument_connect(self) -> None:
        """계측기 연결 버튼 핸들러."""
        try:
            from app.ui.dialogs.instrument_config import InstrumentConfigDialog
            dialog = InstrumentConfigDialog(parent=self)
            if dialog.exec():
                cfg = dialog.get_config()
                engine = MeasurementEngine(self.settings)
                instrument = engine.load_instrument(cfg["model"], cfg["resource_name"])
                self.set_instrument(instrument)
        except Exception as exc:
            self._measure_status_label.setText(f"계측기 연결 실패: {exc}")
            self._measure_status_label.setStyleSheet("color: #DC2626; font-size: 11px;")

    def set_instrument(self, instrument: BaseInstrument) -> None:
        model = type(instrument).__name__
        self._instrument = instrument
        self._instr_status_label.setText(f"{model} ●")
        self._instr_status_label.setStyleSheet("color: #4ADE80; font-size: 12px;")
        self.instrument_connected.emit(model)

    def _add_history_row(self, results: list) -> None:
        timestamp = datetime.now().strftime("%H:%M:%S")
        row = self._table.rowCount()
        self._table.insertRow(row)
        primary = results[0]
        values = [
            timestamp,
            self._format_value(primary.value),
            primary.unit,
            f"{self._freq_spin.value():.1f}",
            f"{self._bias_spin.value():.2f}",
            "완료",
        ]
        for col, val in enumerate(values):
            item = QTableWidgetItem(val)
            item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self._table.setItem(row, col, item)
        self._table.scrollToBottom()

    @staticmethod
    def _format_value(value: float) -> str:
        abs_val = abs(value)
        if abs_val == 0:
            return "0"
        if abs_val >= 1e6:
            return f"{value / 1e6:.4f} M"
        if abs_val >= 1e3:
            return f"{value / 1e3:.4f} k"
        if abs_val >= 1:
            return f"{value:.6f}"
        if abs_val >= 1e-3:
            return f"{value * 1e3:.4f} m"
        if abs_val >= 1e-6:
            return f"{value * 1e6:.4f} µ"
        if abs_val >= 1e-9:
            return f"{value * 1e9:.4f} n"
        return f"{value * 1e12:.4f} p"
