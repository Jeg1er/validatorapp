"""Run the desktop application: python main.py."""
import sys
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import QApplication
from ui.main_window import MainWindow
from ui.controller import ValidationController

import traceback

from PyQt6.QtCore import QThread
from PyQt6.QtWidgets import QMessageBox


def report_exception(error_type, error_value, error_traceback):
    text = "".join(
        traceback.format_exception(
            error_type, error_value, error_traceback
        )
    )
    print(text, file=sys.stderr, flush=True)

    app = QApplication.instance()

    if app is not None and QThread.currentThread() == app.thread():
        QMessageBox.critical(None, "Ошибка программы", text)


sys.excepthook = report_exception

def main():
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    app.setFont(QFont("Arial", 10))
    window = MainWindow(demo="--demo" in sys.argv)
    window.controller = ValidationController(window)
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
