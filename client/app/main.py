import sys
from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import QEventLoop
from app.config.settings import Settings
from app.core.api_client import APIClient
from app.ui.login_dialog import LoginDialog
from app.ui.main_window import MainWindow


def main():
    app = QApplication(sys.argv)
    # 마지막 창이 닫혀도 QApplication이 자동 종료되지 않도록 설정
    # (로그아웃 후 로그인 다이얼로그를 다시 띄우기 위해 필요)
    app.setQuitOnLastWindowClosed(False)
    settings = Settings()

    while True:
        # 로그인 다이얼로그
        api_client = APIClient(settings)
        login_dialog = LoginDialog(settings)
        if login_dialog.exec() != LoginDialog.DialogCode.Accepted:
            break

        # 로그인 성공: JWT 토큰 + username 반영
        api_client.set_token(login_dialog.token)
        settings.operator = login_dialog.username

        # 메인 윈도우 — 로컬 이벤트 루프로 닫힐 때까지 대기
        window = MainWindow(settings, api_client, username=login_dialog.username)
        loop = QEventLoop()
        window.window_closed.connect(loop.quit)
        window.show()
        loop.exec()

        # 로그아웃이 아니라 창을 직접 닫은 경우 → 앱 종료
        if not window.is_logout:
            break

    sys.exit(0)


if __name__ == "__main__":
    main()
