from __future__ import annotations
from validator.config import Settings
from validator.key_cleanup import clean_key_archive

import csv
from pathlib import Path

from PyQt6.QtCore import (
    QAbstractTableModel, QModelIndex, QSortFilterProxyModel,
    QThread, Qt, pyqtSignal,
)
from PyQt6.QtWidgets import (
    QAbstractItemView, QButtonGroup, QDialog, QDialogButtonBox,
    QFileDialog, QFrame, QHBoxLayout, QLabel, QLineEdit,
    QListWidget, QListWidgetItem, QMessageBox, QPlainTextEdit,
    QPushButton, QTableView, QVBoxLayout,
)

from .service import ProductIndex, SearchErrors, archive_signature


# Exact text requested for the status square.
ERROR_TILE_TEMPLATE = "{count} errors  occured"


def display_text(value):
    return str(value).encode("utf-8", errors="backslashreplace").decode("utf-8")


class SearchWorker(QThread):
    progress = pyqtSignal(str)
    ready = pyqtSignal(object)
    failed = pyqtSignal(object)  # A list of individual error messages.
    cancelled = pyqtSignal()

    def __init__(self, data_path, key_path, mode, query, settings,
                 cached_index=None, cached_signature=None, parent=None):
        super().__init__(parent)
        self.data_path = Path(data_path)
        self.key_path = Path(key_path)
        self.mode = mode
        self.query = query
        self.settings = settings
        self.index = cached_index
        self.signature = cached_signature

    def run(self):
        try:
            self.progress.emit("Checking archives...")
            if self.data_path.samefile(self.key_path):
                raise SearchErrors([
                    "The data archive and key archive must be different files."
                ])

            self.progress.emit("Cleaning key archive...")
            cleanup = clean_key_archive(
                self.key_path,
                self.settings or Settings(),
                self.isInterruptionRequested,
            )
            if cleanup.removed:
                self.progress.emit(
                    f"Removed {len(cleanup.removed)} key file(s)"
                )
            signature = archive_signature(self.data_path, self.key_path)
            if self.index is None or self.signature != signature:
                self.index = ProductIndex(
                    self.data_path, self.key_path, self.settings,
                    cancelled=self.isInterruptionRequested,
                    progress=self.progress.emit,
                )
                if archive_signature(self.data_path, self.key_path) != signature:
                    raise SearchErrors([
                        "An archive changed while it was being read. Run the search again."
                    ])
                self.signature = signature
            else:
                self.progress.emit("Using cached data...")

            result = self.index.search(
                self.mode, self.query,
                cancelled=self.isInterruptionRequested,
                progress=self.progress.emit,
            )
            if self.isInterruptionRequested():
                raise InterruptedError("Search cancelled.")
            self.ready.emit(result)
        except InterruptedError:
            self.cancelled.emit()
        except SearchErrors as error:
            self.failed.emit(list(error.errors))
        except Exception as error:
            self.failed.emit([f"{type(error).__name__}: {display_text(error)}"])


class ResultModel(QAbstractTableModel):
    def __init__(self, result, parent=None):
        super().__init__(parent)
        self.headers = result.headers
        self.rows = result.rows

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self.rows)

    def columnCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self.headers)

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None
        if role in (Qt.ItemDataRole.DisplayRole, Qt.ItemDataRole.ToolTipRole):
            return display_text(self.rows[index.row()][index.column()])
        return None

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):
        if role != Qt.ItemDataRole.DisplayRole:
            return None
        if orientation == Qt.Orientation.Horizontal:
            return self.headers[section]
        return str(section + 1)


