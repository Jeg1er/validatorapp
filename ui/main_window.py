from __future__ import annotations
from pathlib import Path
from PyQt6.QtCore import Qt, QUrl, pyqtSignal
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (
    QDialog, QFileDialog, QFrame, QGraphicsDropShadowEffect, QHBoxLayout, QLabel,
    QMainWindow, QMessageBox, QPushButton, QVBoxLayout, QWidget,
)
from validator.models import Cell, Issue, Table, ValidationResult
from .console import ConsoleView, console_html
from .file_drop import FileDropBox
from .styles import APP_STYLE
from .table_dialog import IssueTableDialog


class MainWindow(QMainWindow):
    def open_product_search(self):
        import traceback

        try:
            print("SEARCH_STAGE_1: button clicked", flush=True)

            if self.busy:
                return

            if (
                self.zip_drop.path is None
                or self.key_drop.path is None
            ):
                QMessageBox.warning(
                    self,
                    "Product search",
                    "Выберите основной ZIP и ZIP-ключ.",
                )
                return

            from product_search.dialog import ProductSearchDialog

            print("SEARCH_STAGE_2: module imported", flush=True)

            controller = getattr(self, "controller", None)
            settings = getattr(controller, "settings", None)

            dialog = ProductSearchDialog(
                data_path=self.zip_drop.path,
                key_path=self.key_drop.path,
                settings=settings,
                parent=self,
            )

            print("SEARCH_STAGE_3: window created", flush=True)

            dialog.exec()

        except Exception:
            error = traceback.format_exc()
            print(error, flush=True)

            QMessageBox.critical(
                self,
                "search open error",
                error,
            )
    submit_requested = pyqtSignal(object, object)
    cancel_requested = pyqtSignal()

    def __init__(self, demo=False):
        super().__init__()
        self.setWindowTitle("Exchange file validation")
        self.resize(1133, 627)
        self.setMinimumSize(900, 580)
        self.result = ValidationResult()
        self.messages = self.result.issues
        self.busy = False
        self.progress_text = ""
        self.summary = ""
        self.console_dialog = None
        self.expanded_console = None
        self.table_dialogs = []
        self.setStyleSheet(APP_STYLE)
        root = QWidget()
        root.setObjectName("background")
        self.setCentralWidget(root)
        layout = QHBoxLayout(root)
        layout.setContentsMargins(52, 41, 55, 40)
        layout.setSpacing(36)

        left = self.make_card()
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(24, 27, 24, 45)
        left_layout.setSpacing(0)
        self.zip_drop = FileDropBox(".zip", "Click to select files, or drag and drop")
        self.zip_drop.setMinimumHeight(290)
        left_layout.addWidget(self.zip_drop, 1)
        left_layout.addSpacing(56)
        self.submit_button = QPushButton("Submit")
        self.submit_button.setObjectName("submit")
        self.submit_button.setFixedHeight(83)
        self.submit_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.submit_button.setToolTip("Select a validation ZIP to enable Submit; the key ZIP is optional")
        self.submit_button.setEnabled(False)
        self.submit_button.clicked.connect(self.on_submit)
        self.search_button = QPushButton("Search")
        self.search_button.setObjectName("submit")
        self.search_button.setFixedHeight(83)
        self.search_button.setEnabled(False)
        self.search_button.setCursor(
            Qt.CursorShape.PointingHandCursor
        )
        self.search_button.clicked.connect(
            self.open_product_search
        )

        actions = QHBoxLayout()
        actions.setSpacing(12)
        actions.addWidget(self.submit_button, 1)
        actions.addWidget(self.search_button, 1)

        left_layout.addLayout(actions)
        layout.addWidget(left, 414)

        right = QVBoxLayout()
        right.setSpacing(12)
        key_card = self.make_card()
        key_card.setFixedHeight(184)
        key_layout = QHBoxLayout(key_card)
        key_layout.setContentsMargins(28, 25, 28, 25)
        key_layout.setSpacing(35)
        self.key_drop = FileDropBox(".zip")
        self.key_drop.setFixedSize(142, 134)
        key_layout.addWidget(self.key_drop)
        title = QLabel("Add a key file which\nrepresents client’s TS")
        title.setObjectName("keyTitle")
        title.setWordWrap(True)
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        key_layout.addWidget(title, 1)
        right.addWidget(key_card)

        console_card = self.make_card()
        console_layout = QVBoxLayout(console_card)
        console_layout.setContentsMargins(0, 0, 0, 14)
        console_layout.setSpacing(0)
        header = QHBoxLayout()
        header.setSpacing(0)
        badge = QLabel("CONSOLE")
        badge.setObjectName("consoleBadge")
        badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        badge.setFixedSize(217, 35)
        header.addWidget(badge)
        header.addStretch()
        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.setVisible(False)
        self.cancel_button.clicked.connect(self.cancel_requested.emit)
        header.addWidget(self.cancel_button)
        self.expand_button = QPushButton("↗")
        self.expand_button.setObjectName("expand")
        self.expand_button.setFixedSize(57, 35)
        self.expand_button.setAccessibleName("Expand console")
        self.expand_button.setToolTip("Open console in a separate window")
        self.expand_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.expand_button.clicked.connect(self.expand_console)
        header.addWidget(self.expand_button)
        console_layout.addLayout(header)
        self.console = ConsoleView()
        self.console.anchorClicked.connect(self.open_message)
        inset = QHBoxLayout()
        inset.setContentsMargins(19, 0, 19, 0)
        inset.addWidget(self.console)
        console_layout.addLayout(inset, 1)
        right.addWidget(console_card, 1)
        layout.addLayout(right, 576)

        for box in (self.zip_drop, self.key_drop):
            box.file_selected.connect(self.file_changed)
            box.rejected.connect(self.reject_file)
        QWidget.setTabOrder(self.zip_drop, self.key_drop)
        QWidget.setTabOrder(self.key_drop, self.submit_button)
        QWidget.setTabOrder(self.submit_button, self.expand_button)
        if demo:
            table = Table("demo", "dimensions_example.csv", "dimensions",
                          [["item_uid", "width", "height", "depth"], ["1001", "0", "20", "15"], ["1002", "abc", "30", "10"]],
                          [1, 2, 3], ";", "utf-8")
            self.result.tables[table.id] = table
            self.messages.extend([
                Issue("K", "WARNING", "Style example: zero dimension.", [Cell("demo", 1, 1)], item_uid="1001"),
                Issue("I", "ERROR", "Style example: invalid numeric value.", [Cell("demo", 2, 1)], item_uid="1002"),
            ])
            self.summary = "Design examples only — not validation results."
        self.render_console()

    def make_card(self):
        card = QFrame()
        card.setObjectName("card")
        effect = QGraphicsDropShadowEffect(card)
        effect.setBlurRadius(22)
        effect.setOffset(4, 14)
        effect.setColor(QColor(0, 0, 0, 65))
        card.setGraphicsEffect(effect)
        return card

    def file_changed(self, path):
        if not self.busy:
            self.clear_console()
        self.update_submit_state()

    def reject_file(self, text):
        QMessageBox.warning(self, "File selection", text)

    def update_submit_state(self):
        ready = self.zip_drop.path is not None and not self.busy
        self.submit_button.setEnabled(ready)
        self.search_button.setEnabled(ready and self.key_drop.path is not None)
        self.submit_button.setToolTip(
            "Validate selected files; the key ZIP is optional"
            if ready else "Select a validation ZIP to enable Submit"
        )

    def on_submit(self):
        if not self.busy and self.zip_drop.path is not None:
            self.submit_requested.emit(self.zip_drop.path, self.key_drop.path)
    
    def set_busy(self, busy):
        self.busy = busy
        self.zip_drop.setEnabled(not busy)
        self.key_drop.setEnabled(not busy)
        self.cancel_button.setVisible(busy)
        self.submit_button.setText("Working…" if busy else "Submit")
        self.update_submit_state()

    def show_progress(self, text):
        self.progress_text = text
        self.render_console()

    def show_result(self, result):
        self.result = result
        self.messages = result.issues
        self.progress_text = ""
        prefix = "Cancelled — partial results. " if result.cancelled else "Validation finished. "
        self.summary = prefix + f"Errors: {result.error_count}; warnings: {result.warning_count}."
        self.render_console()

    def clear_console(self):
        for dialog in list(self.table_dialogs):
            dialog.close()
        self.table_dialogs.clear()
        self.result = ValidationResult()
        self.messages = self.result.issues
        self.progress_text = ""
        self.summary = ""
        self.render_console()

    def render_console(self):
        document = console_html(self.messages, self.progress_text, self.summary, self.result)
        views = [self.console] + ([self.expanded_console] if self.expanded_console is not None else [])
        for view in views:
            view.setHtml(document)
            frame = view.document().rootFrame()
            fmt = frame.frameFormat()
            fmt.setTopMargin(4)
            frame.setFrameFormat(fmt)
            if view is self.console:
                margin = max(0, view.viewport().height() - view.document().size().height() - 2)
                fmt.setTopMargin(4 + margin)
                frame.setFrameFormat(fmt)
            view.verticalScrollBar().setValue(view.verticalScrollBar().maximum())

    def open_message(self, url):
        if url.scheme() != "issue":
            return
        try:
            index = int(url.path())
            if index < 0:
                return
            issue = self.messages[index]
        except (ValueError, IndexError):
            return
        dialog = IssueTableDialog(self.result, issue, self)
        self.table_dialogs.append(dialog)
        dialog.finished.connect(lambda code: self.release_dialog(dialog))
        dialog.show()

    def release_dialog(self, dialog):
        if dialog in self.table_dialogs:
            self.table_dialogs.remove(dialog)
        dialog.deleteLater()

    def expand_console(self):
        if self.console_dialog is not None:
            self.console_dialog.show()
            self.console_dialog.raise_()
            self.console_dialog.activateWindow()
            return
        self.console_dialog = QDialog(self)
        self.console_dialog.setWindowTitle("Console")
        self.console_dialog.resize(850, 550)
        layout = QVBoxLayout(self.console_dialog)
        self.expanded_console = ConsoleView()
        self.expanded_console.anchorClicked.connect(self.open_message)
        layout.addWidget(self.expanded_console)
        export = QPushButton("Save console as TXT")
        export.clicked.connect(self.save_console)
        layout.addWidget(export)
        self.render_console()
        self.console_dialog.show()

    def save_console(self):
        filename, _ = QFileDialog.getSaveFileName(self, "Save console", "console.txt", "Text files (*.txt)")
        if not filename:
            return
        try:
            lines = [self.summary] + [f"{issue.severity} [{issue.rule}]: {issue.text}" +
                    (f"; item_uid: {issue.item_uid}" if issue.item_uid else "") for issue in self.messages]
            Path(filename).write_text("\n".join(lines), encoding="utf-8", errors="backslashreplace")
        except OSError as exc:
            QMessageBox.critical(self, "Cannot save console", str(exc))

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, "console"):
            self.render_console()

    def closeEvent(self, event):
        if self.busy:
            self.cancel_requested.emit()
            QMessageBox.information(self, "Validation", "Cancellation requested. Close the window after the current rule finishes.")
            event.ignore()
        else:
            super().closeEvent(event)
