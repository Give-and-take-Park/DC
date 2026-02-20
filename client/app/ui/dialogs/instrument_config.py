from typing import List, Optional
from PyQt6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QFormLayout,
    QLineEdit,
    QComboBox,
    QDialogButtonBox,
    QPushButton,
    QHBoxLayout,
)
from app.instruments.registry import InstrumentRegistry


class InstrumentConfigDialog(QDialog):
    """계측기 연결 설정 다이얼로그"""

    def __init__(self, parent=None, available_resources: Optional[List[str]] = None):
        super().__init__(parent)
        self.setWindowTitle("계측기 설정")
        self.available_resources = available_resources or []
        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        form = QFormLayout()

        # 계측기 모델 선택
        self.model_combo = QComboBox()
        self.model_combo.addItems(InstrumentRegistry.list_models())
        form.addRow("계측기 모델:", self.model_combo)

        # GPIB 리소스 주소
        resource_row = QHBoxLayout()
        self.resource_combo = QComboBox()
        self.resource_combo.setEditable(True)
        self.resource_combo.addItems(self.available_resources)
        resource_row.addWidget(self.resource_combo)

        refresh_btn = QPushButton("갱신")
        refresh_btn.setFixedWidth(50)
        refresh_btn.clicked.connect(self._on_refresh)
        resource_row.addWidget(refresh_btn)
        form.addRow("GPIB 리소스:", resource_row)

        # 세션명
        self.session_name_edit = QLineEdit()
        self.session_name_edit.setPlaceholderText("예: 100nF DC바이어스 평가")
        form.addRow("세션명:", self.session_name_edit)

        # 클라이언트 ID
        self.client_id_edit = QLineEdit("station-01")
        form.addRow("클라이언트 ID:", self.client_id_edit)

        layout.addLayout(form)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _on_refresh(self) -> None:
        """GPIB 리소스 목록을 다시 조회한다."""
        try:
            from app.instruments.gpib.connection import GPIBConnectionManager
            with GPIBConnectionManager() as mgr:
                resources = mgr.list_resources()
            self.resource_combo.clear()
            self.resource_combo.addItems(resources)
        except Exception as e:
            self.resource_combo.setPlaceholderText(f"조회 실패: {e}")

    def get_config(self) -> dict:
        """입력된 설정값을 딕셔너리로 반환한다."""
        return {
            "model": self.model_combo.currentText(),
            "resource_name": self.resource_combo.currentText(),
            "session_name": self.session_name_edit.text() or None,
            "client_id": self.client_id_edit.text(),
        }
