from __future__ import annotations
from PyQt6.QtCore import QAbstractTableModel, QModelIndex, QRegularExpression, QSortFilterProxyModel, Qt
from PyQt6.QtGui import QColor, QPen
from PyQt6.QtWidgets import (
    QAbstractItemView, QApplication, QDialog, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QTableView, QTabWidget, QVBoxLayout, QWidget, QStyledItemDelegate,
    QStyle, QStyleOptionViewItem,
)
from validator.models import Issue, Table, ValidationResult


def safe_text(text: str) -> str:
    return text.encode("utf-8", errors="backslashreplace").decode("utf-8")


class HighlightDelegate(QStyledItemDelegate):
    """Selection must not hide the yellow/red issue background."""
    def paint(self, painter, option, index):
        copy = QStyleOptionViewItem(option)
        selected = bool(copy.state & QStyle.StateFlag.State_Selected)
        copy.state &= ~QStyle.StateFlag.State_Selected
        super().paint(painter, copy, index)
        if selected:
            painter.save()
            painter.setPen(QPen(QColor("#3176ba"), 1))
            painter.drawRect(option.rect.adjusted(0, 0, -1, -1))
            painter.restore()


class CsvTableModel(QAbstractTableModel):
    """Shows every record without creating a widget per cell."""
    def __init__(self, table: Table, issues: list[Issue], focused: Issue, parent=None):
        super().__init__(parent)
        self.table = table
        self.highlights = {}
        self.reasons = {}
        for issue in issues:
            for cell in issue.cells:
                if cell.table_id != table.id:
                    continue
                position = (cell.row, cell.column)
                # When viewing a WARNING, its own cells must remain yellow
                # even if a different rule marked the same cell as an error.
                if issue is focused or position not in self.highlights:
                    self.highlights[position] = issue.severity
                self.reasons.setdefault(position, []).append(f"[{issue.rule}] {issue.text}")
        self.columns = max([1] + [len(row) for row in table.records] +
                           [column + 1 for _, column in self.highlights])
        self.rows = max([1, len(table.records)] + [row + 1 for row, _ in self.highlights])

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else self.rows

    def columnCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else self.columns

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None
        row, column = index.row(), index.column()
        if role == Qt.ItemDataRole.DisplayRole:
            if row >= len(self.table.records):
                return "" if self.table.records else "(empty file)" if column == 0 else ""
            record = self.table.records[row]
            return safe_text(record[column]) if column < len(record) else "(missing field)"
        if role == Qt.ItemDataRole.BackgroundRole:
            severity = self.highlights.get((row, column))
            if severity:
                return QColor("#fff1a8" if severity == "WARNING" else "#ffc6c6")
        if role == Qt.ItemDataRole.ToolTipRole:
            reasons = self.reasons.get((row, column), [])
            value = self.data(index, Qt.ItemDataRole.DisplayRole)
            return safe_text(value + ("\n\n" + "\n".join(reasons) if reasons else ""))
        if role == Qt.ItemDataRole.UserRole:
            return row
        return None

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):
        if role != Qt.ItemDataRole.DisplayRole:
            return None
        if orientation == Qt.Orientation.Horizontal:
            name = self.table.headers[section] if section < len(self.table.headers) else "extra / missing column"
            return f"{section + 1}: {safe_text(name)}"
        line = self.table.line_numbers[section] if section < len(self.table.line_numbers) else section + 1
        return str(line)


