from PyQt6.QtWidgets import QPushButton, QVBoxLayout, QLabel
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont


class MeasurementCard(QPushButton):
    """클릭 가능한 측정 항목 카드 위젯."""

    def __init__(self, icon: str, title: str, subtitle: str, unit: str, parent=None):
        super().__init__(parent)
        self.setObjectName("measurement-card")
        self.setFixedSize(200, 140)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(6)

        icon_label = QLabel(icon)
        icon_font = QFont()
        icon_font.setPointSize(22)
        icon_label.setFont(icon_font)
        icon_label.setAlignment(Qt.AlignmentFlag.AlignLeft)

        title_label = QLabel(title)
        title_font = QFont()
        title_font.setPointSize(12)
        title_font.setBold(True)
        title_label.setFont(title_font)
        title_label.setStyleSheet("color: #1E293B;")

        sub_label = QLabel(f"{subtitle}  [{unit}]")
        sub_label.setStyleSheet("color: #64748B; font-size: 11px;")

        layout.addWidget(icon_label)
        layout.addWidget(title_label)
        layout.addWidget(sub_label)
        layout.addStretch()