class ValueFilterProxy(QSortFilterProxyModel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.filters = {}

    def filterAcceptsRow(self, source_row, source_parent):
        row = self.sourceModel().rows[source_row]
        return all(row[column] in values for column, values in self.filters.items())

    def set_values(self, column, values):
        if values is None:
            self.filters.pop(column, None)
        else:
            self.filters[column] = set(values)
        self.invalidateFilter()

    def clear_filters(self):
        self.filters.clear()
        self.invalidateFilter()

    def available_values(self, column):
        values = set()
        for row in self.sourceModel().rows:
            if all(row[other_column] in allowed
                   for other_column, allowed in self.filters.items()
                   if other_column != column):
                values.add(row[column])
        return sorted(values, key=lambda value: (value.casefold(), value))


class ValuesDialog(QDialog):
    def __init__(self, title, values, selected, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"Filter: {title}")
        self.resize(380, 480)
        self.selected_values = None
        layout = QVBoxLayout(self)
        self.search = QLineEdit()
        self.search.setPlaceholderText("Search values…")
        self.search.textChanged.connect(self.filter_list)
        layout.addWidget(self.search)
        self.list_widget = QListWidget()
        layout.addWidget(self.list_widget, 1)

        for value in values:
            item = QListWidgetItem("(empty)" if value == "" else display_text(value))
            item.setData(Qt.ItemDataRole.UserRole, value)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Checked
                               if selected is None or value in selected
                               else Qt.CheckState.Unchecked)
            self.list_widget.addItem(item)

        selection_buttons = QHBoxLayout()
        select_all = QPushButton("Select visible")
        clear_all = QPushButton("Uncheck visible")
        select_all.clicked.connect(lambda: self.set_visible_checked(True))
        clear_all.clicked.connect(lambda: self.set_visible_checked(False))
        selection_buttons.addWidget(select_all)
        selection_buttons.addWidget(clear_all)
        layout.addLayout(selection_buttons)
        remove_filter = QPushButton("Remove this filter")
        remove_filter.clicked.connect(self.remove_filter)
        layout.addWidget(remove_filter)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok
                                  | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.apply_filter)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def filter_list(self, text):
        text = text.casefold()
        for position in range(self.list_widget.count()):
            item = self.list_widget.item(position)
            value = item.data(Qt.ItemDataRole.UserRole)
            item.setHidden(text not in value.casefold())

    def set_visible_checked(self, checked):
        state = Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked
        for position in range(self.list_widget.count()):
            item = self.list_widget.item(position)
            if not item.isHidden():
                item.setCheckState(state)

    def remove_filter(self):
        self.selected_values = None
        self.accept()

    def apply_filter(self):
        selected = set()
        for position in range(self.list_widget.count()):
            item = self.list_widget.item(position)
            if item.checkState() == Qt.CheckState.Checked:
                selected.add(item.data(Qt.ItemDataRole.UserRole))
        self.selected_values = None if len(selected) == self.list_widget.count() else selected
        self.accept()


