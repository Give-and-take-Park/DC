import sys
from PyQt6.QtWidgets import QApplication, QMessageBox
from app.config.settings import Settings
from app.core.api_client import APIClient
from app.ui.login_dialog import LoginDialog
from app.ui.main_window import MainWindow


def main():
    app = QApplication(sys.argv)
    settings = Settings()
    api_client = APIClient(settings)

    # 로그인 다이얼로그 표시
    login_dialog = LoginDialog(settings)
    if login_dialog.exec() != LoginDialog.DialogCode.Accepted:
        sys.exit(0)

    # 로그인 성공: JWT 토큰 + username 반영
    api_client.set_token(login_dialog.token)
    settings.operator = login_dialog.username

    # 메인 윈도우 표시
    window = MainWindow(settings, api_client, username=login_dialog.username)
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
