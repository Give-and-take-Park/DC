from PyQt6.QtWidgets import QMainWindow


class MainWindow(QMainWindow):
    """메인 윈도우"""

    def __init__(self, settings):
        super().__init__()
        self.settings = settings
        self.setWindowTitle("DC Data Collector")
        self._init_ui()

    def _init_ui(self):
        # TODO: UI 구성 요소 초기화
        pass