class ConsolidatedTableDialog(QDialog):
    def __init__(self, result, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Consolidated data")
        self.resize(1100, 650)
        layout = QVBoxLayout(self)
        hint = QLabel("Filter values: right-click a column header. Sort: left-click a header.")
        hint.setWordWrap(True)
        layout.addWidget(hint)
        self.model = ResultModel(result, self)
        self.proxy = ValueFilterProxy(self)
        self.proxy.setSourceModel(self.model)
        self.table = QTableView()
        self.table.setModel(self.proxy)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.table.setAlternatingRowColors(True)
        self.table.setSortingEnabled(True)
        self.table.sortByColumn(-1, Qt.SortOrder.AscendingOrder)
        header = self.table.horizontalHeader()
        header.setDefaultSectionSize(180)
        header.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        header.customContextMenuRequested.connect(self.open_column_filter)
        layout.addWidget(self.table, 1)
        self.counter = QLabel()
        layout.addWidget(self.counter)
        actions = QHBoxLayout()
        reset = QPushButton("Reset filters")
        download = QPushButton("Download CSV")
        close = QPushButton("Close")
        reset.clicked.connect(self.reset_filters)
        download.clicked.connect(self.export_csv)
        close.clicked.connect(self.accept)
        actions.addWidget(reset)
        actions.addStretch()
        actions.addWidget(download)
        actions.addWidget(close)
        layout.addLayout(actions)
        self.update_counter()

    def open_column_filter(self, position):
        column = self.table.horizontalHeader().logicalIndexAt(position)
        if column < 0:
            return
        dialog = ValuesDialog(self.model.headers[column],
                              self.proxy.available_values(column),
                              self.proxy.filters.get(column), self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.proxy.set_values(column, dialog.selected_values)
            self.update_counter()

    def reset_filters(self):
        self.proxy.clear_filters()
        self.update_counter()

    def update_counter(self):
        filtered = [self.model.headers[column] for column in self.proxy.filters]
        text = f"Table rows: {self.proxy.rowCount()} of {self.model.rowCount()}"
        if filtered:
            text += " | Filters: " + ", ".join(filtered)
        self.counter.setText(text)

    def export_csv(self):
        filename, _ = QFileDialog.getSaveFileName(
            self, "Save consolidated data", "consolidated.csv", "CSV files (*.csv)")
        if not filename:
            return
        if not filename.lower().endswith(".csv"):
            filename += ".csv"
        try:
            with open(filename, "w", encoding="utf-8-sig",
                      errors="backslashreplace", newline="") as stream:
                writer = csv.writer(stream, delimiter=";")
                writer.writerow(self.model.headers)
                for row in range(self.proxy.rowCount()):
                    source = self.proxy.mapToSource(self.proxy.index(row, 0))
                    writer.writerow(self.model.rows[source.row()])
        except OSError as error:
            QMessageBox.critical(self, "Export error", display_text(error))


class SearchErrorsDialog(QDialog):
    """One numbered entry per search error."""

    def __init__(self, errors, parent=None):
        super().__init__(parent)
        self.errors = list(errors)
        self.setWindowTitle(f"Search errors ({len(self.errors)})")
        self.resize(850, 460)
        layout = QVBoxLayout(self)
        heading = QLabel(f"Search could not finish. Errors: {len(self.errors)}")
        layout.addWidget(heading)
        self.details = QPlainTextEdit()
        self.details.setReadOnly(True)
        self.details.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        lines = []
        for number, error in enumerate(self.errors, 1):
            message = " ".join(display_text(error).splitlines())
            lines.append(f"{number}. {message}")
        self.details.setPlainText("\n".join(lines))
        layout.addWidget(self.details, 1)
        buttons = QHBoxLayout()
        copy = QPushButton("Copy errors")
        close = QPushButton("Close")
        copy.clicked.connect(self.copy_errors)
        close.clicked.connect(self.accept)
        buttons.addWidget(copy)
        buttons.addStretch()
        buttons.addWidget(close)
        layout.addLayout(buttons)

    def copy_errors(self):
        self.details.selectAll()
        self.details.copy()


class ProductSearchDialog(QDialog):
    def __init__(self, data_path, key_path, settings=None, parent=None):
        super().__init__(parent)
        self.data_path = Path(data_path)
        self.key_path = Path(key_path)
        self.settings = settings
        self.worker = None
        self.cached_index = None
        self.cached_signature = None
        self.result = None
        self.search_errors = []
        self.closing = False

        self.setWindowTitle("Product search")
        self.resize(815, 536)
        self.setMinimumSize(740, 480)
        self.setStyleSheet("""
            QDialog { background: #f9fafc; }
            QFrame#searchCard { background: white; border-radius: 45px; }
            QLineEdit#searchInput { background: #fcfcff; color: #171717;
                border: 1px solid #171717; border-radius: 36px;
                padding: 0 20px; font: 16pt Arial; }
            QPushButton#searchMode { background: #a7adb1; color: white;
                border: none; border-radius: 22px; font: bold 13pt Arial; }
            QPushButton#searchMode:checked { background: #4bb14e; }
            QPushButton#searchGo { background: #4bb14e; color: white;
                border: none; border-radius: 34px; font: bold 23pt Arial; }
            QPushButton#searchGo:disabled { background: #afd4b0; }
            QPushButton#showData { background: white; color: #4bb14e;
                border: 3px solid #a7adb1; border-radius: 25px; font: bold 13pt Arial; }
            QPushButton#showData[status="idle"],
            QPushButton#showData[status="working"] { color: #8e969c; }
            QPushButton#showData[status="error"] { color: #e53935; }
            QPushButton#showData[status="success"] { color: #4bb14e; }
        """)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(52, 46, 40, 42)
        card = QFrame()
        card.setObjectName("searchCard")
        outer.addWidget(card)
        layout = QVBoxLayout(card)
        layout.setContentsMargins(24, 26, 24, 24)
        layout.setSpacing(20)
        self.input = QLineEdit()
        self.input.setObjectName("searchInput")
        self.input.setMinimumHeight(74)
        self.input.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.input.setPlaceholderText("Provide UID, barcode or name of an item")
        self.input.textChanged.connect(self.invalidate_result)
        self.input.returnPressed.connect(self.start_search)
        layout.addWidget(self.input)
        content = QHBoxLayout()
        content.setSpacing(55)
        layout.addLayout(content, 1)
        left = QVBoxLayout()
        left.setSpacing(13)
        content.addLayout(left, 1)
        self.modes = QButtonGroup(self)
        self.modes.setExclusive(True)
        for title, mode in (("BARCODE", "barcode"), ("UID", "uid"), ("NAME", "name")):
            button = QPushButton(title)
            button.setObjectName("searchMode")
            button.setCheckable(True)
            button.setMinimumHeight(43)
            button.setProperty("search_mode", mode)
            self.modes.addButton(button)
            button.clicked.connect(self.invalidate_result)
            left.addWidget(button)
            if mode == "uid":
                button.setChecked(True)
        self.go = QPushButton("Search")
        self.go.setObjectName("searchGo")
        self.go.setMinimumHeight(88)
        self.go.clicked.connect(self.start_search)
        left.addWidget(self.go)
        left.addStretch()
        self.show_data = QPushButton()
        self.show_data.setObjectName("showData")
        self.show_data.setMinimumSize(248, 235)
        self.show_data.clicked.connect(self.open_result)
        content.addWidget(self.show_data, 1, Qt.AlignmentFlag.AlignVCenter)
        # Processing statuses now live in the square, without a separate log label.
        self.invalidate_result()

    def set_tile(self, text, state="idle", clickable=False):
        self.show_data.setText(text)
        self.show_data.setProperty("status", state)
        self.show_data.setEnabled(clickable)
        self.show_data.setCursor(Qt.CursorShape.PointingHandCursor
                                 if clickable else Qt.CursorShape.ArrowCursor)
        self.show_data.setAccessibleName(text)
        self.show_data.setToolTip(text)
        style = self.show_data.style()
        style.unpolish(self.show_data)
        style.polish(self.show_data)
        self.show_data.update()

    def invalidate_result(self, *_):
        self.result = None
        self.search_errors = []
        self.set_tile("no data do find")
        self.go.setEnabled(bool(self.input.text().strip()) and self.worker is None)

    def set_busy(self, busy):
        self.input.setEnabled(not busy)
        for button in self.modes.buttons():
            button.setEnabled(not busy)
        self.go.setText("Searching…" if busy else "Search")
        self.go.setEnabled(not busy and bool(self.input.text().strip()))

    def start_search(self):
        query = self.input.text().strip()
        if not query or self.worker is not None:
            return
        mode = self.modes.checkedButton().property("search_mode")
        self.invalidate_result()
        self.set_busy(True)
        self.set_tile("Checking archives...", "working")
        self.worker = SearchWorker(
            self.data_path, self.key_path, mode, query, self.settings,
            self.cached_index, self.cached_signature, self,
        )
        self.worker.progress.connect(self.show_progress)
        self.worker.ready.connect(self.search_ready)
        self.worker.failed.connect(self.search_failed)
        self.worker.cancelled.connect(self.search_cancelled)
        self.worker.finished.connect(self.search_finished)
        self.worker.start()

    def show_progress(self, text):
        if not self.closing and not self.search_errors:
            self.set_tile(text, "working")

    def search_ready(self, result):
        if self.closing:
            return
        self.cached_index = self.worker.index
        self.cached_signature = self.worker.signature
        self.result = result
        self.search_errors = []
        if not result.rows:
            self.set_tile("No matches found")
            return
        self.set_tile("show consolidated data", "success", True)
        self.show_data.setToolTip(
            f"Items found: {len(result.item_uids)}. Related records: {result.record_count}."
        )

    def search_failed(self, errors):
        if self.closing:
            return
        entries = [errors] if isinstance(errors, str) else list(errors)
        self.result = None
        self.search_errors = [display_text(error) for error in entries if str(error).strip()]
        if not self.search_errors:
            self.search_errors = ["An unknown search error occurred."]
        self.set_tile(ERROR_TILE_TEMPLATE.format(count=len(self.search_errors)), "error", True)

    def search_cancelled(self):
        if not self.closing:
            self.set_tile("Search cancelled")

    def search_finished(self):
        worker = self.worker
        self.worker = None
        if worker is not None:
            worker.deleteLater()
        self.set_busy(False)
        if self.closing:
            super().reject()

    def open_result(self):
        if self.search_errors:
            SearchErrorsDialog(self.search_errors, self).exec()
        elif self.result is not None and self.result.rows:
            ConsolidatedTableDialog(self.result, self).exec()

    def reject(self):
        if self.worker is not None and self.worker.isRunning():
            self.closing = True
            self.worker.requestInterruption()
            self.set_tile("Cancelling...", "working")
            return
        super().reject()

    def closeEvent(self, event):
        if self.worker is not None and self.worker.isRunning():
            event.ignore()
            self.reject()
        else:
            super().closeEvent(event)
