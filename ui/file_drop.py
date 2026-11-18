from __future__ import annotations
from pathlib import Path
from PyQt6.QtCore import Qt, pyqtSignal, QRectF
from PyQt6.QtGui import QColor, QPainter, QPen, QFont
from PyQt6.QtWidgets import QPushButton, QFileDialog, QSizePolicy
from .styles import GREEN


class FileDropBox(QPushButton):
    """Real button: mouse/Space/Enter opens Explorer; accepts one local file."""
    file_selected = pyqtSignal(object)
    rejected = pyqtSignal(str)

    def __init__(self, extension: str, title: str = "", parent=None):
        super().__init__(parent)
        self.extension = extension
        self.title = title
        self.path: Path | None = None
        self.dragging = False
        self.setObjectName("fileDropBox")
        self.setAcceptDrops(True)  # Enables Qt drag/drop events.
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setAccessibleName(f"Select one {extension.upper()} file")
        self.setToolTip(f"Click or press Enter to choose one {extension} file; you can also drag it here.")
        self.setStyleSheet("background: transparent; border: none;")
        self.clicked.connect(self.choose_file)  # Connect a function, not its result.

    def choose_file(self):
        start_dir = str(self.path.parent) if self.path else str(Path.home())
        filename, _ = QFileDialog.getOpenFileName(
            self, f"Select {self.extension.upper()} file", start_dir,
            f"{self.extension.upper()} files (*{self.extension});;All files (*)",
        )
        if filename:  # Cancel keeps the previous choice.
            self.set_file(Path(filename))

    def set_file(self, path: Path) -> bool:
        path = Path(path)
        if not path.is_file():
            self.rejected.emit("Choose an existing file, not a folder.")
            return False
        if path.suffix.lower() != self.extension:
            self.rejected.emit(f"Only one {self.extension} file is allowed in this area.")
            return False
        try:
            with path.open("rb"):
                pass
        except OSError as exc:
            self.rejected.emit(f"Cannot read the selected file: {exc}")
            return False
        self.path = path.resolve()
        self.setToolTip(str(self.path) + "\nClick to replace this file.")
        self.setAccessibleDescription(f"Selected: {self.path.name}")
        self.file_selected.emit(self.path)
        self.update()
        return True

    def _paths_from_event(self, event) -> list[Path]:
        if not event.mimeData().hasUrls():
            return []
        urls = event.mimeData().urls()
        if len(urls) != 1 or not urls[0].isLocalFile():
            return []
        return [Path(urls[0].toLocalFile())]

    def dragEnterEvent(self, event):
        paths = self._paths_from_event(event)
        if self.isEnabled() and paths and paths[0].is_file() and paths[0].suffix.lower() == self.extension:
            self.dragging = True
            event.acceptProposedAction()
            self.update()
        else:
            event.ignore()

    def dragLeaveEvent(self, event):
        self.dragging = False
        self.update()
        event.accept()

    def dropEvent(self, event):
        self.dragging = False
        paths = self._paths_from_event(event)
        if self.isEnabled() and paths and self.set_file(paths[0]):
            event.acceptProposedAction()
        else:
            event.ignore()
        self.update()

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self.choose_file()
        else:
            super().keyPressEvent(event)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        active = self.dragging or self.hasFocus() or self.underMouse()
        painter.setBrush(QColor("#f2faf2" if active else "#ffffff"))
        pen = QPen(QColor(GREEN if active or self.path else "#a7adb1"), 3)
        pen.setStyle(Qt.PenStyle.DashLine)
        painter.setPen(pen)
        radius = 32 if self.title else 20
        painter.drawRoundedRect(QRectF(self.rect()).adjusted(2, 2, -2, -2), radius, radius)
        area = self.rect().adjusted(10, 12, -10, -12)
        flags = Qt.AlignmentFlag.AlignCenter | Qt.TextFlag.TextWordWrap
        if self.path:
            painter.setPen(QColor(GREEN))
            painter.setFont(QFont("Arial", 12, QFont.Weight.Bold))
            # Elide very long names so they cannot spill past the drop zone.
            name = painter.fontMetrics().elidedText(self.path.name, Qt.TextElideMode.ElideMiddle, area.width())
            painter.drawText(area.adjusted(0, -16, 0, -16), flags, name)
            painter.setPen(QColor("#a7adb1"))
            painter.setFont(QFont("Arial", 10))
            painter.drawText(area.adjusted(0, 38, 0, 0), flags, "Click to replace")
        elif self.title:
            painter.setPen(QColor(GREEN))
            painter.setFont(QFont("Arial", 12, QFont.Weight.Bold))
            painter.drawText(area.adjusted(0, -17, 0, -17), flags, self.title)
            painter.setPen(QColor("#a7adb1"))
            painter.setFont(QFont("Arial", 10))
            painter.drawText(area.adjusted(0, 35, 0, 0), flags, f"Select 1 file with a {self.extension} format")
        else:
            painter.setPen(QColor("#a7adb1"))
            painter.setFont(QFont("Arial", 10))
            painter.drawText(area, flags, f"Select 1 file with a\n{self.extension} format")


