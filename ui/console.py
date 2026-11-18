import html
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QFrame, QTextBrowser
from .table_dialog import safe_text


class ConsoleView(QTextBrowser):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setOpenLinks(False)
        self.setOpenExternalLinks(False)
        self.setReadOnly(True)
        self.setAccessibleName("Validation console")
        self.setStyleSheet("QTextBrowser { background: #fbfbff; border-radius: 26px; padding: 16px; font: 11pt 'Arial'; }")


def console_html(issues, progress="", summary="", result=None):
    colors = {"INFO": "#888f94", "WARNING": "#ffad43", "ERROR": "#ff3636"}
    esc = lambda value: html.escape(safe_text(str(value)))
    rows = []
    if progress:
        rows.append(f"<p style='color:#888f94'>{esc(progress)}</p>")
    if summary:
        rows.append(f"<p style='color:#555'>{esc(summary)}</p>")
    for index, issue in enumerate(issues):
        color = colors.get(issue.severity, "#888f94")
        location = ""
        if result and issue.cells:
            cell = issue.cells[0]
            table = result.tables.get(cell.table_id)
            if table:
                physical = table.line_numbers[cell.row] if cell.row < len(table.line_numbers) else cell.row + 1
                location = f" (line {physical}, column {cell.column + 1})"
        uid = f' · item_uid: <a href="issue:{index}">{esc(issue.item_uid)}</a>' if issue.item_uid else ""
        link = f' - <a href="issue:{index}">link</a>' if issue.cells or issue.table_ids or issue.details else ""
        rows.append(f"<div><b style='color:{color}'>{esc(issue.severity)} [{esc(issue.rule)}]:</b> "
                    f"{esc(issue.text + location)}{uid}{link}</div>")
    return "<html><body style='color:#161616'>" + "".join(rows) + "</body></html>"
