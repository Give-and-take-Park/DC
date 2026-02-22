from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel,
)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFont

from app.ui.widgets.measurement_card import MeasurementCard


# 측정 항목 정의: (icon, title, characteristic, subtitle, unit)
_CARDS = [
    ("≈", "정전용량", "CAPACITANCE", "Cp", "F"),
    ("Ω", "ESR", "ESR", "등가직렬저항", "Ω"),
    ("Q", "Q Factor", "Q_FACTOR", "품질계수", "–"),
    ("Z", "임피던스", "IMPEDANCE", "|Z|", "Ω"),
    ("⚡", "DC 바이어스", "DC_BIAS", "DC Bias", "V"),
    ("🌡", "온도 특성", "CAPACITANCE_TEMP", "온도 스윕", "F"),
]


class HomePage(QWidget):
    """측정 항목 카드 그리드 홈 화면."""

    card_clicked = pyqtSignal(str, str)  # (characteristic, title)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._init_ui()

    def _init_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(32, 32, 32, 32)
        root.setSpacing(24)

        # 섹션 헤더
        header_label = QLabel("측정 항목 선택")
        header_font = QFont("Segoe UI", 18)
        header_font.setBold(True)
        header_label.setFont(header_font)
        header_label.setStyleSheet("color: #1E293B;")

        desc_label = QLabel("측정할 MLCC 특성을 선택하세요.")
        desc_label.setStyleSheet("color: #64748B; font-size: 13px;")

        root.addWidget(header_label)
        root.addWidget(desc_label)
        root.addSpacing(8)

        # 카드 그리드 (3열 × 2행)
        grid_widget = QWidget()
        grid = QGridLayout(grid_widget)
        grid.setSpacing(16)
        grid.setContentsMargins(0, 0, 0, 0)

        for idx, (icon, title, characteristic, subtitle, unit) in enumerate(_CARDS):
            card = MeasurementCard(icon, title, subtitle, unit)
            card.clicked.connect(
                lambda checked=False, c=characteristic, t=title: self.card_clicked.emit(c, t)
            )
            row, col = divmod(idx, 3)
            grid.addWidget(card, row, col)

        root.addWidget(grid_widget)
        root.addStretch()
