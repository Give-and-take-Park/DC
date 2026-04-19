from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QSizePolicy, QFrame,
)
from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QFont


# ── 메인 카드 정의 ────────────────────────────────────────────────────────
# (icon, title, characteristic, description, available)
_MAIN_CARDS = [
    (
        "⚡",
        "DC-bias",
        "DC_BIAS",
        "직류 바이어스 인가에 따른\n용량 특성 평가",
        True,
    ),
    (
        "🔧",
        "HALT / 8585",
        "HALT_8585",
        "신뢰성 시험 조건에서의\n전기 특성 측정",
        False,
    ),
    (
        "🔬",
        "광학 설계분석",
        "OPTICAL",
        "광학 특성 및\n설계 결과 분석",
        True,
    ),
]


# ── 말풍선 위젯 ────────────────────────────────────────────────────────────
class _ComingSoonBubble(QFrame):
    """클릭한 카드 위에 잠깐 표시되는 '추후 오픈 예정' 말풍선."""

    def __init__(self, parent: QWidget):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setStyleSheet(
            "QFrame {"
            "  background: #1E3A5F;"
            "  border-radius: 10px;"
            "}"
        )

        lbl = QLabel("추후 오픈 예정입니다.", self)
        lbl.setStyleSheet(
            "color: #FFFFFF;"
            "font-size: 14px;"
            "font-weight: 600;"
            "padding: 10px 18px;"
            "background: transparent;"
        )
        lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(lbl)
        self.adjustSize()
        self.hide()

        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self.hide)

    def show_near(self, card: QWidget) -> None:
        """카드 중앙 상단에 말풍선을 표시하고 1.8초 후 자동으로 숨긴다."""
        self.adjustSize()
        # 카드 중앙 상단 → 부모 좌표로 변환
        card_center_x = card.x() + card.width() // 2
        card_top_y    = card.y()
        x = card_center_x - self.width() // 2
        y = card_top_y - self.height() - 10
        # 화면 밖으로 나가지 않도록 보정
        x = max(0, min(x, self.parent().width() - self.width()))
        y = max(0, y)
        self.move(x, y)
        self.show()
        self.raise_()
        self._timer.start(1800)


# ── 홈 페이지 ──────────────────────────────────────────────────────────────
class HomePage(QWidget):
    """3개 대형 카드로 구성된 측정 항목 선택 홈 화면."""

    card_clicked = pyqtSignal(str, str)  # (characteristic, title)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._bubble = _ComingSoonBubble(self)
        self._init_ui()

    def _init_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(48, 40, 48, 40)
        root.setSpacing(28)

        # ── 페이지 타이틀 ─────────────────────────────────────────
        title_label = QLabel("측정 항목 선택")
        title_font = QFont("Segoe UI", 22)
        title_font.setBold(True)
        title_label.setFont(title_font)
        title_label.setStyleSheet("color: #1E293B;")

        desc_label = QLabel("측정할 항목을 선택하세요.")
        desc_label.setStyleSheet("color: #64748B; font-size: 14px;")

        root.addWidget(title_label)
        root.addWidget(desc_label)

        # ── 카드 영역 ─────────────────────────────────────────────
        card_row = QHBoxLayout()
        card_row.setSpacing(24)
        card_row.setContentsMargins(0, 0, 0, 0)

        for icon, title, characteristic, description, available in _MAIN_CARDS:
            card = self._build_card(icon, title, characteristic, description, available)
            card_row.addWidget(card, 1)

        root.addLayout(card_row, 1)

    def _build_card(
        self,
        icon: str,
        title: str,
        characteristic: str,
        description: str,
        available: bool,
    ) -> QPushButton:
        """카드 버튼을 생성한다. available=False이면 잠금 스타일을 적용한다."""
        card = QPushButton()
        card.setObjectName("measurement-card" if available else "measurement-card-locked")
        card.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        card.setMinimumSize(180, 220)

        if available:
            card.setCursor(Qt.CursorShape.PointingHandCursor)
            card.clicked.connect(
                lambda checked=False, c=characteristic, t=title:
                    self.card_clicked.emit(c, t)
            )
        else:
            card.setCursor(Qt.CursorShape.ArrowCursor)
            card.clicked.connect(
                lambda checked=False, c=card: self._bubble.show_near(c)
            )

        layout = QVBoxLayout(card)
        layout.setContentsMargins(36, 40, 36, 36)
        layout.setSpacing(0)

        # 아이콘
        icon_lbl = QLabel(icon)
        icon_font = QFont()
        icon_font.setPointSize(42)
        icon_lbl.setFont(icon_font)
        icon_lbl.setAlignment(Qt.AlignmentFlag.AlignLeft)
        layout.addWidget(icon_lbl)

        layout.addSpacing(20)

        # 제목
        title_lbl = QLabel(title)
        title_font = QFont("Segoe UI", 20)
        title_font.setBold(True)
        title_lbl.setFont(title_font)
        title_lbl.setStyleSheet("color: #1E293B;" if available else "color: #94A3B8;")
        layout.addWidget(title_lbl)

        layout.addSpacing(12)

        # 설명
        desc_lbl = QLabel(description)
        color = "#64748B" if available else "#CBD5E1"
        desc_lbl.setStyleSheet(f"color: {color}; font-size: 14px; line-height: 1.5;")
        desc_lbl.setWordWrap(True)
        layout.addWidget(desc_lbl)

        layout.addStretch()

        # 우하단 표시 (활성: →, 비활성: 준비 중)
        bottom_row = QHBoxLayout()
        bottom_row.addStretch()
        if available:
            bottom_lbl = QLabel("→")
            bottom_lbl.setFont(QFont("Segoe UI", 18))
            bottom_lbl.setStyleSheet("color: #2563EB;")
        else:
            bottom_lbl = QLabel("준비 중")
            bottom_lbl.setFont(QFont("Segoe UI", 12))
            bottom_lbl.setStyleSheet(
                "color: #94A3B8;"
                "background: #F1F5F9;"
                "border-radius: 6px;"
                "padding: 3px 8px;"
            )
        bottom_row.addWidget(bottom_lbl)
        layout.addLayout(bottom_row)

        return card
