"""DC Bias 특성 측정 페이지

레이아웃:
┌─────────────────────┬──────────────────────────────────────────┐
│ 측정 조건 (280px)   │  측정 결과 테이블                        │
│                     │                                          │
│ 주파수: 1000 Hz     │  인가전압(V) │ 1차측정(F) │ 2차측정(F)  │
│ AC Level: 1.0 V     │  0.0         │ 100.23 nF  │ 99.87 nF   │
│ 시작전압: 0.0 V     │  1.0         │  98.45 nF  │ 98.12 nF   │
│ 종료전압: 5.0 V     │  ...         │  ...       │ ...        │
│ 전압스텝: 1.0 V     │                                          │
│ 지연시간: 100 ms    │                                          │
│                     │                                          │
│ 측정 횟수: 2회      │                                          │
│                     │                                          │
│ [측정 시작]         │                                          │
│ [중지]              │                                          │
│ [초기화]            │                                          │
│ [CSV 내보내기]      │                                          │
│                     │                                          │
│ [====     ] 3/6     │                                          │
└─────────────────────┴──────────────────────────────────────────┘
"""

import csv
import time
from pathlib import Path
from typing import List, Optional

from PyQt6.QtCore import QObject, Qt, QThread, pyqtSignal, pyqtSlot
from PyQt6.QtGui import QColor, QFont, QKeySequence
from PyQt6.QtWidgets import (
    QApplication,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSpinBox,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.config.settings import Settings
from app.core.api_client import APIClient
from app.core.measurement_engine import MeasurementEngine
from app.instruments.base import BaseInstrument
from app.instruments.drivers.lcr_meter.base_lcr import BaseLCRMeter


# ── 전압 포인트 계산 (numpy 미사용) ─────────────────────────────
def _compute_voltage_points(start_v: float, end_v: float, step_v: float) -> List[float]:
    """start_v → end_v 사이를 step_v 간격으로 나눈 전압 목록 반환."""
    if step_v <= 0:
        return [start_v]
    points: List[float] = []
    v = start_v
    # 부동소수점 오차 허용(스텝의 백만분의 일)
    tolerance = step_v * 1e-6
    while v <= end_v + tolerance:
        points.append(round(v, 6))
        v = round(v + step_v, 6)
    return points


def _fmt_cap(value_f: float) -> str:
    """정전용량 값을 읽기 좋은 단위 문자열로 변환."""
    if value_f != value_f:          # NaN
        return "N/A"
    abs_v = abs(value_f)
    if abs_v >= 1e-3:
        return f"{value_f * 1e3:.4f} mF"
    if abs_v >= 1e-6:
        return f"{value_f * 1e6:.4f} µF"
    if abs_v >= 1e-9:
        return f"{value_f * 1e9:.4f} nF"
    return f"{value_f * 1e12:.4f} pF"


# ── 측정 워커 ────────────────────────────────────────────────────
class _SweepWorker(QObject):
    """DC Bias 전압 스윕을 별도 QThread에서 실행하는 워커."""

    row_done = pyqtSignal(int, float, float)   # (row_index, voltage_V, capacitance_F)
    finished = pyqtSignal()
    error = pyqtSignal(str)

    def __init__(
        self,
        instrument: BaseInstrument,
        voltage_points: List[float],
        frequency: float,
        ac_level: float,
        delay_ms: int,
    ):
        super().__init__()
        self._instrument = instrument
        self._voltage_points = voltage_points
        self._frequency = frequency
        self._ac_level = ac_level
        self._delay_ms = delay_ms
        self._running = True

    def stop(self) -> None:
        self._running = False

    @pyqtSlot()
    def run(self) -> None:
        try:
            # ── 1. 측정 함수·주파수·AC 레벨·DC 바이어스 활성화 ──────
            # configure() 내부에서 아래 GPIB 커맨드가 순서대로 전송됨:
            #   FUNC:IMP:TYPE CPRP  → Cp-Rp 측정 모드
            #   FREQ <freq>         → 측정 주파수
            #   VOLT <ac_level>     → AC 신호 레벨
            #   BIAS:VOLT 0         → 초기 DC 바이어스 0 V
            #   BIAS:STATE ON       → DC 바이어스 출력 활성화 (이 명령이 핵심)
            self._instrument.configure(
                frequency=self._frequency,
                ac_level=self._ac_level,
                dc_bias=0.0,            # 스윕 시작 전 0 V 에서 activate
            )

            # ── 2. 전압 포인트별 측정 루프 ───────────────────────────
            for idx, voltage in enumerate(self._voltage_points):
                if not self._running:
                    break

                # DC 바이어스 전압 인가 (BIAS:STATE는 이미 ON)
                self._instrument.set_dc_bias(voltage)

                # 지연: 계측기 내부 측정 버퍼가 새 바이어스 조건으로
                # 갱신될 때까지 대기 (최소 1 측정 주기 이상이어야 함)
                if self._delay_ms > 0:
                    time.sleep(self._delay_ms / 1000.0)

                # 최신 측정값 수집 (FETC? — 연속 트리거 모드)
                results = self._instrument.measure()
                capacitance = next(
                    (r.value for r in results if r.characteristic.value == "capacitance"),
                    float("nan"),
                )

                self.row_done.emit(idx, voltage, capacitance)

            self.finished.emit()

        except Exception as exc:
            self.error.emit(str(exc))

        finally:
            # ── 3. 스윕 종료·중단 공통 — DC 바이어스 해제 ─────────
            # 정상 완료, 사용자 중지, 예외 발생 모두 여기서 처리
            # DUT 보호를 위해 반드시 0 V 복귀 후 BIAS:STATE OFF
            try:
                if isinstance(self._instrument, BaseLCRMeter):
                    self._instrument.disable_dc_bias()
            except Exception:
                pass  # 정리 실패는 무시 (이미 예외 처리 완료)


# ── 복사 지원 테이블 ─────────────────────────────────────────────
class _CopyableTable(QTableWidget):
    """마우스 드래그·Shift+Click·Ctrl+Click으로 셀 범위 선택 후
    Ctrl+C로 클립보드에 탭 구분 텍스트(Excel 호환)를 복사하는 테이블."""

    def keyPressEvent(self, event) -> None:  # type: ignore[override]
        if event.matches(QKeySequence.StandardKey.Copy):
            self._copy_selection()
        else:
            super().keyPressEvent(event)

    def _copy_selection(self) -> None:
        ranges = self.selectedRanges()
        if not ranges:
            return
        min_row = min(r.topRow() for r in ranges)
        max_row = max(r.bottomRow() for r in ranges)
        min_col = min(r.leftColumn() for r in ranges)
        max_col = max(r.rightColumn() for r in ranges)

        lines: list[str] = []
        for row in range(min_row, max_row + 1):
            cells: list[str] = []
            for col in range(min_col, max_col + 1):
                item = self.item(row, col)
                cells.append(item.text() if item else "")
            lines.append("\t".join(cells))
        QApplication.clipboard().setText("\n".join(lines))


# ── DC Bias 측정 페이지 ──────────────────────────────────────────
class DCBiasMeasurementPage(QWidget):
    """DC Bias 전압 스윕 측정 전용 페이지."""

    back_requested = pyqtSignal()
    status_message = pyqtSignal(str)
    instrument_connected = pyqtSignal(str)   # (model_name) → MainWindow 상태바 갱신

    def __init__(
        self,
        settings: Settings,
        api_client: APIClient,
        parent: Optional[QWidget] = None,
    ):
        super().__init__(parent)
        self.settings = settings
        self.api_client = api_client
        self._instrument: Optional[BaseInstrument] = None
        self._thread: Optional[QThread] = None
        self._worker: Optional[_SweepWorker] = None
        self._sweep_count: int = 0          # 완료된 스윕 횟수
        self._voltage_points: List[float] = []

        self._init_ui()

    # ── UI 구성 ─────────────────────────────────────────────────
    def _init_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        root.addWidget(self._build_page_header())

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setHandleWidth(1)
        splitter.addWidget(self._build_condition_panel())
        splitter.addWidget(self._build_result_panel())
        splitter.setSizes([300, 900])
        splitter.setStretchFactor(0, 0)   # 조건 패널: 사용자 드래그만으로 조절
        splitter.setStretchFactor(1, 1)   # 결과 패널: 창 확장 시 자동으로 늘어남

        root.addWidget(splitter)

    # ── 페이지 헤더 ─────────────────────────────────────────────
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

        title = QLabel("DC Bias 특성 측정")
        title_font = QFont("Segoe UI", 14)
        title_font.setBold(True)
        title.setFont(title_font)
        title.setStyleSheet("color: #1E3A5F;")

        self._instr_label = QLabel("계측기: 미연결")
        self._instr_label.setStyleSheet("color: #94A3B8; font-size: 12px;")

        layout.addWidget(back_btn)
        layout.addSpacing(16)
        layout.addWidget(title)
        layout.addStretch()
        layout.addWidget(self._instr_label)
        return header

    # ── 왼쪽: 조건 패널 ─────────────────────────────────────────
    def _build_condition_panel(self) -> QWidget:
        container = QWidget()
        container.setObjectName("dc-condition-panel")
        container.setFixedWidth(300)   # 창 크기 변경 시에도 너비 고정
        # 셀렉터 없는 인라인 스타일은 자식 QPushButton까지 background: white 를
        # 덮어쓰므로 반드시 objectName 스코프 셀렉터를 사용한다
        container.setStyleSheet(
            "QWidget#dc-condition-panel { background: #FFFFFF; border-right: 1px solid #E2E8F0; }"
        )

        # ── 메인 레이아웃: 스크롤 영역(상단) + 고정 버튼(하단) ──
        main_layout = QVBoxLayout(container)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # ── 스크롤 영역 (계측기 + 측정 조건 + 상태) ─────────────
        scroll_content = QWidget()
        inner = QVBoxLayout(scroll_content)
        inner.setContentsMargins(12, 12, 12, 8)
        inner.setSpacing(8)

        # 계측기 그룹
        instr_box = QGroupBox("계측기")
        instr_form = QFormLayout(instr_box)
        instr_form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        instr_form.setVerticalSpacing(10)
        instr_form.setHorizontalSpacing(12)
        instr_form.setContentsMargins(12, 18, 12, 10)

        self._instr_status_label = QLabel("미연결")
        self._instr_status_label.setStyleSheet("color: #94A3B8; font-size: 12px;")
        instr_form.addRow("상태:", self._instr_status_label)

        self._instr_connect_btn = QPushButton("계측기 연결")
        self._instr_connect_btn.setObjectName("secondary")
        self._instr_connect_btn.setMinimumHeight(34)
        self._instr_connect_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._instr_connect_btn.clicked.connect(self._on_instrument_connect)
        instr_form.addRow(self._instr_connect_btn)

        inner.addWidget(instr_box)

        # 측정 조건 그룹
        cond_box = QGroupBox("측정 조건")
        form = QFormLayout(cond_box)
        # AllNonFixedFieldsGrow: 스핀박스가 패널 잔여 너비를 채워 레이블·입력칸 간격 확보
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        form.setVerticalSpacing(10)
        form.setHorizontalSpacing(12)
        form.setContentsMargins(12, 20, 12, 12)

        self._freq_spin = QDoubleSpinBox()
        self._freq_spin.setRange(20.0, 2_000_000.0)
        self._freq_spin.setValue(1_000.0)
        self._freq_spin.setSuffix(" Hz")
        self._freq_spin.setDecimals(1)

        self._ac_spin = QDoubleSpinBox()
        self._ac_spin.setRange(0.005, 2.0)
        self._ac_spin.setValue(1.0)
        self._ac_spin.setSuffix(" V")
        self._ac_spin.setDecimals(3)

        self._start_spin = QDoubleSpinBox()
        self._start_spin.setRange(-40.0, 40.0)
        self._start_spin.setValue(0.0)
        self._start_spin.setSuffix(" V")
        self._start_spin.setDecimals(2)

        self._end_spin = QDoubleSpinBox()
        self._end_spin.setRange(-40.0, 40.0)
        self._end_spin.setValue(5.0)
        self._end_spin.setSuffix(" V")
        self._end_spin.setDecimals(2)

        self._step_spin = QDoubleSpinBox()
        self._step_spin.setRange(0.01, 10.0)
        self._step_spin.setValue(1.0)
        self._step_spin.setSuffix(" V")
        self._step_spin.setDecimals(2)

        self._delay_spin = QSpinBox()
        self._delay_spin.setRange(0, 5_000)
        self._delay_spin.setValue(100)
        self._delay_spin.setSuffix(" ms")

        form.addRow("주파수:", self._freq_spin)
        form.addRow("AC Level:", self._ac_spin)
        form.addRow("시작 전압:", self._start_spin)
        form.addRow("종료 전압:", self._end_spin)
        form.addRow("전압 스텝:", self._step_spin)
        form.addRow("지연 시간:", self._delay_spin)

        inner.addWidget(cond_box)

        # 측정 횟수 + 진행 + 상태
        self._count_label = QLabel("측정 횟수: 0회")
        self._count_label.setStyleSheet("color: #64748B; font-size: 12px;")
        inner.addWidget(self._count_label)

        self._progress_bar = QProgressBar()
        self._progress_bar.setRange(0, 100)
        self._progress_bar.setValue(0)
        self._progress_bar.setTextVisible(True)
        self._progress_bar.setFormat("%v / %m 포인트")
        self._progress_bar.setFixedHeight(18)
        self._progress_bar.hide()
        inner.addWidget(self._progress_bar)

        self._status_label = QLabel("")
        self._status_label.setStyleSheet("color: #64748B; font-size: 11px;")
        self._status_label.setWordWrap(True)
        inner.addWidget(self._status_label)

        inner.addStretch()

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setWidget(scroll_content)
        main_layout.addWidget(scroll, 1)

        # ── 고정 버튼 섹션 (항상 보임) ──────────────────────────
        btn_widget = QWidget()
        btn_widget.setObjectName("dc-btn-panel")
        btn_widget.setStyleSheet(
            "QWidget#dc-btn-panel { background: #FFFFFF; border-top: 1px solid #E2E8F0; }"
        )
        btn_layout = QVBoxLayout(btn_widget)
        btn_layout.setContentsMargins(16, 12, 16, 16)
        btn_layout.setSpacing(8)

        self._start_btn = QPushButton("▶  측정 시작")
        self._start_btn.setObjectName("dc-primary")
        self._start_btn.setMinimumHeight(40)
        self._start_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._start_btn.clicked.connect(self._on_start)

        self._stop_btn = QPushButton("■  중지")
        self._stop_btn.setObjectName("dc-secondary")
        self._stop_btn.setMinimumHeight(36)
        self._stop_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._stop_btn.setEnabled(False)
        self._stop_btn.clicked.connect(self._on_stop)

        self._clear_btn = QPushButton("초기화")
        self._clear_btn.setObjectName("dc-secondary")
        self._clear_btn.setMinimumHeight(36)
        self._clear_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._clear_btn.clicked.connect(self._on_clear)

        self._export_btn = QPushButton("CSV 내보내기")
        self._export_btn.setObjectName("dc-secondary")
        self._export_btn.setMinimumHeight(36)
        self._export_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._export_btn.setEnabled(False)
        self._export_btn.clicked.connect(self._on_export_csv)

        btn_layout.addWidget(self._start_btn)
        btn_layout.addWidget(self._stop_btn)
        btn_layout.addWidget(self._clear_btn)
        btn_layout.addWidget(self._export_btn)

        main_layout.addWidget(btn_widget)

        return container

    # ── 오른쪽: 결과 테이블 ─────────────────────────────────────
    def _build_result_panel(self) -> QWidget:
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(16, 12, 16, 16)
        layout.setSpacing(8)

        # 패널 헤더
        header_row = QHBoxLayout()
        result_label = QLabel("측정 결과")
        font = QFont("Segoe UI", 12)
        font.setBold(True)
        result_label.setFont(font)
        result_label.setStyleSheet("color: #1E293B;")

        self._point_count_label = QLabel("")
        self._point_count_label.setStyleSheet("color: #94A3B8; font-size: 11px;")

        header_row.addWidget(result_label)
        header_row.addStretch()
        header_row.addWidget(self._point_count_label)
        layout.addLayout(header_row)

        # 테이블 (셀 범위 선택 + Ctrl+C 복사 지원)
        self._table = _CopyableTable(0, 1)
        self._table.setHorizontalHeaderLabels(["인가 전압 (V)"])
        self._table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeMode.Fixed
        )
        self._table.horizontalHeader().setDefaultSectionSize(130)
        self._table.horizontalHeader().setStretchLastSection(True)
        self._table.verticalHeader().setDefaultSectionSize(28)
        self._table.verticalHeader().setVisible(True)
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectItems)
        self._table.setSelectionMode(QTableWidget.SelectionMode.ExtendedSelection)
        self._table.setAlternatingRowColors(True)
        self._table.setStyleSheet(
            "QTableWidget { font-size: 12px; }"
            "QTableWidget::item { padding: 2px 8px; }"
        )
        layout.addWidget(self._table)

        return panel

    # ── 이벤트 핸들러 ────────────────────────────────────────────
    def _on_start(self) -> None:
        if self._instrument is None:
            self._set_status("계측기가 연결되지 않았습니다.", error=True)
            return
        if self._thread and self._thread.isRunning():
            return

        # 전압 포인트 계산
        self._voltage_points = _compute_voltage_points(
            self._start_spin.value(),
            self._end_spin.value(),
            self._step_spin.value(),
        )
        if not self._voltage_points:
            self._set_status("유효한 전압 범위를 설정하세요.", error=True)
            return

        # 테이블 행 초기화 (첫 스윕 시 또는 초기화 후)
        if self._table.rowCount() == 0:
            self._init_table_rows()

        # 새 스윕 열 추가
        self._sweep_count += 1
        col_idx = self._table.columnCount()
        self._table.setColumnCount(col_idx + 1)
        self._table.setHorizontalHeaderItem(
            col_idx,
            QTableWidgetItem(f"{self._sweep_count}차 측정 (F)"),
        )

        # 진행 표시
        self._progress_bar.setMaximum(len(self._voltage_points))
        self._progress_bar.setValue(0)
        self._progress_bar.show()
        self._start_btn.setEnabled(False)
        self._stop_btn.setEnabled(True)
        self._set_status(f"스윕 {self._sweep_count}차 진행 중…")

        # 워커 스레드 시작
        self._thread = QThread()
        self._worker = _SweepWorker(
            instrument=self._instrument,
            voltage_points=self._voltage_points,
            frequency=self._freq_spin.value(),
            ac_level=self._ac_spin.value(),
            delay_ms=self._delay_spin.value(),
        )
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.run)
        self._worker.row_done.connect(
            lambda row, v, c: self._on_row_done(row, v, c, col_idx)
        )
        self._worker.finished.connect(self._on_sweep_finished)
        self._worker.error.connect(self._on_sweep_error)
        self._worker.finished.connect(self._thread.quit)
        self._worker.error.connect(self._thread.quit)
        self._thread.start()

    def _on_stop(self) -> None:
        if self._worker:
            self._worker.stop()
        self._set_status("측정 중지됨.")

    def _on_clear(self) -> None:
        if self._thread and self._thread.isRunning():
            return
        self._table.clearContents()
        self._table.setRowCount(0)
        self._table.setColumnCount(1)
        self._table.setHorizontalHeaderLabels(["인가 전압 (V)"])
        self._sweep_count = 0
        self._voltage_points = []
        self._count_label.setText("측정 횟수: 0회")
        self._point_count_label.setText("")
        self._progress_bar.hide()
        self._export_btn.setEnabled(False)
        self._set_status("")

    def _on_export_csv(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self, "CSV로 저장", "dc_bias_result.csv", "CSV 파일 (*.csv)"
        )
        if not path:
            return
        try:
            self._export_to_csv(Path(path))
            self.status_message.emit(f"CSV 저장 완료: {path}")
            self._set_status("CSV 저장 완료.")
        except Exception as exc:
            self._set_status(f"저장 실패: {exc}", error=True)

    # ── 워커 슬롯 ────────────────────────────────────────────────
    @pyqtSlot(int, float, float, int)
    def _on_row_done(self, row: int, voltage: float, capacitance: float, col: int) -> None:
        # 인가 전압 열은 1차 측정 때만 기입
        if col == 1:
            v_item = QTableWidgetItem(f"{voltage:.3f}")
            v_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            v_item.setForeground(QColor("#1E3A5F"))
            self._table.setItem(row, 0, v_item)

        # 측정값 기입
        c_item = QTableWidgetItem(_fmt_cap(capacitance))
        c_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        c_item.setData(Qt.ItemDataRole.UserRole, capacitance)   # 원시값(F) 보존
        self._table.setItem(row, col, c_item)

        self._progress_bar.setValue(row + 1)
        self._table.scrollToItem(c_item)

    @pyqtSlot()
    def _on_sweep_finished(self) -> None:
        self._start_btn.setEnabled(True)
        self._stop_btn.setEnabled(False)
        self._export_btn.setEnabled(True)
        self._progress_bar.hide()
        self._count_label.setText(f"측정 횟수: {self._sweep_count}회")
        self._set_status(f"{self._sweep_count}차 스윕 완료.")
        self.status_message.emit(f"DC Bias 스윕 {self._sweep_count}차 완료")

    @pyqtSlot(str)
    def _on_sweep_error(self, msg: str) -> None:
        self._start_btn.setEnabled(True)
        self._stop_btn.setEnabled(False)
        self._progress_bar.hide()
        # 열 헤더는 이미 추가된 상태이므로 "(오류)" 표시로 구분
        col = self._table.columnCount() - 1
        if col >= 1:
            header_item = self._table.horizontalHeaderItem(col)
            if header_item:
                header_item.setText(f"{self._sweep_count}차 측정 (오류)")
        self._sweep_count = max(0, self._sweep_count - 1)
        self._count_label.setText(f"측정 횟수: {self._sweep_count}회")
        self._set_status(f"오류: {msg}", error=True)

    # ── 헬퍼 ─────────────────────────────────────────────────────
    def _on_instrument_connect(self) -> None:
        """계측기 연결 버튼 핸들러 — GPIB 스캔 후 드라이버를 로드한다."""
        try:
            from app.ui.dialogs.instrument_config import InstrumentConfigDialog
            dialog = InstrumentConfigDialog(parent=self)
            if dialog.exec():
                cfg = dialog.get_config()
                engine = MeasurementEngine(self.settings)
                instrument = engine.load_instrument(cfg["model"], cfg["resource_name"])
                self.set_instrument(instrument)
        except Exception as exc:
            self._set_status(f"계측기 연결 실패: {exc}", error=True)

    def set_instrument(self, instrument: BaseInstrument) -> None:
        """계측기 인스턴스를 주입한다."""
        self._instrument = instrument
        model = type(instrument).__name__
        self._instr_label.setText(f"계측기: {model} ●")
        self._instr_label.setStyleSheet("color: #4ADE80; font-size: 12px;")
        self._instr_status_label.setText(f"{model} ●")
        self._instr_status_label.setStyleSheet("color: #4ADE80; font-size: 12px;")
        self.instrument_connected.emit(model)

    def _init_table_rows(self) -> None:
        """전압 포인트 수만큼 행을 미리 생성한다."""
        self._table.setRowCount(len(self._voltage_points))
        self._point_count_label.setText(
            f"{len(self._voltage_points)} 포인트  "
            f"({self._start_spin.value():.2f} V → {self._end_spin.value():.2f} V, "
            f"스텝 {self._step_spin.value():.2f} V)"
        )

    def _set_status(self, msg: str, *, error: bool = False) -> None:
        color = "#DC2626" if error else "#64748B"
        self._status_label.setStyleSheet(f"color: {color}; font-size: 11px;")
        self._status_label.setText(msg)

    def _export_to_csv(self, path: Path) -> None:
        """현재 테이블 내용을 CSV로 저장한다."""
        with path.open("w", newline="", encoding="utf-8-sig") as f:
            writer = csv.writer(f)

            # 헤더 행
            headers = [
                self._table.horizontalHeaderItem(c).text()
                for c in range(self._table.columnCount())
            ]
            writer.writerow(headers)

            # 데이터 행 (측정값 열은 원시 float 값 사용)
            for row in range(self._table.rowCount()):
                row_data = []
                for col in range(self._table.columnCount()):
                    item = self._table.item(row, col)
                    if item is None:
                        row_data.append("")
                    elif col == 0:
                        # 전압: 숫자 그대로
                        row_data.append(item.text())
                    else:
                        # 용량: UserRole에 저장된 원시 float(F) 사용
                        raw = item.data(Qt.ItemDataRole.UserRole)
                        row_data.append(f"{raw:.6e}" if raw is not None else item.text())
                writer.writerow(row_data)