class TablePane(QWidget):
    def __init__(self, table: Table, result: ValidationResult, issue: Issue, parent=None):
        super().__init__(parent)
        self.table_data = table
        self.issue = issue
        self.positions = sorted({(cell.row, cell.column) for cell in issue.cells if cell.table_id == table.id})
        self.position_index = -1
        layout = QVBoxLayout(self)
        delimiter = {"\t": "TAB"}.get(table.delimiter, table.delimiter)
        info = QLabel(f"{table.filename} · encoding: {table.encoding} · delimiter: {delimiter!r} · "
                      f"data records: {max(0, len(table.records) - 1)}")
        info.setTextFormat(Qt.TextFormat.PlainText)
        layout.addWidget(info)
        search = QLineEdit()
        search.setPlaceholderText("Filter the full table…")
        layout.addWidget(search)
        self.search = search
        self.model = CsvTableModel(table, result.issues, issue, self)
        self.proxy = QSortFilterProxyModel(self)
        self.proxy.setSourceModel(self.model)
        self.proxy.setFilterKeyColumn(-1)
        self.proxy.setFilterCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        search.textChanged.connect(lambda text: self.proxy.setFilterRegularExpression(
            QRegularExpression(QRegularExpression.escape(text), QRegularExpression.PatternOption.CaseInsensitiveOption)))
        self.view = QTableView()
        self.view.setModel(self.proxy)
        self.view.setItemDelegate(HighlightDelegate(self.view))
        self.view.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.view.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.view.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectItems)
        self.view.setSortingEnabled(True)
        self.view.sortByColumn(-1, Qt.SortOrder.AscendingOrder)
        self.view.horizontalHeader().setDefaultSectionSize(180)
        self.view.verticalHeader().setDefaultSectionSize(28)
        self.view.setStyleSheet("QTableView { background: white; color: #222; }")
        layout.addWidget(self.view, 1)
        controls = QHBoxLayout()
        previous = QPushButton("Previous issue cell")
        following = QPushButton("Next issue cell")
        copy = QPushButton("Copy selected cells")
        previous.clicked.connect(lambda: self.navigate(-1))
        following.clicked.connect(lambda: self.navigate(1))
        copy.clicked.connect(self.copy_selection)
        previous.setEnabled(bool(self.positions))
        following.setEnabled(bool(self.positions))
        controls.addWidget(previous)
        controls.addWidget(following)
        controls.addWidget(copy)
        layout.addLayout(controls)
        if self.positions:
            self.navigate(1)

    def navigate(self, direction):
        if not self.positions:
            return
        self.position_index = (self.position_index + direction) % len(self.positions)
        row, column = self.positions[self.position_index]
        source = self.model.index(row, column)
        index = self.proxy.mapFromSource(source)
        if not index.isValid():
            self.search.clear()
            index = self.proxy.mapFromSource(source)
        self.view.setCurrentIndex(index)
        self.view.scrollTo(index, QAbstractItemView.ScrollHint.PositionAtCenter)

    def copy_selection(self):
        indices = self.view.selectionModel().selectedIndexes()
        rows = {}
        for index in indices:
            rows.setdefault(index.row(), {})[index.column()] = str(index.data() or "")
        text = "\n".join("\t".join(values.get(column, "") for column in range(min(values), max(values) + 1))
                         for _, values in sorted(rows.items()))
        QApplication.clipboard().setText(text)


class IssueTableDialog(QDialog):
    def __init__(self, result: ValidationResult, issue: Issue, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"[{issue.rule}] {issue.severity} — validation details")
        self.resize(1100, 650)
        self.setMinimumSize(750, 430)
        layout = QVBoxLayout(self)
        title = QLabel(f"[{issue.rule}] {issue.text}")
        title.setTextFormat(Qt.TextFormat.PlainText)
        title.setWordWrap(True)
        layout.addWidget(title)
        if issue.details:
            details = QLabel(safe_text(issue.details))
            details.setTextFormat(Qt.TextFormat.PlainText)
            details.setWordWrap(True)
            layout.addWidget(details)
        ids = list(dict.fromkeys([cell.table_id for cell in issue.cells] + issue.table_ids))
        self.tabs = QTabWidget()
        self.panes = []
        for table_id in ids:
            if table_id in result.tables:
                table = result.tables[table_id]
                pane = TablePane(table, result, issue, self)
                self.panes.append(pane)
                self.tabs.addTab(pane, f"{table.source}: {table.filename}")
        if self.panes:
            layout.addWidget(self.tabs, 1)
        else:
            empty = QLabel("This issue concerns the archive/settings; there is no CSV cell to show.")
            layout.addWidget(empty, 1)
        close = QPushButton("Close")
        close.clicked.connect(self.accept)
        layout.addWidget(close)
