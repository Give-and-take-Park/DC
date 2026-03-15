import sys
from pathlib import Path
from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import QPropertyAnimation
from PyQt6.QtGui import QIcon
from app.config.settings import Settings
from app.core.api_client import APIClient
from app.ui.login_dialog import LoginDialog
from app.ui.main_window import MainWindow


def _show_login(settings: Settings, geometry=None) -> None:
    """로그인 다이얼로그를 표시하고 로그인 완료 시 MainWindow로 전환한다."""
    app = QApplication.instance()
    api_client = APIClient(settings)
    dialog = LoginDialog(settings)
    app._login_dialog = dialog  # GC 방지

    if geometry is not None:
        dialog.setGeometry(geometry)

    def _on_login_ready(username: str) -> None:
        settings.operator = username

        # LoginDialog와 같은 위치·크기로 MainWindow를 opacity=0으로 즉시 표시
        # (이 시점에 LoginDialog가 페이드아웃을 시작하므로 크로스페이드 발생)
        window = MainWindow(settings, api_client, username=username)
        app._main_window = window  # GC 방지
        window.setGeometry(dialog.geometry())
        window.setWindowOpacity(0.0)
        window.show()

        # LoginDialog 페이드아웃(300ms)과 동시에 MainWindow 페이드인(300ms)
        fade_in = QPropertyAnimation(window, b"windowOpacity", window)
        fade_in.setDuration(300)
        fade_in.setStartValue(0.0)
        fade_in.setEndValue(1.0)
        fade_in.start()
        # dialog.hide()는 dialog 자체 fade 완료 후 호출됨

        def _on_closed() -> None:
            if window.is_logout:
                # 로그아웃 → MainWindow 위치에서 로그인 화면 재표시
                _show_login(settings, geometry=window.geometry())
            else:
                QApplication.instance().quit()

        window.window_closed.connect(_on_closed)

    dialog.login_ready.connect(_on_login_ready)
    dialog.rejected.connect(QApplication.instance().quit)

    # 로그인 다이얼로그도 페이드인으로 등장
    dialog.setWindowOpacity(0.0)
    dialog.show()
    fade_in_dlg = QPropertyAnimation(dialog, b"windowOpacity", dialog)
    fade_in_dlg.setDuration(280)
    fade_in_dlg.setStartValue(0.0)
    fade_in_dlg.setEndValue(1.0)
    fade_in_dlg.start()


def main():
    app = QApplication(sys.argv)
    # 마지막 창이 닫혀도 QApplication이 자동 종료되지 않도록 설정
    # (로그아웃 후 로그인 다이얼로그를 다시 띄우기 위해 필요)
    app.setQuitOnLastWindowClosed(False)
    icon_path = Path(__file__).parent / "ui" / "styles" / "icon.ico"
    if icon_path.exists():
        app.setWindowIcon(QIcon(str(icon_path)))
    settings = Settings()

    _show_login(settings)
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
