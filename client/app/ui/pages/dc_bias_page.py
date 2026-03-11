"""DC Bias 특성 측정 페이지 (Cp-D / Cs-D 모드)

레이아웃:
┌───────────────────────┬──────────────────────────────────────────────────────┐
│ 조건 패널 (230px)     │ 측정 결과                                             │
│                       │                                                      │
│ ┌ 계측기 ──────────┐  │  No. │ 전압 인가 조건 │ CHIP 1 │ CHIP 2(추가됨) │  │
│ │ GPIB: [combo][연결][●] │  │      │ AC(V)▼ DC(V)▼ │ Cp  DF │ Cp  DF │       │
│ └──────────────────┘  │  1   │               │        │        │           │
│ ┌ 측정 조건 ────────┐  │  2   │               │        │        │           │
│ │ 측정 모드 [combo] │  │  …                                                   │
│ │ 주파수    [combo] │  │                                                      │
│ │ 유지시간  [combo] │  │                                                      │
│ │ LOT no.   [text ] │  │                                                      │
│ └──────────────────┘  │                                                      │
│ [▶ 측정 시작]         │                                                      │
│ [■ 중지  ]            │                                                      │
│ [초기화  ]            │                                                      │
│ [CSV 내보내기]        │                                                      │
└───────────────────────┴──────────────────────────────────────────────────────┘

측정 흐름:
  1차 '측정 시작' → CHIP 1 열로 모든 데이터 행 AC/DC 조건 순차 측정
  2차 '측정 시작' → CHIP 2 열 자동 추가 → 모든 행 측정
  3차 이후 동일 패턴
"""

import csv
import time
from pathlib import Path
from typing import List, Optional

from PyQt6.QtCore import QObject, QPoint, QRegularExpression, Qt, QThread, pyqtSignal, pyqtSlot
from PyQt6.QtGui import QColor, QFont, QKeySequence, QRegularExpressionValidator
from PyQt6.QtWidgets import (
    QApplication,
    QComboBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMenu,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSplitter,
    QStyledItemDelegate,
    QTableWidget,
    QTableWidgetItem,
    QToolTip,
    QVBoxLayout,
    QWidget,
)

from app.config.settings import Settings
from app.core.api_client import APIClient
from app.core.measurement_engine import MeasurementEngine
from app.instruments.base import BaseInstrument
from app.instruments.drivers.lcr_meter.base_lcr import BaseLCRMeter

# ── 상수 ──────────────────────────────────────────────────────────────────────
_MODE_OPTIONS  = ["Cp-D", "Cs-D"]
_FREQ_OPTIONS  = ["100", "200", "1K", "100K", "직접 입력"]
_HOLD_OPTIONS  = ["1", "2", "3", "60", "직접 입력"]
_AC_DC_PRESETS = ["0", "1", "2"]
_CUSTOM_LABEL  = "직접 입력"

_HEADER_ROWS = 2     # 테이블 상단 2행이 헤더
_INIT_ROWS   = 5     # 초기 데이터 행 수

# 고정 컬럼 인덱스
_COL_NO      = 0     # No.
_COL_HOLD    = 1     # 유지 시간(s)
_COL_FREQ    = 2     # 주파수(Hz)
_COL_AC      = 3     # AC(V)
_COL_DC      = 4     # DC(V)
_FIXED_COLS  = 5     # No. + Hold + Freq + AC + DC


# ── 0 이상 실수 전용 델리게이트 ────────────────────────────────────────────────
class _NonNegativeDelegate(QStyledItemDelegate):
    """데이터 셀 편집 시 0 이상의 실수만 입력 허용."""

    _PATTERN = QRegularExpression(r"^\d*\.?\d*$")  # 음수·문자 불허

    def createEditor(self, parent, option, index):  # type: ignore[override]
        editor = super().createEditor(parent, option, index)
        if isinstance(editor, QLineEdit):
            # 유지 시간·주파수 컬럼은 "1K", "100K" 등 자유 입력 허용
            if index.column() not in (_COL_HOLD, _COL_FREQ):
                editor.setValidator(QRegularExpressionValidator(self._PATTERN, editor))
            editor.setAlignment(Qt.AlignmentFlag.AlignCenter)
            editor.setStyleSheet("QLineEdit { padding: 0px 2px; font-size: 12px; }")
        return editor

    def setModelData(self, editor, model, index):  # type: ignore[override]
        super().setModelData(editor, model, index)
        # ※ model.setData(TextAlignmentRole)를 여기서 호출하면 커밋 사이클 도중
        #   dataChanged 시그널이 발생해 "commitData … does not belong" 경고가 뜬다.
        #   정렬은 _ResultTable.itemChanged 슬롯에서 커밋 완료 후 처리한다.


# ── 헤더 셀 아이템 생성 ───────────────────────────────────────────────────────
def _make_header_item(text: str) -> QTableWidgetItem:
    item = QTableWidgetItem(text)
    item.setFlags(Qt.ItemFlag.ItemIsEnabled)
    item.setBackground(QColor("#EFF6FF"))
    item.setForeground(QColor("#1E3A5F"))
    item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
    f = QFont("Segoe UI", 9)
    f.setBold(True)
    item.setFont(f)
    return item


