import threading
from pathlib import Path

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QWidget, QProgressBar,
)
from PyQt6.QtCore import Qt, QPropertyAnimation, QTimer, pyqtSignal
from PyQt6.QtGui import QFont, QIcon, QKeyEvent

from app.core.api_client import APIClient
from app.config.settings import Settings


class LoginDialog(QDialog):
    """Knox ID 입력 다이얼로그.

    Knox ID 입력 후 서버에 접속 로그를 전송하고 login_ready 시그널을 emit한다.
    인증 결과와 무관하게 즉시 메인 화면으로 전환한다.
    """

    login_ready = pyqtSignal(str)   # Knox ID (username)

    def __init__(self, settings: Settings, parent=None):
        super().__init__(parent)
        self.settings = settings
        self.api_client = APIClient(settings)
        self.token: str = "knox"
        self.username: str = ""

        self.setWindowTitle("RIMS")
        self.setMinimumSize(960, 640)
        self.resize(1200, 760)
        self.setWindowFlags(
            Qt.WindowType.Dialog | Qt.WindowType.WindowCloseButtonHint
        )
        _icon = Path(__file__).parent / "styles" / "icon.ico"
        if _icon.exists():
            self.setWindowIcon(QIcon(str(_icon)))
        self._init_ui()

    def _init_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── 카드 컨테이너 (중앙 정렬) ──────────────────────────────
        card = QWidget()
        card.setObjectName("card")
        card.setFixedWidth(480)
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
        title = QLabel("Raffaello Inspection\n& Metrology System")
        title_font = QFont("Segoe UI", 20)
        title_font.setBold(True)
        title.setFont(title_font)
        title.setStyleSheet("color: #1E3A5F;")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)

        sub = QLabel("Knox ID를 입력하세요")
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
        self._username_edit.setPlaceholderText("Knox ID")
        self._username_edit.setMinimumHeight(48)
        self._username_edit.setStyleSheet(_input_style)
        self._username_edit.returnPressed.connect(self._on_login)

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

        # 로딩 프로그레스바 (인디케이터 모드)
        self._progress_bar = QProgressBar()
        self._progress_bar.setRange(0, 0)   # indeterminate (marquee) 모드
        self._progress_bar.setFixedHeight(4)
        self._progress_bar.setTextVisible(False)
        self._progress_bar.setStyleSheet(
            "QProgressBar {"
            "  background: #E2E8F0;"
            "  border: none;"
            "  border-radius: 2px;"
            "}"
            "QProgressBar::chunk {"
            "  background: #1E3A5F;"
            "  border-radius: 2px;"
            "}"
        )
        self._progress_bar.hide()

        card_layout.addWidget(title)
        card_layout.addWidget(sub)
        card_layout.addSpacing(8)
        card_layout.addWidget(self._username_edit)
        card_layout.addWidget(self._error_label)
        card_layout.addWidget(self._login_btn)
        card_layout.addWidget(self._progress_bar)

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
        # returnPressed + keyPressEvent 양쪽에서 호출될 수 있으므로 중복 실행 방지
        if getattr(self, "_login_in_progress", False):
            return
        self._login_in_progress = True

        knox_id = self._username_edit.text().strip()
        if not knox_id:
            self._login_in_progress = False
            self._show_error("Knox ID를 입력하세요.")
            return

        self._login_btn.setEnabled(False)
        self._login_btn.setText("연결 중...")
        self._error_label.hide()
        self._progress_bar.show()
        self.username = knox_id

        # UI 갱신(버튼 텍스트·프로그레스바)이 화면에 그려진 후 API 호출
        # singleShot(0) → 이벤트 루프 1틱 후 실행, 블로킹 전에 렌더링 완료
        QTimer.singleShot(0, self._do_api_call)

    def _do_api_call(self) -> None:
        """로딩 화면 표시 후 API 호출을 백그라운드 스레드에서 실행한다."""
        # 600ms 타이머를 즉시 시작 — API 호출 완료 여부와 무관하게 전환 타이밍 고정
        QTimer.singleShot(600, self._do_transition)
        # 접속 로그 전송을 백그라운드에서 실행 (UI 스레드 블로킹 방지)
        threading.Thread(target=self._send_access_log, daemon=True).start()

    def _send_access_log(self) -> None:
        try:
            self.api_client.log_access(self.username)
        except Exception:
            pass

    def _do_transition(self) -> None:
        """로딩 완료 후 크로스페이드로 MainWindow로 전환한다."""
        self._progress_bar.hide()

        # login_ready를 먼저 emit → main.py가 MainWindow를 opacity=0으로 즉시 표시
        # 그 직후 LoginDialog 페이드아웃 시작 → 두 윈도우가 동시에 크로스페이드
        self.login_ready.emit(self.username)

        self._fade_anim = QPropertyAnimation(self, b"windowOpacity", self)
        self._fade_anim.setDuration(300)
        self._fade_anim.setStartValue(1.0)
        self._fade_anim.setEndValue(0.0)
        self._fade_anim.finished.connect(self.hide)
        self._fade_anim.start()

    def _show_error(self, message: str) -> None:
        self._error_label.setText(message)
        self._error_label.show()

    def keyPressEvent(self, event: QKeyEvent) -> None:  # type: ignore[override]
        # Enter 처리:
        #   - QLineEdit 포커스 시: returnPressed 시그널이 _on_login을 호출
        #   - 버튼 포커스 시: Qt가 Enter → clicked 변환 → _on_login을 호출
        # 여기서 중복 호출하면 MainWindow가 2개 생성되므로 super()에만 위임한다.
        super().keyPressEvent(event)
