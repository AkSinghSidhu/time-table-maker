"""Run the Qt editing and worker lifecycle checks without opening desktop windows."""

import contextlib
import io
import os
from pathlib import Path
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

os.environ["QT_QPA_PLATFORM"] = "offscreen"
import pandas as pd
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QTableWidget

from engine.cancellation import GenerationCancelled
from gui.app import TimeTableApp, WorkerThread
from gui.preview_view import PreviewView
from tests.helpers import fixture, write_workbook


class GuiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setQuitOnLastWindowClosed(False)

    def setUp(self):
        self.data, self.schedule = fixture()
        self.widgets = []
        self.output = io.StringIO()
        self.stdout = contextlib.redirect_stdout(self.output)
        self.stderr = contextlib.redirect_stderr(self.output)
        self.stdout.__enter__()
        self.stderr.__enter__()

    def tearDown(self):
        for widget in self.widgets:
            worker = getattr(widget, "worker", None)
            if worker is not None:
                worker.cancel()
                worker.wait(3000)
            widget.close()
            widget.deleteLater()
        self.app.processEvents()
        self.stderr.__exit__(None, None, None)
        self.stdout.__exit__(None, None, None)

    def preview(self):
        preview = PreviewView()
        self.widgets.append(preview)
        preview.display_schedule(self.schedule, self.data)
        return preview

    def window(self):
        window = TimeTableApp()
        self.widgets.append(window)
        return window

    def test_preview_is_read_only_and_exports_model_values(self):
        preview = self.preview()
        table = preview.tables[0]
        self.assertEqual(table.editTriggers(), QTableWidget.NoEditTriggers)
        self.assertFalse(table.item(0, 0).flags() & Qt.ItemIsEditable)
        # Programmatic changes to presentation widgets must not change the exported model.
        table.item(0, 0).setText("untrusted presentation text")
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "export.xlsx"
            preview.document.export_excel(path)
            self.assertIn("Mathematics", pd.read_excel(path, sheet_name="Class_C1", index_col=0).iloc[0, 0])

    def test_swap_refreshes_class_and_teacher_tabs(self):
        preview = self.preview()
        preview.tables[0].item(0, 0).setSelected(True)
        preview.tables[0].item(1, 0).setSelected(True)
        with patch("gui.preview_view.QMessageBox.warning") as warning:
            preview._swap_selected()
        warning.assert_not_called()
        teacher = preview.tables[preview.view_keys.index(("teacher_id", "T1"))]
        self.assertEqual(preview.tables[0].item(0, 0).text(), "Free")
        self.assertEqual(teacher.item(0, 0).text(), "Free")
        self.assertIn("Mathematics", teacher.item(1, 0).text())
        self.assertIn("Schedule Verified", preview.val_banner.text())

    def test_invalid_swap_displays_reason_and_preserves_model(self):
        self.data.unavailability = pd.DataFrame([dict(teacher_id="T1", day="Tuesday", period=1)])
        preview = self.preview()
        preview.tables[0].item(0, 0).setSelected(True)
        preview.tables[0].item(1, 0).setSelected(True)
        with patch("gui.preview_view.QMessageBox.warning") as warning:
            preview._swap_selected()
        warning.assert_called_once()
        self.assertIn("Unavailability", warning.call_args.args[2])
        self.assertEqual(preview.document.master_schedule, self.schedule)

    def test_break_selection_cannot_be_swapped(self):
        preview = self.preview()
        preview.tables[0].item(0, 0).setSelected(True)
        preview.tables[0].item(0, 3).setSelected(True)
        with patch("gui.preview_view.QMessageBox.warning") as warning:
            preview._swap_selected()
        self.assertEqual(warning.call_args.args[1], "Cannot Swap Break")
        self.assertEqual(preview.document.master_schedule, self.schedule)

    def test_browse_loads_workbook_configuration(self):
        window = self.window()
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "input.xlsx"
            write_workbook(self.data, path)
            with patch("gui.app.QFileDialog.getOpenFileName", return_value=(str(path), "")):
                window._browse_file()
            self.assertEqual(window.periods_spin.value(), 6)
            self.assertEqual(window.break_spin.value(), 3)
            self.assertEqual(window.days_edit.text(), "Monday, Tuesday")
            path.unlink()
        window.periods_spin.setValue(2)
        self.assertLessEqual(window.break_spin.value(), 2)

    def test_generate_passes_current_configuration_to_worker(self):
        window = self.window()
        window.filepath = "input.xlsx"
        window.periods_spin.setValue(4)
        window.break_spin.setValue(2)
        window.days_edit.setText("Wednesday, Thursday")
        with patch("gui.app.WorkerThread") as worker:
            window._start_generation()
            self.assertEqual(worker.call_args.args[2], dict(periods_per_day=4, break_after_period=2, working_days="Wednesday, Thursday"))
            worker.return_value.start.assert_called_once()
            self.assertFalse(window.browse_btn.isEnabled())
            self.assertTrue(window.cancel_btn.isEnabled())
            window._on_generation_finished(True, (self.schedule, self.data))
            window._on_worker_stopped()
        self.assertTrue(window.generate_btn.isEnabled())
        self.assertTrue(window.export_excel_btn.isEnabled())

    def test_worker_generates_with_configuration_override(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "input.xlsx"
            write_workbook(self.data, path)
            worker = WorkerThread(str(path), 5, dict(periods_per_day=4, break_after_period=2, working_days="Wednesday, Thursday"))
            results = []
            worker.completed.connect(lambda success, result: results.append((success, result)))
            worker.run()
            self.assertTrue(results[0][0], results[0][1])
            schedule, data = results[0][1]
            self.assertEqual(data.periods_per_day, 4)
            self.assertTrue(all(row["day"] in {"Wednesday", "Thursday"} and row["period"] <= 4 for row in schedule))

    def test_close_waits_for_worker_cancellation(self):
        entered = threading.Event()
        class WaitingWorker(WorkerThread):
            def run(self):
                entered.set()
                self.cancel_event.wait(3)
                self.completed.emit(False, GenerationCancelled("Cancelled"))
        window = self.window()
        worker = WaitingWorker("unused", 30, parent=window)
        window.worker = worker
        worker.completed.connect(window._on_generation_finished)
        worker.finished.connect(window._on_worker_stopped)
        worker.start()
        self.assertTrue(entered.wait(2))
        self.assertFalse(window.close())  # The first close request is deferred.
        self.assertTrue(worker.cancel_event.is_set())
        deadline = time.monotonic() + 3
        while window.worker is not None and time.monotonic() < deadline:
            self.app.processEvents()
            QTest.qWait(10)
        self.assertIsNone(window.worker)
        self.assertFalse(window.isVisible())

    def test_export_failure_is_reported(self):
        window = self.window()
        window.preview_view.display_schedule(self.schedule, self.data)
        with patch("gui.app.QFileDialog.getSaveFileName", return_value=("output.xlsx", "")), \
             patch.object(window.preview_view.document, "export_excel", side_effect=PermissionError("File is open")), \
             patch("gui.app.QMessageBox.critical") as critical:
            window._export_excel()
        self.assertIn("File is open", critical.call_args.args[2])


if __name__ == "__main__":
    unittest.main()