# ── 정전용량 포맷 헬퍼 ────────────────────────────────────────────────────────
def _fmt_cap(v: float) -> str:
    """정전용량을 nF 단위 숫자로 변환 (단위 문자 제외)."""
    if v != v:
        return "N/A"
    return f"{v * 1e9:.4f}"


# ── 측정 워커 (행 순차 스윕) ──────────────────────────────────────────────────
class _MeasurementWorker(QObject):
    """AC/DC 조건 목록을 받아 행 순서대로 측정하는 워커.
    각 행마다 configure(ac_level, dc_bias) → hold → measure."""

    row_done = pyqtSignal(int, float, float)   # (row_idx 0-based, cp_F, df)
    finished = pyqtSignal()
    error    = pyqtSignal(str)

    def __init__(
        self,
        instrument: BaseInstrument,
        conditions: List[tuple],   # [(hold_s, freq_hz, ac_v, dc_v), …] per data row
        mode: str = "CPD",         # "CPD" (Cp-D) 또는 "CSD" (Cs-D)
    ):
        super().__init__()
        self._instrument  = instrument
        self._conditions  = conditions
        self._mode        = mode
        self._running     = True

    def stop(self) -> None:
        self._running = False

    @pyqtSlot()
    def run(self) -> None:
        try:
            # 스윕 전 1회 — 측정 함수·바이어스·연속 트리거 설정 (주파수는 행별 configure에서)
            if hasattr(self._instrument, "setup_sweep"):
                self._instrument.setup_sweep(mode=self._mode)

            for row_idx, (hold_s, freq_hz, ac_v, dc_v) in enumerate(self._conditions):
                if not self._running:
                    break
                # 행별 파라미터(주파수·AC 레벨·DC 바이어스) 전송
                self._instrument.configure(
                    frequency=freq_hz,
                    ac_level=ac_v,
                    dc_bias=dc_v,
                    mode=self._mode,
                )
                if hold_s > 0:
                    time.sleep(hold_s)
                results = self._instrument.measure()
                cp = next(
                    (r.value for r in results if r.characteristic.value == "capacitance"),
                    float("nan"),
                )
                df = next(
                    (r.value for r in results if r.characteristic.value in ("df", "d")),
                    float("nan"),
                )
                self.row_done.emit(row_idx, cp, df)

            self.finished.emit()

        except Exception as exc:
            self.error.emit(str(exc))

        finally:
            try:
                if isinstance(self._instrument, BaseLCRMeter):
                    self._instrument.disable_dc_bias()
            except Exception:
                pass


