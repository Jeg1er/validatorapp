import unittest
from pathlib import Path

from PyQt6.QtCore import Qt, QUrl
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication

from ui.controller import ValidationController
from ui.main_window import MainWindow
from ui.table_dialog import CsvTableModel, IssueTableDialog
from validator.config import Settings
from validator.models import Cell, Issue, Table, ValidationResult


class GuiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def make_result(self):
        table = Table("data:0", "dimensions_a.csv", "dimensions",
                      [["item_uid", "width"], ["001", "0"], ["002", "bad"]], [1, 2, 3], ";", "utf-8")
        warning = Issue("K", "WARNING", "Zero dimension.", [Cell(table.id, 1, 1)], item_uid="001")
        error = Issue("I", "ERROR", "Not numeric.", [Cell(table.id, 2, 1)])
        return table, warning, error, ValidationResult({table.id: table}, [warning, error])

    def test_table_colors_full_rows_and_filter_navigation(self):
        table, warning, error, result = self.make_result()
        model = CsvTableModel(table, result.issues, warning)
        self.assertEqual(model.rowCount(), 3)
        self.assertEqual(model.columnCount(), 2)
        self.assertEqual(model.data(model.index(1, 1), Qt.ItemDataRole.BackgroundRole).name(), "#fff1a8")
        self.assertEqual(model.data(model.index(2, 1), Qt.ItemDataRole.BackgroundRole).name(), "#ffc6c6")
        dialog = IssueTableDialog(result, warning)
        dialog.show()
        self.app.processEvents()
        pane = dialog.panes[0]
        selected_rect = pane.view.visualRect(pane.view.currentIndex())
        image = pane.view.viewport().grab().toImage()
        color = image.pixelColor(selected_rect.right() - 15, selected_rect.center().y())
        self.assertEqual(color.name(), "#fff1a8")  # Selection cannot cover the warning color.
        pane.search.setText("002")
        self.assertEqual(pane.proxy.rowCount(), 1)
        pane.navigate(1)
        self.assertEqual(pane.search.text(), "")
        self.assertEqual(pane.proxy.mapToSource(pane.view.currentIndex()).row(), 1)
        dialog.close()

    def test_warning_color_wins_for_focused_cell(self):
        table, warning, error, result = self.make_result()
        overlap = Issue("G", "ERROR", "Row mismatch.", [Cell(table.id, 1, 1)])
        result.issues.insert(0, overlap)
        model = CsvTableModel(table, result.issues, warning)
        self.assertEqual(model.data(model.index(1, 1), Qt.ItemDataRole.BackgroundRole).name(), "#fff1a8")

    def test_header_and_missing_cell_highlights(self):
        table, warning, error, result = self.make_result()
        issue = Issue("H", "ERROR", "Missing header.", [Cell(table.id, 0, 0), Cell(table.id, 1, 2)])
        model = CsvTableModel(table, [issue], issue)
        self.assertEqual(model.columnCount(), 3)
        self.assertEqual(model.data(model.index(1, 2)), "(missing field)")
        self.assertEqual(model.data(model.index(0, 0), Qt.ItemDataRole.BackgroundRole).name(), "#ffc6c6")

    def test_link_and_submit_gating(self):
        window = MainWindow()
        window.show()
        self.app.processEvents()
        self.assertFalse(window.submit_button.isEnabled())
        root = Path(__file__).resolve().parents[1] / "examples"
        window.zip_drop.set_file(root / "data_example.zip")
        self.assertFalse(window.submit_button.isEnabled())
        window.key_drop.set_file(root / "key_example.zip")
        self.assertTrue(window.submit_button.isEnabled())
        table, warning, error, result = self.make_result()
        window.show_result(result)
        window.open_message(QUrl("issue:0"))
        self.assertEqual(len(window.table_dialogs), 1)
        self.assertEqual(window.table_dialogs[0].panes[0].model.rowCount(), 3)
        window.clear_console()
        self.assertEqual(window.table_dialogs, [])
        window.close()

    def test_background_validation_and_second_run(self):
        window = MainWindow()
        controller = ValidationController(window, Settings(sql_encoding="utf-8"))
        root = Path(__file__).resolve().parents[1] / "examples"
        window.zip_drop.set_file(root / "data_example.zip")
        window.key_drop.set_file(root / "key_example.zip")
        for _ in range(2):
            window.on_submit()
            self.assertTrue(window.busy)
            for iteration in range(500):
                QTest.qWait(10)
                if controller.thread is None:
                    break
            self.assertIsNone(controller.thread)
            self.assertFalse(window.busy)
            self.assertTrue(window.submit_button.isEnabled())
            self.assertGreater(window.result.error_count, 0)
            self.assertTrue(any(issue.rule == "K" for issue in window.result.issues))
        window.close()


if __name__ == "__main__":
    unittest.main()
