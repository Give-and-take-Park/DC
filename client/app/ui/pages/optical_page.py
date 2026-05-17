"""광학 설계분석 페이지

방향 A — 파일 직접 업로드 (복수)
방향 B — 화면 영역 드래그 캡처 (복수, 고해상도 DPI 반영)
두 방식으로 추가한 이미지를 하나의 목록에서 관리 → 일괄 서버 전송.

레이아웃:
┌─────────────────────────┬──────────────────────────────────────────────────┐
│ 조건 패널 (260px 고정)  │ 이미지 패널                                       │
│                         │                                                  │
│ ┌ 작업 정보 ──────────┐ │  [📂 파일 추가]  [📷 화면 캡처]  ← 탭 토글       │
│ │ 작업자: [________] │ │  ─────────────────────────────────────────────── │
│ │ Lot No: [________] │ │  파일 탭: 드래그앤드롭 영역 + 파일 선택 버튼       │
│ └────────────────────┘ │  캡처 탭: [캡처 시작] + 안내 문구                 │
│                         │  ─────────────────────────────────────────────── │
│ 대기 이미지: 0장        │  이미지 목록 (격자 형태)                           │
│                         │  [card][card][card]                               │
│ [▲ 서버 전송]           │  [card][card]...                                  │
│ [전체 삭제]             │                                                  │
└─────────────────────────┴──────────────────────────────────────────────────┘
"""

import os
import tempfile
import uuid
from pathlib import Path
from typing import List, Optional

from PyQt6.QtCore import (
    QEvent, QObject, QPoint, QRect, QRegularExpression, Qt, QThread, QTimer,
    pyqtSignal, pyqtSlot,
)
from PyQt6.QtGui import (
    QColor, QFont, QPainter, QPen, QPixmap, QRegularExpressionValidator,
)
from PyQt6.QtWidgets import (
    QApplication, QDialog, QFileDialog, QFormLayout, QFrame, QGridLayout,
    QGroupBox, QHBoxLayout, QLabel, QLineEdit, QMessageBox, QProgressBar,
    QPushButton, QScrollArea, QSizePolicy, QSplitter, QVBoxLayout, QWidget,
)

from app.config.settings import Settings
from app.core.api_client import APIClient

# 캡처 이미지 저장 해상도 (픽셀)
_CAPTURE_W = 1536
_CAPTURE_H = 1024
# 이미지 격자 열 수
_GRID_COLS  = 3