# ── 다중 레벨 헤더 측정 결과 테이블 (동적 CHIP 열) ───────────────────────────
class _ResultTable(QTableWidget):
    """
    2행 헤더 + 직접 편집 + Enter 이동/행 추가 + Ctrl+C 복사.
    CHIP 열은 측정 시작 때마다 동적으로 추가된다.

    구조:
      행 0 : No.*(2행 span) | 전압 인가 조건*(2열 span) | CHIP 1*(2열 span) | …
      행 1 : (merged)       | AC(V)▼  | DC(V)▼         | Cp  | DF | …
      행 2+: 데이터

    시그널:
      chip_removed() — CHIP 열이 Delete 키로 삭제될 때 emit
    """

    chip_removed = pyqtSignal()   # CHIP 열 삭제 시 emit

    def __init__(self, parent: Optional[QWidget] = None):
        # 초기 컬럼: No., AC(V), DC(V), CHIP1-Cp, CHIP1-DF = 5열
        super().__init__(0, _FIXED_COLS + 2, parent)
        self._chip_count = 1
        self._setup_table()
        self._build_header_rows()
        for _ in range(_INIT_ROWS):
            self.append_data_row()

    # ── 테이블 초기 설정 ─────────────────────────────────────────────
    def _setup_table(self) -> None:
        self.horizontalHeader().setVisible(False)
        self.verticalHeader().setVisible(False)
        self.setEditTriggers(
            QTableWidget.EditTrigger.DoubleClicked
            | QTableWidget.EditTrigger.AnyKeyPressed
        )
        self.setSelectionMode(QTableWidget.SelectionMode.ExtendedSelection)
        self.setGridStyle(Qt.PenStyle.SolidLine)
        self.setStyleSheet(
            "QTableWidget { font-size: 12px; gridline-color: #CBD5E1; }"
            "QTableWidget::item { padding: 2px 6px; }"
            "QTableWidget::item:selected { background: #DBEAFE; color: #1E3A5F; }"
        )
        self.setColumnWidth(_COL_NO,   45)
        self.setColumnWidth(_COL_HOLD, 80)
        self.setColumnWidth(_COL_FREQ, 85)
        self.setColumnWidth(_COL_AC,   72)
        self.setColumnWidth(_COL_DC,   72)
        self._set_chip_col_widths(1)
        self.setItemDelegate(_NonNegativeDelegate(self))
        self.cellClicked.connect(self._on_cell_clicked)
        self.itemChanged.connect(self._on_item_changed)

    def _set_chip_col_widths(self, chip_num: int) -> None:
        col_cp = self.chip_col_start(chip_num)
        if col_cp < self.columnCount():
            self.setColumnWidth(col_cp,     90)   # Cp
        if col_cp + 1 < self.columnCount():
            self.setColumnWidth(col_cp + 1, 75)   # DF

    # ── 헤더 행 구성 ─────────────────────────────────────────────────
    def _build_header_rows(self) -> None:
        self.insertRow(0)
        self.insertRow(1)
        self.setRowHeight(0, 30)
        self.setRowHeight(1, 28)

        # 행 0: No.(2행 span), 측정 조건(4열 span), CHIP 1(2열 span)
        self.setItem(0, _COL_NO, _make_header_item("No."))
        self.setSpan(0, _COL_NO, 2, 1)

        self.setItem(0, _COL_HOLD, _make_header_item("측정 조건"))
        self.setSpan(0, _COL_HOLD, 1, 4)

        self.setItem(0, _FIXED_COLS, _make_header_item("CHIP 1"))
        self.setSpan(0, _FIXED_COLS, 1, 2)

        # 행 1: 유지 시간▼, 주파수▼, AC(V)▼, DC(V)▼, Cp(nF), DF
        for col, label in (
            (_COL_HOLD, "유지 시간(s) ▼"),
            (_COL_FREQ, "주파수(Hz) ▼"),
            (_COL_AC,   "AC(V) ▼"),
            (_COL_DC,   "DC(V) ▼"),
        ):
            self.setItem(1, col, _make_header_item(label))

        self.setItem(1, _FIXED_COLS,     _make_header_item("Cp(nF)"))
        self.setItem(1, _FIXED_COLS + 1, _make_header_item("DF"))

    # ── AC/DC 헤더 클릭 → 일괄 반영 메뉴 ────────────────────────────
    def _on_item_changed(self, item: QTableWidgetItem) -> None:
        """데이터 행의 값이 변경된 후(커밋 완료) 가운데 정렬을 보장한다."""
        if item.row() >= _HEADER_ROWS:
            item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)

    def _on_cell_clicked(self, row: int, col: int) -> None:
        """행 1의 조건 헤더 셀 클릭 시 일괄 입력 메뉴를 띄운다."""
        if row == 1 and col in (_COL_HOLD, _COL_FREQ, _COL_AC, _COL_DC):
            rect = self.visualRect(self.model().index(row, col))
            pos  = self.viewport().mapToGlobal(rect.bottomLeft())
            self._show_fill_menu(col, pos)

    def _show_fill_menu(self, col: int, pos: QPoint) -> None:
        if col == _COL_HOLD:
            presets   = [o for o in _HOLD_OPTIONS if o != _CUSTOM_LABEL]
            col_label = "유지 시간(s)"
        elif col == _COL_FREQ:
            presets   = [o for o in _FREQ_OPTIONS if o != _CUSTOM_LABEL]
            col_label = "주파수(Hz)"
        elif col == _COL_AC:
            presets   = _AC_DC_PRESETS
            col_label = "AC(V)"
        else:
            presets   = _AC_DC_PRESETS
            col_label = "DC(V)"

        menu       = QMenu(self)
        actions    = {menu.addAction(v): v for v in presets}
        menu.addSeparator()
        custom_act = menu.addAction("직접 입력…")

        result = menu.exec(pos)
        if result is None:
            return

        if result is custom_act:
            text, ok = QInputDialog.getText(
                self, "직접 입력", f"{col_label} 일괄 적용 값:"
            )
            if not ok or not text.strip():
                return
            value = text.strip()
        else:
            value = actions[result]

        self._fill_column(col, value)

    def _fill_column(self, col: int, value: str) -> None:
        for row in range(_HEADER_ROWS, self.rowCount()):
            item = QTableWidgetItem(value)
            item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.setItem(row, col, item)

    # ── 동적 CHIP 열 추가 ────────────────────────────────────────────
    @staticmethod
    def chip_col_start(chip_num: int) -> int:
        """chip_num(1-based) Cp 열 인덱스."""
        return _FIXED_COLS + (chip_num - 1) * 2

    def chip_count(self) -> int:
        return self._chip_count

    def add_chip_column(self) -> None:
        """다음 CHIP의 Cp/DF 열을 테이블 끝에 추가한다."""
        self._chip_count += 1
        chip_num = self._chip_count
        col_cp   = self.columnCount()

        self.insertColumn(col_cp)
        self.insertColumn(col_cp + 1)
        self.setColumnWidth(col_cp,     90)
        self.setColumnWidth(col_cp + 1, 75)

        # 그룹 헤더 (행 0)
        self.setItem(0, col_cp, _make_header_item(f"CHIP {chip_num}"))
        self.setSpan(0, col_cp, 1, 2)

        # 서브 헤더 (행 1)
        self.setItem(1, col_cp,     _make_header_item("Cp(nF)"))
        self.setItem(1, col_cp + 1, _make_header_item("DF"))

    # ── 데이터 행 관리 ───────────────────────────────────────────────
    def append_data_row(self) -> int:
        """새 데이터 행 삽입 후 행 인덱스 반환."""
        row = self.rowCount()
        self.insertRow(row)
        self.setRowHeight(row, 28)
        no_item = QTableWidgetItem(str(row - _HEADER_ROWS + 1))
        no_item.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
        no_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        no_item.setBackground(QColor("#F8FAFC"))
        no_item.setForeground(QColor("#64748B"))
        self.setItem(row, _COL_NO, no_item)
        return row

    def clear_data(self) -> None:
        """CHIP 1만 남기고 테이블 전체 초기화."""
        self.clearContents()
        self.setRowCount(0)
        self.setColumnCount(_FIXED_COLS + 2)   # 5열로 리셋
        self._chip_count = 1
        self._build_header_rows()
        for _ in range(_INIT_ROWS):
            self.append_data_row()

    # ── 키 이벤트 ────────────────────────────────────────────────────
    def keyPressEvent(self, event) -> None:  # type: ignore[override]
        key = event.key()
        if event.matches(QKeySequence.StandardKey.Copy):
            self._copy_selection()
        elif key == Qt.Key.Key_Delete:
            self._delete_selected()
        elif key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            idx = self.currentIndex()
            if not idx.isValid() or idx.row() < _HEADER_ROWS:
                super().keyPressEvent(event)
                return
            next_row = idx.row() + 1
            if next_row >= self.rowCount():
                next_row = self.append_data_row()
            super().keyPressEvent(event)  # 에디터 커밋 후 닫기 (EditingState에서 이동 없음)
            self.setCurrentCell(next_row, idx.column())
        else:
            super().keyPressEvent(event)

    def _delete_selected(self) -> None:
        """Delete 키 처리 — 우선순위:
          1. 현재 셀이 CHIP 그룹 헤더(행 0, col ≥ _FIXED_COLS) → CHIP 열 삭제
          2. 선택 범위에 _COL_NO 포함 → 해당 데이터 행 삭제
          3. 선택 범위에 CHIP 데이터 열 포함 → CHIP 열 삭제
          4. 그 외 → 편집 가능한 셀 값만 삭제
        """
        # 1. CHIP 그룹 헤더 클릭(행 0) 상태에서 Delete
        cur = self.currentIndex()
        if cur.isValid() and cur.row() == 0 and cur.column() >= _FIXED_COLS:
            chip_num = (cur.column() - _FIXED_COLS) // 2 + 1
            self._delete_chip(chip_num)
            self._renumber_chip_headers()
            self.chip_removed.emit()
            return

        # 2. No. 컬럼 셀이 선택 범위에 포함 → 행 삭제
        rows_to_delete: set[int] = set()
        for rng in self.selectedRanges():
            if _COL_NO in range(rng.leftColumn(), rng.rightColumn() + 1):
                for row in range(max(rng.topRow(), _HEADER_ROWS), rng.bottomRow() + 1):
                    rows_to_delete.add(row)
        if rows_to_delete:
            for row in sorted(rows_to_delete, reverse=True):
                self.removeRow(row)
            self._renumber_rows()
            return

        # 3. 일반 데이터 셀 (CHIP 포함) → 값만 삭제
        #    CHIP 열 삭제는 헤더(행 0) Delete 또는 우클릭 메뉴로만 수행
        for rng in self.selectedRanges():
            for row in range(rng.topRow(), rng.bottomRow() + 1):
                if row < _HEADER_ROWS:
                    continue
                for col in range(rng.leftColumn(), rng.rightColumn() + 1):
                    if col == _COL_NO:
                        continue
                    item = self.item(row, col)
                    if item is not None:
                        item.setText("")

    # ── 우클릭 컨텍스트 메뉴 ─────────────────────────────────────────
    def contextMenuEvent(self, event) -> None:  # type: ignore[override]
        index = self.indexAt(event.pos())
        if not index.isValid():
            return
        row, col = index.row(), index.column()

        menu = QMenu(self)

        if row >= _HEADER_ROWS and col == _COL_NO:
            # No. 셀 우클릭 → 행 삭제
            act = menu.addAction("행 삭제")
            if menu.exec(event.globalPos()) == act:
                self.removeRow(row)
                self._renumber_rows()

        elif row == 0 and col >= _FIXED_COLS:
            # CHIP 그룹 헤더 우클릭 → 열 삭제
            chip_num = (col - _FIXED_COLS) // 2 + 1
            act = menu.addAction(f"CHIP {chip_num} 열 삭제")
            if menu.exec(event.globalPos()) == act:
                self._delete_chip(chip_num)
                self._renumber_chip_headers()
                self.chip_removed.emit()

    # ── 헬퍼: CHIP 열 한 쌍 제거 ─────────────────────────────────────
    def _delete_chip(self, chip_num: int) -> None:
        if chip_num < 1 or chip_num > self._chip_count:
            return
        col_cp = self.chip_col_start(chip_num)
        self.removeColumn(col_cp + 1)
        self.removeColumn(col_cp)
        self._chip_count -= 1

    # ── 헬퍼: 행 삭제 후 No. 열 재번호 ──────────────────────────────
    def _renumber_rows(self) -> None:
        for row in range(_HEADER_ROWS, self.rowCount()):
            item = self.item(row, _COL_NO)
            if item is not None:
                item.setText(str(row - _HEADER_ROWS + 1))

    def _renumber_chip_headers(self) -> None:
        """CHIP 열 삭제 후 남은 열의 그룹 헤더(행 0)를 재번호한다."""
        for i in range(1, self._chip_count + 1):
            col = self.chip_col_start(i)
            self.setSpan(0, col, 1, 1)          # 기존 span 해제
            self.setItem(0, col, _make_header_item(f"CHIP {i}"))
            self.setSpan(0, col, 1, 2)

    def _copy_selection(self) -> None:
        ranges = self.selectedRanges()
        if not ranges:
            return
        min_r = min(r.topRow()      for r in ranges)
        max_r = max(r.bottomRow()   for r in ranges)
        min_c = min(r.leftColumn()  for r in ranges)
        max_c = max(r.rightColumn() for r in ranges)
        lines: list[str] = []
        for row in range(min_r, max_r + 1):
            cells: list[str] = []
            for col in range(min_c, max_c + 1):
                item = self.item(row, col)
                if item is None:
                    w = self.cellWidget(row, col)
                    cells.append(w.text() if w and hasattr(w, "text") else "")
                else:
                    cells.append(item.text())
            lines.append("\t".join(cells))
        QApplication.clipboard().setText("\n".join(lines))


