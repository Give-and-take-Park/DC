from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QWidget, QSizePolicy,
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont, QKeyEvent

from app.core.api_client import APIClient
from app.config.settings import Settings


class LoginDialog(QDialog):
    """사용자 인증 다이얼로그.

    로그인 성공 시 self.token, self.username이 설정된 상태로 accept()된다.
    """

    def __init__(self, settings: Settings, parent=None):
        super().__init__(parent)
        self.settings = settings
        self.api_client = APIClient(settings)
        self.token: str = ""
        self.username: str = ""

        self.setWindowTitle("MLCC Data Collector — 로그인")
        self.setMinimumSize(960, 640)
        self.resize(1200, 760)
        self.setWindowFlags(
            Qt.WindowType.Dialog | Qt.WindowType.WindowCloseButtonHint
        )
        self._init_ui()

    def _init_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── 카드 컨테이너 (중앙 정렬) ──────────────────────────────
        card = QWidget()
        card.setObjectName("card")
        card.setFixedWidth(480)   # 창 크기와 무관하게 고정
        card.setStyleSheet(
            "QWidget#card {"
            "  background: white;"
            "  border-radius: 14px;"
            "  border: 1px solid #E2E8F0;"
            "}"
        )
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(44, 44, 44, 44)
        card_layout.setSpacing(18)

        # 타이틀
        title = QLabel("MLCC Data Collector")
        title_font = QFont("Segoe UI", 20)
        title_font.setBold(True)
        title.setFont(title_font)
        title.setStyleSheet("color: #1E3A5F;")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)

        sub = QLabel("계정으로 로그인하세요")
        sub.setStyleSheet("color: #64748B; font-size: 15px;")
        sub.setAlignment(Qt.AlignmentFlag.AlignCenter)

        # 입력 필드
        _input_style = (
            "QLineEdit {"
            "  font-size: 15px;"
            "  border: 1.5px solid #1E3A5F;"
            "  border-radius: 6px;"
            "  padding: 8px 12px;"
            "  background: #FFFFFF;"
            "  color: #1E293B;"
            "}"
            "QLineEdit:focus {"
            "  border: 2px solid #2D5F9A;"
            "}"
        )

        self._username_edit = QLineEdit()
        self._username_edit.setPlaceholderText("사용자명")
        self._username_edit.setMinimumHeight(48)
        self._username_edit.setStyleSheet(_input_style)

        self._password_edit = QLineEdit()
        self._password_edit.setPlaceholderText("비밀번호")
        self._password_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self._password_edit.setMinimumHeight(48)
        self._password_edit.setStyleSheet(_input_style)
        self._password_edit.returnPressed.connect(self._on_login)

        # 오류 메시지
        self._error_label = QLabel("")
        self._error_label.setObjectName("error-label")
        self._error_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._error_label.setWordWrap(True)
        self._error_label.setStyleSheet("color: #DC2626; font-size: 13px;")
        self._error_label.hide()

        # 로그인 버튼
        self._login_btn = QPushButton("로그인")
        self._login_btn.setObjectName("primary")
        self._login_btn.setMinimumHeight(50)
        self._login_btn.setStyleSheet(
            "QPushButton#primary {"
            "  background: #1E3A5F;"
            "  color: #FFFFFF;"
            "  border: none;"
            "  border-radius: 6px;"
            "  font-size: 16px;"
            "  font-weight: 600;"
            "}"
            "QPushButton#primary:hover { background: #2D5F9A; }"
            "QPushButton#primary:pressed { background: #162D48; }"
            "QPushButton#primary:disabled { background: #6B8FAD; }"
        )
        self._login_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._login_btn.clicked.connect(self._on_login)

        card_layout.addWidget(title)
        card_layout.addWidget(sub)
        card_layout.addSpacing(8)
        card_layout.addWidget(self._username_edit)
        card_layout.addWidget(self._password_edit)
        card_layout.addWidget(self._error_label)
        card_layout.addWidget(self._login_btn)

        # 외부 여백
        outer = QVBoxLayout()
        outer.setContentsMargins(32, 32, 32, 32)
        outer.addStretch()
        outer.addWidget(card)
        outer.addStretch()

        # 가로 중앙 정렬
        h_layout = QHBoxLayout()
        h_layout.addStretch()
        h_layout.addLayout(outer)
        h_layout.addStretch()

        root.addLayout(h_layout)

    def _on_login(self) -> None:
        username = self._username_edit.text().strip()
        password = self._password_edit.text()

        if not username or not password:
            self._show_error("사용자명과 비밀번호를 입력하세요.")
            return

        self._login_btn.setEnabled(False)
        self._login_btn.setText("로그인 중...")
        self._error_label.hide()

        try:
            data = self.api_client.login(username, password)
            self.token = data["access_token"]
            self.username = data.get("username", username)
            self.accept()
        except Exception as exc:
            msg = str(exc)
            if "401" in msg:
                self._show_error("사용자명 또는 비밀번호가 올바르지 않습니다.")
            elif "connect" in msg.lower() or "connection" in msg.lower():
                self._show_error("서버에 연결할 수 없습니다.\nAPI 서버가 실행 중인지 확인하세요.")
            else:
                self._show_error(f"로그인 실패: {exc}")
        finally:
            self._login_btn.setEnabled(True)
            self._login_btn.setText("로그인")

    def _show_error(self, message: str) -> None:
        self._error_label.setText(message)
        self._error_label.show()

    def keyPressEvent(self, event: QKeyEvent) -> None:  # type: ignore[override]
        if event.key() == Qt.Key.Key_Return or event.key() == Qt.Key.Key_Enter:
            self._on_login()
        else:
            super().keyPressEvent(event)