# ── 전체화면 캡처 오버레이 ─────────────────────────────────────────────────────
class _CaptureOverlay(QWidget):
    """전체 화면 위에 표시되는 영역 선택 오버레이.

    - 오버레이 표시 전에 화면 전체를 미리 캡처하여 배경으로 사용
    - 마우스 드래그로 캡처 영역 선택 (파란 테두리 + 크기 안내)
    - 선택 완료 시 captured(pixmap, suggested_name) emit  (고해상도, BMP)
    - ESC 키로 취소, cancelled() emit
    """

    captured  = pyqtSignal(QPixmap, str)
    cancelled = pyqtSignal()

    def __init__(self) -> None:
        super().__init__(None)
        screen = QApplication.primaryScreen()

        # 오버레이 표시 전에 화면 전체 캡처 (오버레이가 포함되지 않도록)
        self._full_shot: QPixmap = screen.grabWindow(0)

        # ── HiDPI 스케일 팩터 계산 ─────────────────────────────────
        logical_w: int = screen.geometry().width()
        pixmap_w:  int = self._full_shot.width()
        self._px_scale: float = pixmap_w / logical_w if logical_w > 0 else 1.0

        self.setGeometry(screen.geometry())
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setCursor(Qt.CursorShape.CrossCursor)

        self._start:     QPoint = QPoint()
        self._end:       QPoint = QPoint()
        self._selecting: bool   = False

    def _to_pixmap_rect(self, logical: QRect) -> QRect:
        """위젯 논리 좌표 rect 를 _full_shot 픽스맵 좌표로 변환."""
        s = self._px_scale
        return QRect(
            round(logical.x()      * s),
            round(logical.y()      * s),
            round(logical.width()  * s),
            round(logical.height() * s),
        )

    def paintEvent(self, event) -> None:  # type: ignore[override]
        painter = QPainter(self)
        painter.drawPixmap(self.rect(), self._full_shot)
        painter.fillRect(self.rect(), QColor(0, 0, 0, 110))

        if self._selecting:
            sel = QRect(self._start, self._end).normalized()
            if sel.width() > 0 and sel.height() > 0:
                src = self._to_pixmap_rect(sel)
                painter.drawPixmap(sel, self._full_shot, src)
                pen = QPen(QColor("#2563EB"), 2)
                painter.setPen(pen)
                painter.setBrush(Qt.BrushStyle.NoBrush)
                painter.drawRect(sel)
                phys_w = round(sel.width()  * self._px_scale)
                phys_h = round(sel.height() * self._px_scale)
                info_text = f"  {phys_w} × {phys_h} px  "
                f = painter.font()
                f.setPointSize(10)
                painter.setFont(f)
                lx = sel.x()
                ly = sel.y() - 22
                fm = self.fontMetrics()
                tw = fm.horizontalAdvance(info_text) + 8
                painter.fillRect(lx, max(ly, 2), tw, 20, QColor("#2563EB"))
                painter.setPen(QColor("#FFFFFF"))
                painter.drawText(lx + 4, max(ly, 2) + 14, info_text)

    def mousePressEvent(self, event) -> None:  # type: ignore[override]
        if event.button() == Qt.MouseButton.LeftButton:
            self._start     = event.pos()
            self._end       = event.pos()
            self._selecting = True

    def mouseMoveEvent(self, event) -> None:  # type: ignore[override]
        if self._selecting:
            self._end = event.pos()
            self.update()

    def mouseReleaseEvent(self, event) -> None:  # type: ignore[override]
        if event.button() == Qt.MouseButton.LeftButton and self._selecting:
            self._selecting = False
            sel = QRect(self._start, self._end).normalized()
            self.hide()

            if sel.width() > 10 and sel.height() > 10:
                phys_rect = self._to_pixmap_rect(sel)
                cropped = self._full_shot.copy(phys_rect)
                final = cropped.scaled(
                    _CAPTURE_W, _CAPTURE_H,
                    Qt.AspectRatioMode.IgnoreAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
                final.setDevicePixelRatio(1.0)
                name = f"capture_{uuid.uuid4().hex[:8]}.bmp"
                self.captured.emit(final, name)
            else:
                self.cancelled.emit()

    def keyPressEvent(self, event) -> None:  # type: ignore[override]
        if event.key() == Qt.Key.Key_Escape:
            self._selecting = False
            self.hide()
            self.cancelled.emit()


# ── 이미지 아이템 (데이터) ────────────────────────────────────────────────────
class _ImageItem:
    __slots__ = ("uid", "file_path", "display_name", "source", "pixmap", "is_temp")

    def __init__(
        self,
        uid: str,
        file_path: str,
        display_name: str,
        source: str,        # "파일" | "캡처"
        pixmap: QPixmap,
        is_temp: bool = False,
    ) -> None:
        self.uid          = uid
        self.file_path    = file_path
        self.display_name = display_name
        self.source       = source
        self.pixmap       = pixmap
        self.is_temp      = is_temp


# ── 이미지 카드 위젯 (격자 형태) ─────────────────────────────────────────────
class _ImageCard(QFrame):
    """이미지 목록의 개별 아이템 (격자 카드: 썸네일 + 파일명 + 출처 태그 + 삭제)."""

    remove_requested = pyqtSignal(str)    # uid
    name_changed     = pyqtSignal(str, str)  # uid, new_name

    _THUMB_W = 72
    _THUMB_H = 72
    _CARD_W  = 170
    _CARD_H  = 104

    _STYLE_NORMAL = (
        "QFrame#image-card {"
        "  background: #FFFFFF;"
        "  border: 1px solid #E2E8F0;"
        "  border-radius: 8px;"
        "}"
        "QFrame#image-card:hover { border: 1.5px solid #2563EB; }"
    )
    _STYLE_OK = (
        "QFrame#image-card {"
        "  background: #F0FDF4;"
        "  border: 1.5px solid #4ADE80;"
        "  border-radius: 8px;"
        "}"
    )
    _STYLE_ERR = (
        "QFrame#image-card {"
        "  background: #FFF1F2;"
        "  border: 1.5px solid #F87171;"
        "  border-radius: 8px;"
        "}"
    )

    def __init__(self, item: _ImageItem, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.uid = item.uid
        self._ext          = Path(item.display_name).suffix          # e.g. ".jpg"
        self._display_name = Path(item.display_name).stem            # 확장자 제외 파일명
        self._build(item)

    def _build(self, item: _ImageItem) -> None:
        self.setObjectName("image-card")
        self.setStyleSheet(self._STYLE_NORMAL)
        self.setFixedHeight(self._CARD_H)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        row = QHBoxLayout(self)
        row.setContentsMargins(8, 8, 8, 8)
        row.setSpacing(8)

        # 썸네일
        thumb_lbl = QLabel()
        thumb = item.pixmap.scaled(
            self._THUMB_W, self._THUMB_H,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        thumb_lbl.setPixmap(thumb)
        thumb_lbl.setFixedSize(self._THUMB_W, self._THUMB_H)
        thumb_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        thumb_lbl.setStyleSheet(
            "background: #F1F5F9; border-radius: 4px; border: 1px solid #E2E8F0;"
        )
        row.addWidget(thumb_lbl)

        # 오른쪽: 이름 + 태그
        right = QVBoxLayout()
        right.setContentsMargins(0, 0, 0, 0)
        right.setSpacing(4)

        # 이름 행 (label / edit) + × 버튼
        name_row = QHBoxLayout()
        name_row.setContentsMargins(0, 0, 0, 0)
        name_row.setSpacing(2)

        self._name_lbl = QLabel(self._display_name)
        self._name_lbl.setFont(QFont("Segoe UI", 10))
        self._name_lbl.setStyleSheet("color: #1E293B; font-weight: 600;")
        self._name_lbl.setWordWrap(True)
        self._name_lbl.setToolTip("클릭하여 파일명 수정")
        self._name_lbl.setCursor(Qt.CursorShape.IBeamCursor)
        self._name_lbl.mousePressEvent = self._start_edit  # type: ignore[method-assign]

        self._name_edit = QLineEdit(self._display_name)
        self._name_edit.setFont(QFont("Segoe UI", 10))
        self._name_edit.setStyleSheet(
            "QLineEdit { border: 1.5px solid #2563EB; border-radius: 3px; padding: 1px 4px; }"
        )
        self._name_edit.hide()
        self._name_edit.editingFinished.connect(self._finish_edit)
        self._name_edit.installEventFilter(self)

        name_row.addWidget(self._name_lbl, 1)
        name_row.addWidget(self._name_edit, 1)

        del_btn = QPushButton("×")
        del_btn.setFixedSize(18, 18)
        del_btn.setStyleSheet(
            "QPushButton {"
            "  background: transparent; color: #94A3B8;"
            "  border: 1px solid #E2E8F0; border-radius: 3px;"
            "  font-size: 12px; font-weight: bold;"
            "}"
            "QPushButton:hover { color: #DC2626; border-color: #DC2626; }"
        )
        del_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        del_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        del_btn.clicked.connect(lambda: self.remove_requested.emit(self.uid))
        name_row.addWidget(del_btn, 0, Qt.AlignmentFlag.AlignTop)

        right.addLayout(name_row)

        tag_color = "#2563EB" if item.source == "파일" else "#7C3AED"
        ext_str = self._ext.lstrip(".").upper()
        tag_lbl = QLabel(f"● {ext_str} {item.source}")
        tag_lbl.setStyleSheet(f"color: {tag_color}; font-size: 12px;")
        right.addWidget(tag_lbl)
        right.addStretch()

        row.addLayout(right, 1)

    def _start_edit(self, _event) -> None:
        self._name_lbl.hide()
        self._name_edit.setText(self._display_name)
        self._name_edit.show()
        self._name_edit.selectAll()
        self._name_edit.setFocus()

    def _finish_edit(self) -> None:
        new_stem = self._name_edit.text().strip()
        if new_stem and new_stem != self._display_name:
            self._display_name = new_stem
            self.name_changed.emit(self.uid, new_stem + self._ext)
        self._name_lbl.setText(self._display_name)
        self._name_edit.hide()
        self._name_lbl.show()

    def _cancel_edit(self) -> None:
        self._name_edit.blockSignals(True)
        self._name_edit.setText(self._display_name)  # 입력 내용 원복
        self._name_edit.hide()
        self._name_lbl.show()
        self._name_edit.blockSignals(False)

    def eventFilter(self, obj: QObject, event: QEvent) -> bool:  # type: ignore[override]
        if obj is self._name_edit and event.type() == QEvent.Type.KeyPress:
            if event.key() == Qt.Key.Key_Escape:  # type: ignore[attr-defined]
                self._cancel_edit()
                return True
        return super().eventFilter(obj, event)

    def mark_ok(self) -> None:
        self.setStyleSheet(self._STYLE_OK)

    def mark_error(self) -> None:
        self.setStyleSheet(self._STYLE_ERR)


# ── 파이프라인 워커 ───────────────────────────────────────────────────────────
class _PipelineWorker(QObject):
    """ZIP 압축 → 업로드 → 분석 요청 → 결과 다운로드 파이프라인 워커.

    5단계 진행:
      1. 이미지 ZIP 압축
      2. ZIP 서버 업로드
      3. 서버 분석 요청
      4. 결과 ZIP 다운로드
      5. 완료
    """

    stage_changed = pyqtSignal(int, str)   # (단계 1-5, 안내 문구)
    finished      = pyqtSignal(bool, str)  # (성공 여부, 메시지)

    _MSGS = {
        1: "1/5: 폴더 압축 중",
        2: "2/5: 서버로 파일 전송 중",
        3: "3/5: 서버에서 분석 진행 중",
        4: "4/5: 결과 다운로드 중",
        5: "5/5: 결과 다운로드 완료",
    }

    def __init__(
        self,
        api_client: APIClient,
        items: List[_ImageItem],
        operator: str,
        lot_no: str,
        save_dir: Path,
    ) -> None:
        super().__init__()
        self._api      = api_client
        self._items    = items
        self._operator = operator
        self._lot_no   = lot_no
        self._save_dir = save_dir

    @pyqtSlot()
    def run(self) -> None:
        import tempfile
        import zipfile

        zip_path: Optional[Path] = None
        try:
            # ── 1단계: ZIP 압축 ─────────────────────────────────────
            self.stage_changed.emit(1, self._MSGS[1])
            tmp_dir = Path(tempfile.gettempdir()) / "rims_optical"
            tmp_dir.mkdir(exist_ok=True)
            zip_path = tmp_dir / f"{self._lot_no}.zip"

            with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
                for item in self._items:
                    zf.write(item.file_path, item.display_name)

            # ── 2단계: ZIP 업로드 ────────────────────────────────────
            self.stage_changed.emit(2, self._MSGS[2])
            upload_result = self._api.upload_optical_zip(
                zip_path=str(zip_path),
                operator=self._operator,
                lot_no=self._lot_no,
            )
            folder_name: str = upload_result.get("folder_name", self._lot_no)

            # ── 3단계: 분석 요청 ─────────────────────────────────────
            self.stage_changed.emit(3, self._MSGS[3])
            self._api.request_optical_analysis(folder_name)

            # ── 4단계: 결과 다운로드 ─────────────────────────────────
            self.stage_changed.emit(4, self._MSGS[4])
            result_bytes = self._api.download_optical_result(folder_name)

            self._save_dir.mkdir(parents=True, exist_ok=True)

            # ── 버전 A: ZIP 파일로 저장 ──────────────────────────────
            # out_path = self._save_dir / f"{folder_name}_result.zip"
            # out_path.write_bytes(result_bytes)

            # ── 버전 B: Excel 파일로 저장 ────────────────────────────
            out_path = self._save_dir / f"{folder_name}_result.xlsx"
            out_path.write_bytes(result_bytes)

            # ── 5단계: 완료 ──────────────────────────────────────────
            self.stage_changed.emit(5, self._MSGS[5])
            self.finished.emit(True, str(out_path))

        except Exception as exc:
            self.finished.emit(False, f"오류: {exc}")
        finally:
            if zip_path is not None:
                try:
                    zip_path.unlink(missing_ok=True)
                except Exception:
                    pass


# ── 광학 설계분석 페이지 ──────────────────────────────────────────────────────
class OpticalAnalysisPage(QWidget):
    """광학 설계분석 이미지 업로드 페이지."""

    back_requested       = pyqtSignal()
    status_message       = pyqtSignal(str)
    instrument_connected = pyqtSignal(str)   # MainWindow 인터페이스 호환용

    def __init__(
        self,
        settings: Settings,
        api_client: APIClient,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.settings   = settings
        self.api_client = api_client

        self._items:        List[_ImageItem]           = []
        self._cards:        dict[str, _ImageCard]      = {}
        self._cards_order:  list[str]                  = []
        self._thread:       Optional[QThread]          = None
        self._worker:       Optional[_PipelineWorker]  = None
        self._overlay:      Optional[_CaptureOverlay]  = None

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
        splitter.addWidget(self._build_image_panel())
        splitter.setSizes([260, 900])
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        root.addWidget(splitter)

        self._switch_tab("file")

    # ── 페이지 서브헤더 ──────────────────────────────────────────────
    def _build_page_header(self) -> QWidget:
        header = QWidget()
        header.setFixedHeight(48)
        header.setStyleSheet("background: #F4F6F9; border-bottom: 1px solid #E2E8F0;")
        layout = QHBoxLayout(header)
        layout.setContentsMargins(16, 0, 16, 0)

        title = QLabel("광학 설계분석")
        tf = QFont("Segoe UI", 14)
        tf.setBold(True)
        title.setFont(tf)
        title.setStyleSheet("color: #1E3A5F;")
        layout.addWidget(title)
        layout.addStretch()
        return header

    # ── 왼쪽: 조건 패널 ──────────────────────────────────────────────
    def _build_condition_panel(self) -> QWidget:
        container = QWidget()
        container.setObjectName("dc-condition-panel")
        container.setFixedWidth(260)
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

        _INPUT_STYLE = (
            "QLineEdit {"
            "  border: 1.5px solid #1E3A5F;"
            "  border-radius: 6px;"
            "  padding: 5px 10px;"
            "  font-size: 9pt;"
            "}"
            "QLineEdit:focus { border: 2px solid #1E3A5F; }"
        )
        info_box = QGroupBox("작업 정보")
        form = QFormLayout(info_box)
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        form.setVerticalSpacing(8)
        form.setHorizontalSpacing(8)
        form.setContentsMargins(12, 20, 12, 12)

        self._operator_edit = QLineEdit()
        self._operator_edit.setFont(QFont("Segoe UI", 9))
        self._operator_edit.setPlaceholderText("작업자명")
        self._operator_edit.setText(self.settings.operator)
        self._operator_edit.setStyleSheet(_INPUT_STYLE)
        form.addRow("작업자:", self._operator_edit)

        self._lot_edit = QLineEdit()
        self._lot_edit.setFont(QFont("Segoe UI", 9))
        self._lot_edit.setPlaceholderText("7자리 영문/숫자")
        self._lot_edit.setMaxLength(7)
        self._lot_edit.setValidator(
            QRegularExpressionValidator(QRegularExpression("[A-Za-z0-9]{0,7}"))
        )
        self._lot_edit.setStyleSheet(_INPUT_STYLE)

        _test_btn = QPushButton("TEST")
        _test_btn.setFixedWidth(46)
        _test_btn.setFixedHeight(32)
        _test_btn.setFont(QFont("Segoe UI", 8))
        _test_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        _test_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        _test_btn.setStyleSheet(
            "QPushButton {"
            "  background: #F1F5F9; color: #475569;"
            "  border: 1.5px solid #CBD5E1; border-radius: 6px;"
            "  font-weight: 600;"
            "}"
            "QPushButton:hover { background: #E2E8F0; border-color: #94A3B8; }"
            "QPushButton:pressed { background: #CBD5E1; }"
        )
        _test_btn.clicked.connect(lambda: self._lot_edit.setText("TestLot"))

        lot_row = QHBoxLayout()
        lot_row.setSpacing(4)
        lot_row.setContentsMargins(0, 0, 0, 0)
        lot_row.addWidget(self._lot_edit, 1)
        lot_row.addWidget(_test_btn, 0)
        form.addRow("Lot No:", lot_row)

        inner.addWidget(info_box)

        self._count_label = QLabel("대기 이미지: 0장")
        self._count_label.setStyleSheet("color: #64748B; font-size: 12px;")
        inner.addWidget(self._count_label)

        self._progress_bar = QProgressBar()
        self._progress_bar.setValue(0)
        self._progress_bar.setFixedHeight(14)
        self._progress_bar.setFormat("%v / %m")
        self._progress_bar.setStyleSheet(
            "QProgressBar { background: #E2E8F0; border: none; border-radius: 4px; }"
            "QProgressBar::chunk { background: #1E3A5F; border-radius: 4px; }"
        )
        self._progress_bar.hide()
        inner.addWidget(self._progress_bar)

        self._status_label = QLabel("")
        self._status_label.setStyleSheet("color: #64748B; font-size: 11px;")
        self._status_label.setWordWrap(True)
        # Ignored: 텍스트 길이가 패널 수평 크기에 영향을 주지 않도록
        self._status_label.setSizePolicy(
            QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred
        )
        inner.addWidget(self._status_label)
        inner.addStretch()

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setWidget(scroll_content)
        main_layout.addWidget(scroll, 1)

        btn_panel = QWidget()
        btn_panel.setObjectName("dc-btn-panel")
        btn_panel.setStyleSheet(
            "QWidget#dc-btn-panel { background: #FFFFFF; border-top: 1px solid #E2E8F0; }"
        )
        bp = QVBoxLayout(btn_panel)
        bp.setContentsMargins(16, 12, 16, 16)
        bp.setSpacing(8)

        self._upload_btn = QPushButton("▲  서버 전송")
        self._upload_btn.setObjectName("dc-primary")
        self._upload_btn.setMinimumHeight(40)
        self._upload_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._upload_btn.setEnabled(False)
        self._upload_btn.clicked.connect(self._on_upload)

        self._clear_all_btn = QPushButton("전체 삭제")
        self._clear_all_btn.setObjectName("dc-secondary")
        self._clear_all_btn.setMinimumHeight(36)
        self._clear_all_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._clear_all_btn.setEnabled(False)
        self._clear_all_btn.clicked.connect(self._on_clear_all)

        bp.addWidget(self._upload_btn)
        bp.addWidget(self._clear_all_btn)
        main_layout.addWidget(btn_panel)

        return container

    # ── 오른쪽: 이미지 패널 ──────────────────────────────────────────
    def _build_image_panel(self) -> QWidget:
        panel = QWidget()
        panel.setStyleSheet("background: #F8FAFC;")
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(16, 12, 16, 16)
        layout.setSpacing(10)

        # ── 탭 토글 행 ───────────────────────────────────────────────
        top_row = QHBoxLayout()
        top_row.setSpacing(0)

        self._tab_file_btn = QPushButton("📂  파일 추가")
        self._tab_file_btn.setCheckable(True)
        self._tab_file_btn.setChecked(True)
        self._tab_file_btn.setMinimumHeight(36)
        self._tab_file_btn.setMinimumWidth(130)
        self._tab_file_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._tab_file_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._tab_file_btn.clicked.connect(lambda: self._switch_tab("file"))

        self._tab_cap_btn = QPushButton("📷  화면 캡처")
        self._tab_cap_btn.setCheckable(True)
        self._tab_cap_btn.setMinimumHeight(36)
        self._tab_cap_btn.setMinimumWidth(130)
        self._tab_cap_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._tab_cap_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._tab_cap_btn.clicked.connect(lambda: self._switch_tab("capture"))

        top_row.addWidget(self._tab_file_btn)
        top_row.addWidget(self._tab_cap_btn)
        top_row.addStretch()
        layout.addLayout(top_row)

        # ── 탭별 액션 패널 ────────────────────────────────────────────
        self._file_action = self._build_file_action()
        self._cap_action  = self._build_capture_action()
        layout.addWidget(self._file_action)
        layout.addWidget(self._cap_action)

        # ── 이미지 목록 헤더 ─────────────────────────────────────────
        list_header = QHBoxLayout()
        list_lbl = QLabel("이미지 목록")
        lf = QFont("Segoe UI", 11)
        lf.setBold(True)
        list_lbl.setFont(lf)
        list_lbl.setStyleSheet("color: #1E293B;")
        list_header.addWidget(list_lbl)
        list_header.addStretch()
        layout.addLayout(list_header)

        # ── 이미지 격자 스크롤 영역 ──────────────────────────────────
        self._list_scroll = QScrollArea()
        self._list_scroll.setWidgetResizable(True)
        self._list_scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        self._list_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._list_scroll.setStyleSheet("background: transparent;")

        self._list_content = QWidget()
        self._list_content.setStyleSheet("background: transparent;")
        content_layout = QVBoxLayout(self._list_content)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(0)

        # 빈 상태 안내
        self._empty_label = QLabel(
            "이미지를 추가하세요.\n"
            "파일을 드래그앤드롭하거나, [파일 선택] 또는 [캡처 시작]을 클릭하세요."
        )
        self._empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._empty_label.setStyleSheet("color: #94A3B8; font-size: 13px;")
        content_layout.addWidget(self._empty_label)

        # 격자 컨테이너
        self._grid_widget = QWidget()
        self._grid_widget.setStyleSheet("background: transparent;")
        self._list_layout = QGridLayout(self._grid_widget)
        self._list_layout.setContentsMargins(0, 4, 0, 4)
        self._list_layout.setSpacing(8)
        for _c in range(_GRID_COLS):
            self._list_layout.setColumnStretch(_c, 1)
        self._grid_widget.hide()
        content_layout.addWidget(self._grid_widget)
        content_layout.addStretch()

        self._list_scroll.setWidget(self._list_content)
        layout.addWidget(self._list_scroll, 1)

        return panel

    def _build_file_action(self) -> QWidget:
        w = QWidget()
        w.setObjectName("file-drop-area")
        w.setFixedHeight(80)
        w.setStyleSheet(
            "QWidget#file-drop-area {"
            "  background: #EFF6FF;"
            "  border: 2px dashed #93C5FD;"
            "  border-radius: 8px;"
            "}"
        )
        w.setAcceptDrops(True)

        layout = QHBoxLayout(w)
        layout.setContentsMargins(16, 8, 16, 8)

        lbl = QLabel("파일을 여기에 드롭하거나")
        lbl.setStyleSheet(
            "color: #64748B; font-size: 12px;"
            "border: none; background: transparent;"
        )

        btn = QPushButton("파일 선택")
        btn.setObjectName("dc-secondary")
        btn.setMinimumHeight(34)
        btn.setMinimumWidth(90)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.clicked.connect(self._on_select_files)

        layout.addStretch()
        layout.addWidget(lbl)
        layout.addSpacing(12)
        layout.addWidget(btn)
        layout.addStretch()

        w.dragEnterEvent = self._drag_enter  # type: ignore[method-assign]
        w.dropEvent      = self._drop_event  # type: ignore[method-assign]
        return w

    def _build_capture_action(self) -> QWidget:
        w = QWidget()
        w.setObjectName("capture-action-area")
        w.setFixedHeight(80)
        w.setStyleSheet(
            "QWidget#capture-action-area {"
            "  background: #F5F3FF;"
            "  border: 2px dashed #A78BFA;"
            "  border-radius: 8px;"
            "}"
        )

        layout = QHBoxLayout(w)
        layout.setContentsMargins(16, 8, 16, 8)

        lbl = QLabel(
            "화면의 특정 영역을 드래그하여 캡처합니다.\n"
            "고해상도(1536×1024 BMP)로 저장됩니다."
        )
        lbl.setStyleSheet(
            "color: #64748B; font-size: 12px;"
            "border: none; background: transparent;"
        )
        lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)

        btn = QPushButton("캡처 시작")
        btn.setMinimumHeight(34)
        btn.setMinimumWidth(90)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setStyleSheet(
            "QPushButton {"
            "  background: #7C3AED; color: #FFFFFF;"
            "  border: none; border-radius: 6px;"
            "  font-size: 13px; font-weight: 600;"
            "}"
            "QPushButton:hover { background: #6D28D9; }"
            "QPushButton:pressed { background: #5B21B6; }"
        )
        btn.clicked.connect(self._on_start_capture)

        layout.addStretch()
        layout.addWidget(lbl)
        layout.addSpacing(12)
        layout.addWidget(btn)
        layout.addStretch()

        return w

    # ── 탭 전환 ──────────────────────────────────────────────────────
    def _switch_tab(self, tab: str) -> None:
        is_file = (tab == "file")
        self._tab_file_btn.setChecked(is_file)
        self._tab_cap_btn.setChecked(not is_file)

        _ACTIVE_L = (
            "QPushButton {"
            "  background: #1E3A5F; color: #FFFFFF;"
            "  border: 1.5px solid #1E3A5F;"
            "  border-radius: 6px 0 0 6px;"
            "  font-size: 13px; font-weight: 600;"
            "  padding: 6px 18px;"
            "}"
        )
        _ACTIVE_R = (
            "QPushButton {"
            "  background: #1E3A5F; color: #FFFFFF;"
            "  border: 1.5px solid #1E3A5F;"
            "  border-radius: 0 6px 6px 0;"
            "  font-size: 13px; font-weight: 600;"
            "  padding: 6px 18px;"
            "}"
        )
        _INACTIVE_L = (
            "QPushButton {"
            "  background: #FFFFFF; color: #64748B;"
            "  border: 1.5px solid #CBD5E1;"
            "  border-radius: 6px 0 0 6px;"
            "  font-size: 13px;"
            "  padding: 6px 18px;"
            "}"
            "QPushButton:hover { background: #F1F5F9; }"
        )
        _INACTIVE_R = (
            "QPushButton {"
            "  background: #FFFFFF; color: #64748B;"
            "  border: 1.5px solid #CBD5E1;"
            "  border-radius: 0 6px 6px 0;"
            "  font-size: 13px;"
            "  padding: 6px 18px;"
            "}"
            "QPushButton:hover { background: #F1F5F9; }"
        )

        if is_file:
            self._tab_file_btn.setStyleSheet(_ACTIVE_L)
            self._tab_cap_btn.setStyleSheet(_INACTIVE_R)
            self._file_action.show()
            self._cap_action.hide()
        else:
            self._tab_file_btn.setStyleSheet(_INACTIVE_L)
            self._tab_cap_btn.setStyleSheet(_ACTIVE_R)
            self._file_action.hide()
            self._cap_action.show()

    # ── 파일 추가 ─────────────────────────────────────────────────────
    def _on_select_files(self) -> None:
        paths, _ = QFileDialog.getOpenFileNames(
            self,
            "이미지 파일 선택",
            "",
            "이미지 파일 (*.jpg *.jpeg *.png *.bmp *.tiff *.tif *.webp)",
        )
        for path in paths:
            self._add_file_item(path)

    def _drag_enter(self, event) -> None:  # type: ignore[misc]
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def _drop_event(self, event) -> None:  # type: ignore[misc]
        _OK_EXT = {".jpg", ".jpeg", ".png", ".bmp", ".tiff", ".tif", ".webp"}
        for url in event.mimeData().urls():
            path = url.toLocalFile()
            if Path(path).suffix.lower() in _OK_EXT:
                self._add_file_item(path)

    def _add_file_item(self, file_path: str) -> None:
        p = QPixmap(file_path)
        if p.isNull():
            self._set_status(f"이미지 로드 실패: {Path(file_path).name}", error=True)
            return
        item = _ImageItem(
            uid=uuid.uuid4().hex,
            file_path=file_path,
            display_name=Path(file_path).name,
            source="파일",
            pixmap=p,
            is_temp=False,
        )
        self._add_item(item)

    # ── 화면 캡처 ─────────────────────────────────────────────────────
    def _on_start_capture(self) -> None:
        win = self.window()
        if win:
            win.showMinimized()
        QTimer.singleShot(300, self._show_overlay)

    def _show_overlay(self) -> None:
        self._overlay = _CaptureOverlay()
        self._overlay.captured.connect(self._on_captured)
        self._overlay.cancelled.connect(self._on_capture_cancelled)
        self._overlay.showFullScreen()

    def _on_captured(self, pixmap: QPixmap, name: str) -> None:
        win = self.window()
        if win:
            win.showNormal()
            win.raise_()
            win.activateWindow()

        tmp_dir = Path(tempfile.gettempdir()) / "rims_captures"
        tmp_dir.mkdir(exist_ok=True)
        tmp_path = str(tmp_dir / name)
        pixmap.save(tmp_path, "BMP")

        item = _ImageItem(
            uid=uuid.uuid4().hex,
            file_path=tmp_path,
            display_name=name,
            source="캡처",
            pixmap=pixmap,
            is_temp=True,
        )
        self._add_item(item)

    def _on_capture_cancelled(self) -> None:
        win = self.window()
        if win:
            win.showNormal()
            win.raise_()
            win.activateWindow()

    # ── 이미지 목록 관리 ──────────────────────────────────────────────
    def _add_item(self, item: _ImageItem) -> None:
        self._items.append(item)
        card = _ImageCard(item)
        card.remove_requested.connect(self._on_remove_item)
        card.name_changed.connect(self._on_name_changed)
        self._cards[item.uid] = card
        self._cards_order.append(item.uid)
        self._rebuild_grid()
        self._refresh_state()

    def _on_remove_item(self, uid: str) -> None:
        item = next((i for i in self._items if i.uid == uid), None)
        if item is None:
            return
        if item.is_temp:
            try:
                Path(item.file_path).unlink(missing_ok=True)
            except Exception:
                pass
        self._items = [i for i in self._items if i.uid != uid]
        card = self._cards.pop(uid, None)
        if uid in self._cards_order:
            self._cards_order.remove(uid)
        if card:
            card.deleteLater()
        self._rebuild_grid()
        self._refresh_state()

    def _on_clear_all(self) -> None:
        for item in self._items:
            if item.is_temp:
                try:
                    Path(item.file_path).unlink(missing_ok=True)
                except Exception:
                    pass
        self._items.clear()
        for card in self._cards.values():
            card.deleteLater()
        self._cards.clear()
        self._cards_order.clear()
        self._rebuild_grid()
        self._refresh_state()
        self._set_status("")

    @pyqtSlot(str, str)
    def _on_name_changed(self, uid: str, new_name: str) -> None:
        item = next((i for i in self._items if i.uid == uid), None)
        if item:
            item.display_name = new_name

    def _rebuild_grid(self) -> None:
        """카드 목록을 격자 레이아웃으로 재배치한다."""
        while self._list_layout.count():
            self._list_layout.takeAt(0)

        for i, uid in enumerate(self._cards_order):
            card = self._cards.get(uid)
            if card:
                row, col = divmod(i, _GRID_COLS)
                self._list_layout.addWidget(card, row, col)

    def _refresh_state(self) -> None:
        has = bool(self._cards_order)
        self._empty_label.setVisible(not has)
        self._grid_widget.setVisible(has)
        self._upload_btn.setEnabled(has)
        self._clear_all_btn.setEnabled(has)
        self._count_label.setText(f"대기 이미지: {len(self._items)}장")

    # ── 서버 전송 ─────────────────────────────────────────────────────
    def _on_upload(self) -> None:
        if not self._items:
            self._set_status("이미지를 선택해주세요.", error=True)
            return
        lot = self._lot_edit.text().strip()
        if len(lot) != 7:
            self._set_status("Lot No를 올바르게 입력해주세요.", error=True)
            self._lot_edit.setFocus()
            return
        if self._thread and self._thread.isRunning():
            return

        self._upload_btn.setEnabled(False)
        self._clear_all_btn.setEnabled(False)
        self._progress_bar.setRange(0, 5)
        self._progress_bar.setValue(0)
        self._progress_bar.show()
        self._set_status("시작 중…")

        save_dir = Path.home() / "Downloads"

        self._thread = QThread()
        self._worker = _PipelineWorker(
            api_client=self.api_client,
            items=list(self._items),
            operator=self._operator_edit.text().strip(),
            lot_no=lot,
            save_dir=save_dir,
        )
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.run)
        self._worker.stage_changed.connect(self._on_stage_changed)
        self._worker.finished.connect(self._on_pipeline_finished)
        self._worker.finished.connect(self._thread.quit)
        self._thread.start()

    @pyqtSlot(int, str)
    def _on_stage_changed(self, stage: int, msg: str) -> None:
        self._progress_bar.setValue(stage)
        self._set_status(msg)

    @pyqtSlot(bool, str)
    def _on_pipeline_finished(self, ok: bool, msg: str) -> None:
        if ok:
            self._progress_bar.setValue(5)
            for card in self._cards.values():
                card.mark_ok()
            # 패널: 짧은 완료 문구 / 상태바: 전체 경로
            self._set_status("5/5: 결과 다운로드 완료")
            self.status_message.emit(f"결과 저장: {msg}")
            self._show_success_dialog(Path(msg).parent)
        else:
            self._progress_bar.hide()
            for card in self._cards.values():
                card.mark_error()
            self._set_status("전송 중 오류가 발생했습니다.", error=True)
            self.status_message.emit(f"광학 분석 오류: {msg}")
        has = bool(self._items)
        self._upload_btn.setEnabled(has)
        self._clear_all_btn.setEnabled(has)

    # ── 헬퍼 ──────────────────────────────────────────────────────────
    def _show_success_dialog(self, save_dir: Path) -> None:
        dlg = QDialog(self)
        dlg.setWindowTitle("분석 완료")
        dlg.setFixedWidth(360)

        layout = QVBoxLayout(dlg)
        layout.setContentsMargins(28, 28, 28, 20)
        layout.setSpacing(20)

        msg_lbl = QLabel("분석을 성공적으로 완료하였습니다.")
        msg_lbl.setFont(QFont("Segoe UI", 11))
        msg_lbl.setWordWrap(True)
        msg_lbl.setStyleSheet("color: #1E293B;")
        layout.addWidget(msg_lbl)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)

        open_btn = QPushButton("폴더 열기")
        open_btn.setObjectName("dc-secondary")
        open_btn.setMinimumHeight(36)
        open_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        open_btn.clicked.connect(
            lambda: os.startfile(str(save_dir)) if save_dir.exists() else None
        )

        ok_btn = QPushButton("확인")
        ok_btn.setObjectName("dc-primary")
        ok_btn.setMinimumHeight(36)
        ok_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        ok_btn.clicked.connect(dlg.accept)

        btn_row.addWidget(open_btn)
        btn_row.addWidget(ok_btn)
        layout.addLayout(btn_row)

        dlg.exec()

    def _set_status(self, msg: str, *, error: bool = False) -> None:
        color = "#DC2626" if error else "#64748B"
        self._status_label.setStyleSheet(f"color: {color}; font-size: 11px;")
        self._status_label.setText(msg)

    def set_instrument(self, instrument) -> None:
        """MainWindow 인터페이스 호환용 — 광학 페이지는 계측기 불필요."""
        pass
