import traceback
from PyQt6.QtCore import QObject, QThread, pyqtSignal, pyqtSlot
from validator.engine import validate_archives
from validator.config import Settings
from validator.models import Issue, ValidationResult


class ValidationWorker(QObject):
    progress = pyqtSignal(str)
    completed = pyqtSignal(object)
    finished = pyqtSignal()

    def __init__(self, data_path, key_path, settings):
        super().__init__()
        self.data_path, self.key_path, self.settings = data_path, key_path, settings

    @pyqtSlot()
    def run(self):
        try:
            result = validate_archives(self.data_path, self.key_path, self.settings,
                                       self.progress.emit, QThread.currentThread().isInterruptionRequested)
        except Exception as exc:
            result = ValidationResult(issues=[Issue(
                "INTERNAL", "ERROR",
                f"Validation could not finish: {type(exc).__name__}: {exc}",
                details=traceback.format_exc(),
            )])
        self.completed.emit(result)
        self.finished.emit()


class ValidationController(QObject):
    def __init__(self, window, settings=None):
        super().__init__(window)
        self.window = window
        self.settings = settings or Settings()
        self.thread = None
        self.worker = None
        window.submit_requested.connect(self.start)
        window.cancel_requested.connect(self.cancel)

    def start(self, data_path, key_path):
        if self.thread is not None:
            return
        if data_path is None:
            self.window.show_result(ValidationResult(issues=[Issue("FILE", "ERROR", "Select the validation ZIP first.")]))
            return
        self.window.clear_console()
        self.window.set_busy(True)
        self.thread = QThread(self)
        self.worker = ValidationWorker(data_path, key_path, self.settings)
        self.worker.moveToThread(self.thread)
        self.thread.started.connect(self.worker.run)
        self.worker.progress.connect(self.window.show_progress)
        self.worker.completed.connect(self.window.show_result)
        self.worker.finished.connect(self.thread.quit)
        self.worker.finished.connect(self.worker.deleteLater)
        self.thread.finished.connect(self.thread_finished)
        self.thread.start()

    def cancel(self):
        if self.thread is not None:
            self.thread.requestInterruption()
            self.window.show_progress("Cancelling after the current validation rule…")

    def thread_finished(self):
        thread = self.thread
        self.thread = None
        self.worker = None
        if thread is not None:
            thread.deleteLater()
        self.window.set_busy(False)
