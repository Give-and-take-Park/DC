from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QSizePolicy,
)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFont


# ── 메인 카드 정의 ────────────────────────────────────────────────────────
# (icon, title, characteristic, description)
_MAIN_CARDS = [
    (
        "⚡",
        "DC-bias",
        "DC_BIAS",
        "직류 바이어스 인가에 따른\n용량 특성 평가",
    ),
    (
        "🔧",
        "HALT / 8585",
        "HALT_8585",
        "신뢰성 시험 조건에서의\n전기 특성 측정",
    ),
    (
        "🔬",
        "광학 설계분석",
        "OPTICAL",
        "광학 특성 및\n설계 결과 분석",
    ),
]


class HomePage(QWidget):
    """3개 대형 카드로 구성된 측정 항목 선택 홈 화면."""

    card_clicked = pyqtSignal(str, str)  # (characteristic, title)

    def __init__(self, parent=None):
        super().__init__(parent)
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

        # ── 카드 영역 — 3개 카드 가로 배열, 창 크기에 비례하여 확장 ─
        card_row = QHBoxLayout()
        card_row.setSpacing(24)
        card_row.setContentsMargins(0, 0, 0, 0)

        for icon, title, characteristic, description in _MAIN_CARDS:
            card = self._build_card(icon, title, characteristic, description)
            card_row.addWidget(card, 1)   # stretch=1 → 3개 카드가 균등 분배

        root.addLayout(card_row, 1)   # stretch=1 → 카드 행이 남은 세로 공간 모두 차지

    def _build_card(
        self, icon: str, title: str, characteristic: str, description: str
    ) -> QPushButton:
        """창 크기에 비례해 늘어나는 대형 카드 버튼을 생성한다."""
        card = QPushButton()
        card.setObjectName("measurement-card")
        card.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        card.setMinimumSize(180, 220)
        card.setCursor(Qt.CursorShape.PointingHandCursor)
        card.clicked.connect(
            lambda checked=False, c=characteristic, t=title:
                self.card_clicked.emit(c, t)
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
        title_lbl.setStyleSheet("color: #1E293B;")
        layout.addWidget(title_lbl)

        layout.addSpacing(12)

        # 설명
        desc_lbl = QLabel(description)
        desc_lbl.setStyleSheet("color: #64748B; font-size: 14px; line-height: 1.5;")
        desc_lbl.setWordWrap(True)
        layout.addWidget(desc_lbl)

        layout.addStretch()

        # 화살표 (우하단)
        arrow_row = QHBoxLayout()
        arrow_row.addStretch()
        arrow_lbl = QLabel("→")
        arrow_font = QFont("Segoe UI", 18)
        arrow_lbl.setFont(arrow_font)
        arrow_lbl.setStyleSheet("color: #2563EB;")
        arrow_row.addWidget(arrow_lbl)
        layout.addLayout(arrow_row)

        return card
