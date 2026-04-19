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
│ │ 세션명: [________] │ │  파일 탭: 드래그앤드롭 영역 + 파일 선택 버튼       │
│ │ 설명:   [________] │ │  캡처 탭: [캡처 시작] + 안내 문구                 │
│ └────────────────────┘ │  ─────────────────────────────────────────────── │
│                         │  [thumb] img1.png   [파일]  [×]                  │
│ 대기 이미지: 0장        │  [thumb] cap_1.png  [캡처]  [×]                  │
│                         │  ...                                             │
│ [▲ 서버 전송]           │                                                  │
│ [전체 삭제]             │                                                  │
└─────────────────────────┴──────────────────────────────────────────────────┘
"""

import tempfile
import uuid
from pathlib import Path
from typing import List, Optional

from PyQt6.QtCore import (
    QObject, QPoint, QRect, Qt, QThread, QTimer, pyqtSignal, pyqtSlot,
)
from PyQt6.QtGui import (
    QColor, QFont, QPainter, QPen, QPixmap,
)
from PyQt6.QtWidgets import (
    QApplication, QFileDialog, QFormLayout, QFrame, QGroupBox,
    QHBoxLayout, QLabel, QLineEdit, QProgressBar, QPushButton,
    QScrollArea, QSplitter, QVBoxLayout, QWidget,
)

from app.config.settings import Settings
from app.core.api_client import APIClient

# 캡처 이미지 저장 해상도 (픽셀)
_CAPTURE_W = 1536
_CAPTURE_H = 1024


# ── 전체화면 캡처 오버레이 ─────────────────────────────────────────────────────
class _CaptureOverlay(QWidget):
    """전체 화면 위에 표시되는 영역 선택 오버레이.

    - 오버레이 표시 전에 화면 전체를 미리 캡처하여 배경으로 사용
    - 마우스 드래그로 캡처 영역 선택 (파란 테두리 + 크기 안내)
    - 선택 완료 시 captured(pixmap, suggested_name) emit  (고해상도)
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
        # Qt6/Windows 에서 grabWindow(0) 이 반환하는 pixmap 의 크기가
        # 논리 픽셀(devicePixelRatio 반영)인 경우와
        # 물리 픽셀(devicePixelRatio == 1) 인 경우 모두 존재한다.
        # logical_w / pixmap_w 를 직접 비교하여 스케일을 계산하면
        # 어느 경우에도 올바른 좌표 변환이 가능하다.
        logical_w: int = screen.geometry().width()
        pixmap_w:  int = self._full_shot.width()
        # _px_scale: 논리 픽셀 1개당 픽스맵 픽셀 수 (≥ 1.0)
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

    # ── 논리 rect → 픽스맵 rect 변환 ────────────────────────────────
    def _to_pixmap_rect(self, logical: QRect) -> QRect:
        """위젯 논리 좌표 rect 를 _full_shot 픽스맵 좌표로 변환."""
        s = self._px_scale
        return QRect(
            round(logical.x()      * s),
            round(logical.y()      * s),
            round(logical.width()  * s),
            round(logical.height() * s),
        )

    # ── 그리기 ──────────────────────────────────────────────────────
    def paintEvent(self, event) -> None:  # type: ignore[override]
        painter = QPainter(self)

        # 배경: 미리 찍어둔 스크린샷 (논리 크기로 자동 스케일)
        painter.drawPixmap(self.rect(), self._full_shot)

        # 반투명 어두운 오버레이
        painter.fillRect(self.rect(), QColor(0, 0, 0, 110))

        if self._selecting:
            sel = QRect(self._start, self._end).normalized()
            if sel.width() > 0 and sel.height() > 0:
                # 선택 영역: 논리 rect → 픽스맵 rect 로 변환 후 원본 복원
                src = self._to_pixmap_rect(sel)
                painter.drawPixmap(sel, self._full_shot, src)
                # 파란 테두리
                pen = QPen(QColor("#2563EB"), 2)
                painter.setPen(pen)
                painter.setBrush(Qt.BrushStyle.NoBrush)
                painter.drawRect(sel)
                # 크기 안내 (물리 픽셀 기준으로 표시)
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

    # ── 마우스 이벤트 ────────────────────────────────────────────────
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
                # 논리 rect → 픽스맵 rect 로 변환하여 정확하게 크롭
                phys_rect = self._to_pixmap_rect(sel)
                cropped = self._full_shot.copy(phys_rect)
                # 지정 해상도(_CAPTURE_W × _CAPTURE_H)로 리샘플링
                # SmoothTransformation: 고품질 바이리니어 보간 적용
                final = cropped.scaled(
                    _CAPTURE_W, _CAPTURE_H,
                    Qt.AspectRatioMode.IgnoreAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
                final.setDevicePixelRatio(1.0)   # 저장 픽셀 = 논리 픽셀 1:1
                name = f"capture_{uuid.uuid4().hex[:8]}.png"
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


# ── 이미지 카드 위젯 ──────────────────────────────────────────────────────────
class _ImageCard(QFrame):
    """이미지 목록의 개별 아이템 (썸네일 + 파일명 + 출처 태그 + 삭제 버튼)."""

    remove_requested = pyqtSignal(str)   # uid

    _THUMB_W = 96
    _THUMB_H = 64

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
        self._build(item)

    def _build(self, item: _ImageItem) -> None:
        self.setObjectName("image-card")
        self.setStyleSheet(self._STYLE_NORMAL)
        self.setFixedHeight(84)

        row = QHBoxLayout(self)
        row.setContentsMargins(10, 8, 10, 8)
        row.setSpacing(12)

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

        # 파일명 + 출처 태그
        info = QVBoxLayout()
        info.setSpacing(4)

        name_lbl = QLabel(item.display_name)
        name_lbl.setFont(QFont("Segoe UI", 10))
        name_lbl.setStyleSheet("color: #1E293B; font-weight: 600;")

        tag_color = "#2563EB" if item.source == "파일" else "#7C3AED"
        tag_lbl = QLabel(f"● {item.source}")
        tag_lbl.setStyleSheet(f"color: {tag_color}; font-size: 11px;")

        info.addWidget(name_lbl)
        info.addWidget(tag_lbl)
        row.addLayout(info, 1)

        # 삭제 버튼
        del_btn = QPushButton("×")
        del_btn.setFixedSize(26, 26)
        del_btn.setStyleSheet(
            "QPushButton {"
            "  background: transparent; color: #94A3B8;"
            "  border: 1px solid #E2E8F0; border-radius: 4px;"
            "  font-size: 15px; font-weight: bold;"
            "}"
            "QPushButton:hover { color: #DC2626; border-color: #DC2626; }"
        )
        del_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        del_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        del_btn.clicked.connect(lambda: self.remove_requested.emit(self.uid))
        row.addWidget(del_btn)

    def mark_ok(self) -> None:
        self.setStyleSheet(self._STYLE_OK)

    def mark_error(self) -> None:
        self.setStyleSheet(self._STYLE_ERR)


# ── 업로드 워커 ───────────────────────────────────────────────────────────────
class _UploadWorker(QObject):
    """이미지 목록을 순차적으로 서버에 업로드하는 백그라운드 워커."""

    progress  = pyqtSignal(int, int, str)    # (현재, 전체, 파일명)
    item_done = pyqtSignal(str, bool, str)   # (uid, 성공여부, 메시지)
    finished  = pyqtSignal(int, int)         # (성공 수, 실패 수)

    def __init__(
        self,
        api_client: APIClient,
        items: List[_ImageItem],
        operator: str,
        session_name: str,
        description: str,
    ) -> None:
        super().__init__()
        self._api      = api_client
        self._items    = items
        self._operator = operator
        self._session  = session_name
        self._desc     = description
        self._running  = True

    def stop(self) -> None:
        self._running = False

    @pyqtSlot()
    def run(self) -> None:
        ok_count  = 0
        err_count = 0
        total     = len(self._items)

        for i, item in enumerate(self._items):
            if not self._running:
                break
            self.progress.emit(i + 1, total, item.display_name)
            try:
                self._api.upload_optical(
                    file_path=item.file_path,
                    operator=self._operator,
                    session_name=self._session,
                    description=self._desc,
                )
                self.item_done.emit(item.uid, True, "업로드 완료")
                ok_count += 1
            except Exception as exc:
                self.item_done.emit(item.uid, False, str(exc))
                err_count += 1

        self.finished.emit(ok_count, err_count)


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

        self._items:   List[_ImageItem]          = []
        self._cards:   dict[str, _ImageCard]     = {}
        self._thread:  Optional[QThread]         = None
        self._worker:  Optional[_UploadWorker]   = None
        self._overlay: Optional[_CaptureOverlay] = None

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

        # 초기 탭 스타일 적용
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

        # ── 스크롤 영역 ───────────────────────────────────────────────
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

        self._session_edit = QLineEdit()
        self._session_edit.setFont(QFont("Segoe UI", 9))
        self._session_edit.setPlaceholderText("세션명 (선택)")
        self._session_edit.setStyleSheet(_INPUT_STYLE)
        form.addRow("세션명:", self._session_edit)

        self._desc_edit = QLineEdit()
        self._desc_edit.setFont(QFont("Segoe UI", 9))
        self._desc_edit.setPlaceholderText("설명 (선택)")
        self._desc_edit.setStyleSheet(_INPUT_STYLE)
        form.addRow("설명:", self._desc_edit)

        inner.addWidget(info_box)

        # 상태
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

        # ── 이미지 카드 스크롤 영역 ──────────────────────────────────
        self._list_scroll = QScrollArea()
        self._list_scroll.setWidgetResizable(True)
        self._list_scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        self._list_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._list_scroll.setStyleSheet("background: transparent;")

        self._list_content = QWidget()
        self._list_content.setStyleSheet("background: transparent;")
        self._list_layout = QVBoxLayout(self._list_content)
        self._list_layout.setContentsMargins(0, 0, 0, 0)
        self._list_layout.setSpacing(6)

        # 빈 상태 안내 (stretch 앞에 배치)
        self._empty_label = QLabel(
            "이미지를 추가하세요.\n"
            "파일을 드래그앤드롭하거나, [파일 선택] 또는 [캡처 시작]을 클릭하세요."
        )
        self._empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._empty_label.setStyleSheet("color: #94A3B8; font-size: 13px;")
        self._list_layout.addWidget(self._empty_label)
        self._list_layout.addStretch()

        self._list_scroll.setWidget(self._list_content)
        layout.addWidget(self._list_scroll, 1)

        return panel

    def _build_file_action(self) -> QWidget:
        """파일 추가 탭: 드래그앤드롭 영역 + 파일 선택 버튼."""
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
        """화면 캡처 탭: 안내 문구 + 캡처 시작 버튼."""
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

        lbl = QLabel("화면의 특정 영역을 드래그하여 캡처합니다.\n고해상도(DPI 반영)로 저장됩니다.")
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
        # 창이 완전히 최소화될 때까지 대기 후 오버레이 표시
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

        # 임시 디렉터리에 PNG로 저장 (고해상도 유지)
        tmp_dir = Path(tempfile.gettempdir()) / "rims_captures"
        tmp_dir.mkdir(exist_ok=True)
        tmp_path = str(tmp_dir / name)
        pixmap.save(tmp_path, "PNG")

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
        self._cards[item.uid] = card
        # stretch 이전 위치(count-1)에 카드 삽입
        self._list_layout.insertWidget(self._list_layout.count() - 1, card)
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
        if card:
            self._list_layout.removeWidget(card)
            card.deleteLater()
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
            self._list_layout.removeWidget(card)
            card.deleteLater()
        self._cards.clear()
        self._refresh_state()
        self._set_status("")

    def _refresh_state(self) -> None:
        has = bool(self._items)
        self._empty_label.setVisible(not has)
        self._upload_btn.setEnabled(has)
        self._clear_all_btn.setEnabled(has)
        self._count_label.setText(f"대기 이미지: {len(self._items)}장")

    # ── 서버 전송 ─────────────────────────────────────────────────────
    def _on_upload(self) -> None:
        if not self._items:
            self._set_status("전송할 이미지가 없습니다.", error=True)
            return
        if self._thread and self._thread.isRunning():
            return

        self._upload_btn.setEnabled(False)
        self._clear_all_btn.setEnabled(False)
        self._progress_bar.setRange(0, len(self._items))
        self._progress_bar.setValue(0)
        self._progress_bar.show()
        self._set_status("서버 전송 중…")

        self._thread = QThread()
        self._worker = _UploadWorker(
            api_client=self.api_client,
            items=list(self._items),
            operator=self._operator_edit.text().strip(),
            session_name=self._session_edit.text().strip(),
            description=self._desc_edit.text().strip(),
        )
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.run)
        self._worker.progress.connect(self._on_upload_progress)
        self._worker.item_done.connect(self._on_item_done)
        self._worker.finished.connect(self._on_upload_finished)
        self._worker.finished.connect(self._thread.quit)
        self._thread.start()

    @pyqtSlot(int, int, str)
    def _on_upload_progress(self, current: int, total: int, name: str) -> None:
        self._progress_bar.setValue(current)
        self._set_status(f"전송 중 ({current}/{total}): {name}")

    @pyqtSlot(str, bool, str)
    def _on_item_done(self, uid: str, ok: bool, _msg: str) -> None:
        card = self._cards.get(uid)
        if card:
            if ok:
                card.mark_ok()
            else:
                card.mark_error()

    @pyqtSlot(int, int)
    def _on_upload_finished(self, ok: int, err: int) -> None:
        self._progress_bar.hide()
        msg = f"전송 완료: 성공 {ok}장"
        if err:
            msg += f", 실패 {err}장"
        self._set_status(msg, error=bool(err))
        self.status_message.emit(msg)
        has = bool(self._items)
        self._upload_btn.setEnabled(has)
        self._clear_all_btn.setEnabled(has)

    # ── 헬퍼 ──────────────────────────────────────────────────────────
    def _set_status(self, msg: str, *, error: bool = False) -> None:
        color = "#DC2626" if error else "#64748B"
        self._status_label.setStyleSheet(f"color: {color}; font-size: 11px;")
        self._status_label.setText(msg)

    def set_instrument(self, instrument) -> None:
        """MainWindow 인터페이스 호환용 — 광학 페이지는 계측기 불필요."""
        pass