# ── GPIB 연결 워커 (UI 스레드 블로킹 방지) ────────────────────────────────────
class _GpibConnectWorker(QObject):
    """pyvisa 연결 + *IDN? 확인을 백그라운드 스레드에서 실행한다."""

    connected = pyqtSignal(object)   # 연결 성공: instrument 인스턴스
    failed    = pyqtSignal(str)      # 연결 실패: 오류 메시지

    def __init__(self, settings: "Settings", resource_name: str):
        super().__init__()
        self._settings       = settings
        self._resource_name  = resource_name

    @pyqtSlot()
    def run(self) -> None:
        try:
            engine     = MeasurementEngine(self._settings)
            instrument = engine.load_instrument("E4980A", self._resource_name)
            idn        = instrument.identify()
            if "E4980" not in idn:
                raise ConnectionError(f"E4980A가 아닙니다: {idn}")
            self.connected.emit(instrument)
        except Exception as exc:
            self.failed.emit(str(exc))


# ── DC Bias 측정 페이지 ───────────────────────────────────────────────────────
class DCBiasMeasurementPage(QWidget):
    """DC Bias 특성 측정 전용 페이지 (Cp-D / Cs-D 모드).

    측정 흐름:
      1차 측정 시작 → CHIP 1 열로 모든 행 측정
      2차 측정 시작 → CHIP 2 열 추가 → 모든 행 측정
      …
    """

    back_requested       = pyqtSignal()
    status_message       = pyqtSignal(str)
    instrument_connected = pyqtSignal(str)

    def __init__(
        self,
        settings: Settings,
        api_client: APIClient,
        parent: Optional[QWidget] = None,
    ):
        super().__init__(parent)
        self.settings   = settings
        self.api_client = api_client
        self._instrument: Optional[BaseInstrument]     = None
        self._thread:     Optional[QThread]            = None
        self._worker:     Optional[_MeasurementWorker] = None
        self._connect_thread: Optional[QThread]           = None
        self._connect_worker: Optional[_GpibConnectWorker] = None
        self._connect_seq:    int = 0   # 요청 순번 — 이전 결과 무시용
        self._next_chip:       int       = 1   # 다음 측정 시작 때 사용할 CHIP 번호
        self._current_chip:    int       = 0   # 현재 측정 중인 CHIP 번호 (0 = 미측정)
        self._meas_count:      int       = 0
        self._meas_row_indices: List[int] = []  # 유효 조건 행의 테이블 행 인덱스
        self._init_ui()

    # ── UI 구성 ──────────────────────────────────────────────────────
    def _init_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        root.addWidget(self._build_page_header())

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setHandleWidth(1)
        splitter.addWidget(self._build_condition_panel())
        splitter.addWidget(self._build_result_panel())
        splitter.setSizes([230, 900])
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        root.addWidget(splitter)

    # ── 페이지 서브헤더 ──────────────────────────────────────────────
    def _build_page_header(self) -> QWidget:
        header = QWidget()
        header.setFixedHeight(48)
        header.setStyleSheet("background: #F4F6F9; border-bottom: 1px solid #E2E8F0;")
        layout = QHBoxLayout(header)
        layout.setContentsMargins(16, 0, 16, 0)

        title = QLabel("DC Bias 특성 측정")
        tf = QFont("Segoe UI", 14)
        tf.setBold(True)
        title.setFont(tf)
        title.setStyleSheet("color: #1E3A5F;")

        self._instr_label = QLabel("계측기: 미연결")
        self._instr_label.setStyleSheet("color: #94A3B8; font-size: 12px;")

        layout.addWidget(title)
        layout.addStretch()
        layout.addWidget(self._instr_label)
        return header

    # ── 왼쪽: 조건 패널 ──────────────────────────────────────────────
    def _build_condition_panel(self) -> QWidget:
        container = QWidget()
        container.setObjectName("dc-condition-panel")
        container.setFixedWidth(230)
        container.setStyleSheet(
            "QWidget#dc-condition-panel {"
            "  background: #FFFFFF;"
            "  border-right: 1px solid #E2E8F0;"
            "}"
        )

        main_layout = QVBoxLayout(container)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        scroll_content = QWidget()
        inner = QVBoxLayout(scroll_content)
        inner.setContentsMargins(12, 12, 12, 8)
        inner.setSpacing(8)

        # ── 계측기 그룹 ──────────────────────────────────────────────
        instr_box = QGroupBox("계측기")
        instr_layout = QVBoxLayout(instr_box)
        instr_layout.setContentsMargins(12, 18, 12, 12)
        instr_layout.setSpacing(6)

        gpib_label = QLabel("GPIB 주소")
        gpib_label.setStyleSheet("font-size: 12px; color: #374151;")
        instr_layout.addWidget(gpib_label)

        # GPIB 콤보 + 연결 버튼 + 상태 점 (한 행)
        gpib_row = QHBoxLayout()
        gpib_row.setSpacing(6)

        self._gpib_combo = QComboBox()
        self._gpib_combo.setFont(QFont("Segoe UI", 9))
        self._gpib_combo.setCursor(Qt.CursorShape.PointingHandCursor)
        self._gpib_combo.setPlaceholderText("(자동 스캔)")
        self._gpib_combo.currentTextChanged.connect(self._on_gpib_changed)

        self._instr_dot = QLabel("●")
        self._instr_dot.setStyleSheet("color: #94A3B8; font-size: 18px;")
        self._instr_dot.setFixedWidth(22)
        self._instr_dot.setAlignment(Qt.AlignmentFlag.AlignCenter)

        gpib_row.addWidget(self._gpib_combo, 1)
        gpib_row.addWidget(self._instr_dot)
        instr_layout.addLayout(gpib_row)

        inner.addWidget(instr_box)

        # ── 측정 조건 그룹 ────────────────────────────────────────────
        cond_box = QGroupBox("측정 조건")
        cond_form = QFormLayout(cond_box)
        cond_form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        cond_form.setVerticalSpacing(8)
        cond_form.setHorizontalSpacing(8)
        cond_form.setContentsMargins(12, 20, 12, 12)

        _COND_STYLE = (
            "QComboBox {"
            "  border: 1.5px solid #1E3A5F;"
            "  border-radius: 6px;"
            "  padding: 5px 10px;"
            "  font-size: 9pt;"
            "}"
            "QComboBox:focus { border: 2px solid #1E3A5F; }"
        )

        # 측정 모드
        self._mode_combo = QComboBox()
        self._mode_combo.setFont(QFont("Segoe UI", 9))
        self._mode_combo.addItems(_MODE_OPTIONS)
        self._mode_combo.setCursor(Qt.CursorShape.PointingHandCursor)
        self._mode_combo.setStyleSheet(_COND_STYLE)
        cond_form.addRow("측정 모드:", self._mode_combo)

        # LOT no. — 7자리 영문+숫자
        self._lot_edit = QLineEdit()
        self._lot_edit.setFont(QFont("Segoe UI", 9))
        self._lot_edit.setMaxLength(7)
        self._lot_edit.setPlaceholderText("7자리 (영문+숫자)")
        self._lot_edit.setValidator(
            QRegularExpressionValidator(
                QRegularExpression("[A-Za-z0-9]{0,7}"), self._lot_edit
            )
        )
        self._lot_edit.setStyleSheet(
            "QLineEdit {"
            "  border: 1.5px solid #1E3A5F;"
            "  border-radius: 6px;"
            "  padding: 5px 10px;"
            "}"
            "QLineEdit:focus { border: 2px solid #1E3A5F; }"
        )
        self._lot_edit.editingFinished.connect(self._on_lot_editing_finished)
        cond_form.addRow("LOT no.:", self._lot_edit)

        inner.addWidget(cond_box)

        # 상태 표시
        self._count_label = QLabel("측정 횟수: 0회")
        self._count_label.setStyleSheet("color: #64748B; font-size: 12px;")
        inner.addWidget(self._count_label)

        self._progress_bar = QProgressBar()
        self._progress_bar.setValue(0)
        self._progress_bar.setFixedHeight(14)
        self._progress_bar.setFormat("행 %v / %m")
        self._progress_bar.setStyleSheet(
            "QProgressBar { background: #E2E8F0; border: none; border-radius: 4px; }"
            "QProgressBar::chunk { background: #1E3A5F; border-radius: 4px; }"
        )
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

        # ── 고정 버튼 섹션 ────────────────────────────────────────────
        btn_panel = QWidget()
        btn_panel.setObjectName("dc-btn-panel")
        btn_panel.setStyleSheet(
            "QWidget#dc-btn-panel { background: #FFFFFF; border-top: 1px solid #E2E8F0; }"
        )
        bp = QVBoxLayout(btn_panel)
        bp.setContentsMargins(16, 12, 16, 16)
        bp.setSpacing(8)

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

        bp.addWidget(self._start_btn)
        bp.addWidget(self._stop_btn)
        bp.addWidget(self._clear_btn)
        bp.addWidget(self._export_btn)
        main_layout.addWidget(btn_panel)

        return container

    # ── 오른쪽: 결과 패널 ────────────────────────────────────────────
    def _build_result_panel(self) -> QWidget:
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(16, 12, 16, 16)
        layout.setSpacing(8)

        label = QLabel("측정 결과")
        lf = QFont("Segoe UI", 12)
        lf.setBold(True)
        label.setFont(lf)
        label.setStyleSheet("color: #1E293B;")
        layout.addWidget(label)

        self._table = _ResultTable()
        self._table.chip_removed.connect(self._on_chip_removed)
        layout.addWidget(self._table)
        return panel

    # ── 공개 메서드: 페이지 진입 시 자동 GPIB 스캔 ───────────────────
    def start_gpib_scan(self) -> None:
        """MainWindow에서 DC-bias 페이지 진입 시 호출 — GPIB 자동 스캔."""
        if self._instrument:
            return   # 이미 연결된 경우 재스캔 불필요
        self._set_status("GPIB 스캔 중…")
        QApplication.processEvents()
        try:
            engine    = MeasurementEngine(self.settings)
            resources = engine.list_gpib_resources()
            self._gpib_combo.blockSignals(True)
            self._gpib_combo.clear()
            if resources:
                self._gpib_combo.addItems(resources)
                self._gpib_combo.setEnabled(True)
                self._set_status(f"{len(resources)}개 리소스 발견.")
            else:
                self._gpib_combo.setEnabled(False)
                self._set_status("GPIB 리소스 없음.", error=True)
            self._gpib_combo.blockSignals(False)
            # 첫 번째 리소스로 자동 연결 시도
            if resources:
                self._on_gpib_changed(resources[0])
        except Exception as exc:
            self._gpib_combo.blockSignals(False)
            self._gpib_combo.clear()
            self._gpib_combo.setEnabled(False)
            self._set_status(f"스캔 실패: {exc}", error=True)

    # ── 이벤트 핸들러 ─────────────────────────────────────────────────

    def _on_gpib_changed(self, resource_name: str) -> None:
        """콤보 선택 변경 시 기존 연결을 해제하고 백그라운드에서 새 리소스 연결 시도.
        UI 스레드를 블로킹하지 않아 콤보 조작 시 렉이 발생하지 않는다."""
        # 진행 중인 연결 시도가 있으면 결과를 무시할 수 있도록 순번 증가
        self._connect_seq += 1
        my_seq = self._connect_seq

        self._instrument = None
        self._instr_dot.setStyleSheet("color: #94A3B8; font-size: 18px;")
        self._instr_label.setText("계측기: 미연결")
        self._instr_label.setStyleSheet("color: #94A3B8; font-size: 12px;")

        if not resource_name:
            self._set_status("")
            return

        self._instr_dot.setStyleSheet("color: #F59E0B; font-size: 18px;")
        self._set_status(f"연결 시도 중… ({resource_name})")

        self._connect_thread = QThread()
        self._connect_worker = _GpibConnectWorker(self.settings, resource_name)
        self._connect_worker.moveToThread(self._connect_thread)
        self._connect_thread.started.connect(self._connect_worker.run)

        def on_connected(instrument) -> None:
            if self._connect_seq != my_seq:
                return   # 이미 더 새로운 요청이 있음 — 결과 무시
            self.set_instrument(instrument)

        def on_failed(msg: str) -> None:
            if self._connect_seq != my_seq:
                return
            self._instr_dot.setStyleSheet("color: #EF4444; font-size: 18px;")
            self._set_status(f"연결 실패: {msg}", error=True)

        self._connect_worker.connected.connect(on_connected)
        self._connect_worker.failed.connect(on_failed)
        self._connect_worker.connected.connect(self._connect_thread.quit)
        self._connect_worker.failed.connect(self._connect_thread.quit)
        self._connect_thread.start()

    def _on_lot_editing_finished(self) -> None:
        """포커스를 잃을 때 LOT no. 7자리 검증 — 툴팁 메시지."""
        lot = self._lot_edit.text()
        if lot and len(lot) != 7:
            QToolTip.showText(
                self._lot_edit.mapToGlobal(
                    QPoint(0, self._lot_edit.height())
                ),
                "7자리를 입력하세요.",
                self._lot_edit,
            )

    def _on_start(self) -> None:
        if self._instrument is None:
            self._set_status("계측기가 연결되지 않았습니다.", error=True)
            return
        if self._thread and self._thread.isRunning():
            return

        # LOT no. 검증
        lot = self._lot_edit.text()
        if len(lot) != 7:
            self._set_status("비어 있는 조건을 입력해주세요.", error=True)
            return

        # 테이블에서 행별로 조건 수집 (유지 시간·주파수·AC·DC 모두 유효한 행만)
        conditions: List[tuple] = []
        row_indices: List[int]  = []
        for row in range(_HEADER_ROWS, self._table.rowCount()):
            def _text(col: int) -> str:
                item = self._table.item(row, col)
                return item.text().strip() if item else ""

            hold_text = _text(_COL_HOLD)
            freq_text = _text(_COL_FREQ)
            ac_text   = _text(_COL_AC)
            dc_text   = _text(_COL_DC)

            if not (hold_text and freq_text and ac_text and dc_text):
                continue   # 빈 값이 하나라도 있으면 스킵
            try:
                hold_s  = float(hold_text)
                freq_hz = self._parse_freq(freq_text)
                ac_v    = float(ac_text)
                dc_v    = float(dc_text)
            except ValueError:
                continue   # 숫자로 변환 불가한 행 스킵
            conditions.append((hold_s, freq_hz, ac_v, dc_v))
            row_indices.append(row)

        if not conditions:
            self._set_status("유효한 조건이 입력된 행이 없습니다.", error=True)
            return

        # 유효 행 확인 후 CHIP 열 추가
        # chip > table.chip_count() 이면 항상 열 추가
        # (초기 상태: chip=1, count=1 → 추가 불필요)
        # (CHIP 1 삭제 후: chip=1, count=0 → 추가 필요)
        # (N차 측정: chip=N, count=N-1 → 추가 필요)
        chip = self._next_chip
        if chip > self._table.chip_count():
            self._table.add_chip_column()
        self._current_chip      = chip
        self._meas_row_indices  = row_indices

        self._progress_bar.setRange(0, len(conditions))
        self._progress_bar.setValue(0)
        self._progress_bar.show()
        self._start_btn.setEnabled(False)
        self._stop_btn.setEnabled(True)
        self._set_status(f"CHIP {chip} 측정 중… (총 {len(conditions)}행)")

        mode_str = "CPD" if self._mode_combo.currentText() == "Cp-D" else "CSD"

        self._thread = QThread()
        self._worker = _MeasurementWorker(
            instrument=self._instrument,
            conditions=conditions,
            mode=mode_str,
        )
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.run)
        self._worker.row_done.connect(self._on_row_done)
        self._worker.finished.connect(self._on_meas_finished)
        self._worker.error.connect(self._on_meas_error)
        self._worker.finished.connect(self._thread.quit)
        self._worker.error.connect(self._thread.quit)
        self._thread.start()

    def _on_stop(self) -> None:
        if self._worker:
            self._worker.stop()
        self._set_status("측정 중지됨.")

    @pyqtSlot()
    def _on_chip_removed(self) -> None:
        """테이블에서 CHIP 열이 삭제되면 _next_chip을 현재 열 수에 맞게 동기화."""
        self._next_chip  = self._table.chip_count() + 1
        self._meas_count = self._table.chip_count()
        self._count_label.setText(f"측정 횟수: {self._meas_count}회")

    def _on_clear(self) -> None:
        if self._thread and self._thread.isRunning():
            return
        self._table.clear_data()
        self._next_chip    = 1
        self._current_chip = 0
        self._meas_count   = 0
        self._count_label.setText("측정 횟수: 0회")
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

    # ── 워커 슬롯 ─────────────────────────────────────────────────────

    @pyqtSlot(int, float, float)
    def _on_row_done(self, row_idx: int, cp: float, df: float) -> None:
        # row_idx는 conditions 리스트의 0-based 인덱스 → 실제 테이블 행으로 변환
        if row_idx >= len(self._meas_row_indices):
            return
        table_row = self._meas_row_indices[row_idx]
        col_cp    = self._table.chip_col_start(self._current_chip)
        col_df    = col_cp + 1

        cp_item = QTableWidgetItem(_fmt_cap(cp))
        cp_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        cp_item.setData(Qt.ItemDataRole.UserRole, cp)
        self._table.setItem(table_row, col_cp, cp_item)

        df_txt  = "N/A" if df != df else f"{df:.6f}"
        df_item = QTableWidgetItem(df_txt)
        df_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        self._table.setItem(table_row, col_df, df_item)

        self._progress_bar.setValue(row_idx + 1)

    @pyqtSlot()
    def _on_meas_finished(self) -> None:
        self._meas_count += 1
        self._next_chip  += 1
        self._current_chip = 0
        self._count_label.setText(f"측정 횟수: {self._meas_count}회")
        self._start_btn.setEnabled(True)
        self._stop_btn.setEnabled(False)
        self._progress_bar.hide()
        self._export_btn.setEnabled(True)
        msg = f"CHIP {self._meas_count} 측정 완료."
        self._set_status(msg)
        self.status_message.emit(msg)

    @pyqtSlot(str)
    def _on_meas_error(self, msg: str) -> None:
        self._start_btn.setEnabled(True)
        self._stop_btn.setEnabled(False)
        self._progress_bar.hide()
        # 실패한 CHIP 열이 추가된 경우 _next_chip을 되돌리지 않음
        # (사용자가 초기화 후 재시도)
        self._set_status(f"오류: {msg}", error=True)

    # ── 헬퍼 ──────────────────────────────────────────────────────────

    def set_instrument(self, instrument: BaseInstrument) -> None:
        self._instrument = instrument
        model = type(instrument).__name__
        self._instr_label.setText(f"계측기: {model} ●")
        self._instr_label.setStyleSheet("color: #4ADE80; font-size: 12px;")
        self._instr_dot.setStyleSheet("color: #4ADE80; font-size: 18px;")
        self._set_status(f"{model} 연결됨.")
        self.instrument_connected.emit(model)

    def _set_status(self, msg: str, *, error: bool = False) -> None:
        color = "#DC2626" if error else "#64748B"
        self._status_label.setStyleSheet(f"color: {color}; font-size: 11px;")
        self._status_label.setText(msg)

    @staticmethod
    def _parse_freq(text: str) -> float:
        t = text.upper().strip()
        if t.endswith("K"):
            return float(t[:-1]) * 1_000
        if t.endswith("M"):
            return float(t[:-1]) * 1_000_000
        return float(t)

    def _export_to_csv(self, path: Path) -> None:
        chip_count = self._table.chip_count()
        with path.open("w", newline="", encoding="utf-8-sig") as f:
            writer = csv.writer(f)
            headers = ["No.", "유지 시간(s)", "주파수(Hz)", "AC(V)", "DC(V)"]
            for i in range(1, chip_count + 1):
                headers += [f"CHIP{i}_Cp", f"CHIP{i}_DF"]
            writer.writerow(headers)

            total_cols = _FIXED_COLS + chip_count * 2
            for row in range(_HEADER_ROWS, self._table.rowCount()):
                row_data = []
                for col in range(total_cols):
                    item = self._table.item(row, col)
                    if item is None:
                        row_data.append("")
                    else:
                        raw = item.data(Qt.ItemDataRole.UserRole)
                        row_data.append(
                            f"{raw:.6e}" if isinstance(raw, float) else item.text()
                        )
                writer.writerow(row_data)
