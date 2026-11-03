import os
import html
import threading

from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QFrame, QSplitter, QStatusBar, QFileDialog,
    QMessageBox, QSpinBox, QSizePolicy, QScrollArea, QLineEdit
)
from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QFont, QCursor, QTextDocument
from PySide6.QtPrintSupport import QPrinter

from engine.scheduler import TimetableScheduler, generate_dummy_template
from engine.data_loader import load_timetable_data
from engine.cancellation import GenerationCancelled, check_cancelled
from engine.exporter import TimetableExporter
from engine.logger import log_step, log_info, log_success
from gui.theme import COLORS, get_main_stylesheet
from gui.preview_view import PreviewView

class WorkerThread(QThread):
    """Background thread for timetable generation."""
    completed = Signal(bool, object)

    def __init__(self, filepath, time_limit_seconds, config_overrides=None, parent=None):
        super().__init__(parent)
        self.filepath = filepath
        self.time_limit_seconds = time_limit_seconds
        self.config_overrides = dict(config_overrides or {})
        self.cancel_event = threading.Event()

    def cancel(self):
        self.cancel_event.set()

    def run(self):
        try:
            check_cancelled(self.cancel_event)
            scheduler = TimetableScheduler(self.filepath, config_overrides=self.config_overrides)
            master_sched, _, _ = scheduler.solve(
                time_limit_seconds=self.time_limit_seconds, cancel_event=self.cancel_event)
            check_cancelled(self.cancel_event)
            self.completed.emit(True, (master_sched, scheduler.data))
        except Exception as e:
            self.completed.emit(False, GenerationCancelled("Timetable generation cancelled.") if self.cancel_event.is_set() else e)


class TimeTableApp(QMainWindow):
    """Main application window — Time Table Maker."""

    APP_TITLE = "📅 Time Table Maker"
    DEFAULT_SIZE = (1400, 800)
    MIN_SIZE = (1000, 600)

    def __init__(self):
        super().__init__()

        self.setWindowTitle(self.APP_TITLE)
        self.resize(*self.DEFAULT_SIZE)
        self.setMinimumSize(*self.MIN_SIZE)

        self.filepath = None
        self.worker = None
        self._closing = False

        # Apply base stylesheet
        self.setStyleSheet(get_main_stylesheet() + """
            QSpinBox, QLineEdit {
                padding: 8px 12px;
                border: 1px solid #E5E7EB;
                border-radius: 6px;
                background-color: #FFFFFF;
                color: #111827;
                font-size: 13px;
                min-height: 20px;
            }
            QSpinBox:focus, QLineEdit:focus {
                border: 1px solid #2563EB;
            }
        """)

        # Build UI
        self._setup_ui()

        # Center on screen and maximize
        self._center_window()
        self.showMaximized()

    def _center_window(self):
        screen = self.screen().availableGeometry()
        x = (screen.width() - self.width()) // 2
        y = (screen.height() - self.height()) // 2
        self.move(x, y)

    def _setup_ui(self):
        central = QWidget()
        self.setCentralWidget(central)

        main_layout = QVBoxLayout(central)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # Header bar
        self._create_header(main_layout)

        # Main content (splitter with settings + preview)
        self._create_main_content(main_layout)

        # Status bar
        self._create_status_bar()

    def _create_header(self, parent_layout):
        header = QFrame()
        header.setFixedHeight(70)
        header.setStyleSheet(f"background-color: {COLORS['bg_secondary']};")

        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(24, 0, 24, 0)

        title = QLabel("📅 TIMETABLE MAKER")
        title.setFont(QFont("Segoe UI", 22, QFont.Bold))
        title.setStyleSheet(f"color: {COLORS['text_primary']}; border: none;")
        header_layout.addWidget(title)

        subtitle = QLabel("Generate Class & Teacher Timetables")
        subtitle.setFont(QFont("Segoe UI", 11))
        subtitle.setStyleSheet(f"color: {COLORS['text_muted']}; margin-left: 16px; border: none;")
        header_layout.addWidget(subtitle)

        header_layout.addStretch()

        self.export_excel_btn = QPushButton("📥 Export Excel")
        self.export_excel_btn.setFixedSize(130, 40)
        self.export_excel_btn.setStyleSheet(f"background-color: {COLORS['success']}; color: white; border: none; border-radius: 6px; font-weight: bold;")
        self.export_excel_btn.setEnabled(False)
        self.export_excel_btn.setCursor(QCursor(Qt.PointingHandCursor))
        self.export_excel_btn.clicked.connect(self._export_excel)
        header_layout.addWidget(self.export_excel_btn)
        
        self.export_pdf_btn = QPushButton("📄 Export PDF")
        self.export_pdf_btn.setFixedSize(130, 40)
        self.export_pdf_btn.setStyleSheet(f"background-color: {COLORS['danger']}; color: white; border: none; border-radius: 6px; font-weight: bold;")
        self.export_pdf_btn.setEnabled(False)
        self.export_pdf_btn.setCursor(QCursor(Qt.PointingHandCursor))
        self.export_pdf_btn.clicked.connect(self._export_pdf)
        header_layout.addWidget(self.export_pdf_btn)

        parent_layout.addWidget(header)

    def _create_main_content(self, parent_layout):
        content = QWidget()
        content.setStyleSheet(f"background-color: {COLORS['bg_secondary']};")
        content_layout = QHBoxLayout(content)
        content_layout.setContentsMargins(16, 16, 16, 16)
        content_layout.setSpacing(16)

        splitter = QSplitter(Qt.Horizontal)
        splitter.setHandleWidth(16)
        splitter.setStyleSheet("QSplitter::handle { background-color: transparent; }")

        settings_panel = self._build_settings_panel()
        settings_panel.setMinimumWidth(320)

        preview_card = QFrame()
        preview_card.setProperty("class", "card")
        preview_card.setMinimumWidth(400)
        preview_card_layout = QVBoxLayout(preview_card)
        preview_card_layout.setContentsMargins(0, 0, 0, 0)
        preview_card_layout.setSpacing(0)
        self.preview_view = PreviewView()
        preview_card_layout.addWidget(self.preview_view)

        splitter.addWidget(settings_panel)
        splitter.addWidget(preview_card)
        splitter.setSizes([420, 930])

        content_layout.addWidget(splitter)
        parent_layout.addWidget(content, 1)

    def _build_settings_panel(self) -> QFrame:
        outer_container = QFrame()
        outer_container.setProperty("class", "card")
        outer_layout = QVBoxLayout(outer_container)
        outer_layout.setContentsMargins(0, 0, 0, 0)

        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setFrameShape(QFrame.NoFrame)

        panel = QFrame()
        panel.setStyleSheet("background-color: transparent;")
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(20)

        # -- File Upload --
        section = QVBoxLayout()
        lbl = QLabel("1. Upload Data")
        lbl.setProperty("class", "heading")
        section.addWidget(lbl)
        
        btn_layout = QHBoxLayout()
        self.template_btn = QPushButton("Download Template")
        self.template_btn.setStyleSheet(f"background-color: {COLORS['primary']}; color: white; border: none; border-radius: 6px; padding: 8px 16px; font-weight: bold;")
        self.template_btn.clicked.connect(self._download_template)
        btn_layout.addWidget(self.template_btn)
        section.addLayout(btn_layout)

        row = QHBoxLayout()
        self.file_path_display = QLabel("No file selected")
        self.file_path_display.setStyleSheet(
            f"color: {COLORS['text_muted']}; padding: 10px; "
            f"border: 1px solid {COLORS['border']}; border-radius: 6px; "
            f"background: {COLORS['bg_tertiary']};"
        )
        self.file_path_display.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

        browse_btn = self.browse_btn = QPushButton("Browse")
        browse_btn.setFixedSize(90, 38)
        browse_btn.setStyleSheet(f"background-color: {COLORS['primary']}; color: white; border: none; border-radius: 6px; font-weight: bold;")
        browse_btn.setCursor(QCursor(Qt.PointingHandCursor))
        browse_btn.clicked.connect(self._browse_file)
        row.addWidget(self.file_path_display)
        row.addWidget(browse_btn)
        section.addLayout(row)
        layout.addLayout(section)

        # -- Configuration --
        cfg_section = QVBoxLayout()
        cfg_lbl = QLabel("2. Timetable Parameters")
        cfg_lbl.setProperty("class", "heading")
        cfg_section.addWidget(cfg_lbl)
        
        days_lbl = QLabel("Days (comma separated):")
        self.days_edit = QLineEdit("Monday, Tuesday, Wednesday, Thursday, Friday")
        cfg_section.addWidget(days_lbl)
        cfg_section.addWidget(self.days_edit)
        
        p_row = QHBoxLayout()
        p_lbl = QLabel("Periods per day:")
        self.periods_spin = QSpinBox()
        self.periods_spin.setRange(1, 24)
        self.periods_spin.setValue(8)
        p_row.addWidget(p_lbl)
        p_row.addWidget(self.periods_spin)
        cfg_section.addLayout(p_row)
        
        b_row = QHBoxLayout()
        b_lbl = QLabel("Break after Period (0 = None):")
        self.break_spin = QSpinBox()
        self.break_spin.setRange(0, self.periods_spin.value())
        self.break_spin.setValue(4)
        b_row.addWidget(b_lbl)
        b_row.addWidget(self.break_spin)
        cfg_section.addLayout(b_row)
        self.periods_spin.valueChanged.connect(self.break_spin.setMaximum)

        t_row = QHBoxLayout()
        t_lbl = QLabel("Solver time limit (seconds):")
        self.time_spin = QSpinBox()
        self.time_spin.setRange(5, 900)
        self.time_spin.setValue(120)
        t_row.addWidget(t_lbl)
        t_row.addWidget(self.time_spin)
        cfg_section.addLayout(t_row)

        layout.addLayout(cfg_section)
        layout.addStretch()

        # -- Actions --
        self.generate_btn = QPushButton("⚡ Generate Timetable")
        self.generate_btn.setFixedHeight(50)
        self.generate_btn.setFont(QFont("Segoe UI", 12, QFont.Bold))
        self.generate_btn.setStyleSheet(f"background-color: {COLORS['primary']}; color: white; border: none; border-radius: 8px; font-weight: bold;")
        self.generate_btn.setCursor(QCursor(Qt.PointingHandCursor))
        self.generate_btn.clicked.connect(self._start_generation)
        layout.addWidget(self.generate_btn)
        self.cancel_btn = QPushButton("Cancel Generation")
        self.cancel_btn.setEnabled(False)
        self.cancel_btn.clicked.connect(self._cancel_generation)
        layout.addWidget(self.cancel_btn)

        scroll_area.setWidget(panel)
        outer_layout.addWidget(scroll_area)

        return outer_container

    def _create_status_bar(self):
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.status_label = QLabel("✅ Ready.")
        self.status_bar.addWidget(self.status_label)

    def _download_template(self):
        dest, _ = QFileDialog.getSaveFileName(
            self, "Save Template", "template.xlsx", "Excel Files (*.xlsx)"
        )
        if dest:
            try:
                generate_dummy_template(dest)
                self.status_label.setText(f"✅ Template saved to {dest}")
                log_success(f"Template dataset downloaded to: {dest}")
            except Exception as exc:
                QMessageBox.critical(self, "Template Failed", str(exc))

    def _browse_file(self):
        file_name, _ = QFileDialog.getOpenFileName(
            self, "Select Dataset", "", "Excel Files (*.xlsx)"
        )
        if file_name:
            try:
                data = load_timetable_data(file_name)
            except Exception as exc:
                QMessageBox.critical(self, "Invalid Workbook", str(exc))
                return
            self.filepath = file_name
            self.periods_spin.setValue(data.periods_per_day)
            self.break_spin.setValue(data.break_after_period)
            self.days_edit.setText(", ".join(data.working_days))
            self.preview_view._show_empty_state()
            self.file_path_display.setText(os.path.basename(file_name))
            self.export_excel_btn.setEnabled(False)
            self.export_pdf_btn.setEnabled(False)
            self.status_label.setText(f"📂 File loaded: {os.path.basename(file_name)}.")
            log_info(f"User selected dataset file: {file_name}")

    def _start_generation(self):
        if not self.filepath:
            QMessageBox.warning(self, "Error", "Please upload a data file or download the template!")
            return

        if self.worker is not None and self.worker.isRunning():
            return

        log_step("🖥️ GUI Event", "User clicked 'Generate Timetable'")

        self.generate_btn.setEnabled(False)
        self.generate_btn.setText("⏳ Generating...")
        self._set_busy(True)
        overrides = {
            "working_days": self.days_edit.text(),
            "periods_per_day": self.periods_spin.value(),
            "break_after_period": self.break_spin.value(),
        }
        self.worker = WorkerThread(self.filepath, self.time_spin.value(), overrides, parent=self)
        self.worker.completed.connect(self._on_generation_finished)
        self.worker.finished.connect(self._on_worker_stopped)
        self.worker.start()

    def _on_generation_finished(self, success: bool, result):
        if self._closing:
            return
        if success:
            try:
                self.preview_view.display_schedule(*result)
                self.status_label.setText("✅ Timetable generated!")
                log_success("Timetable generation completed and validated in Preview UI.")
            except Exception as exc:
                self.preview_view._show_empty_state()
                QMessageBox.critical(self, "Preview Failed", str(exc))
        elif isinstance(result, GenerationCancelled):
            self.status_label.setText("Generation cancelled.")
        else:
            self.status_label.setText("Generation failed.")
            QMessageBox.critical(self, "Failed", f"Error:\n{result}")
            log_info(f"Generation failed: {result}")

    def _set_busy(self, busy):
        for widget in (self.generate_btn, self.browse_btn, self.template_btn, self.days_edit,
                       self.periods_spin, self.break_spin, self.time_spin, self.preview_view):
            widget.setEnabled(not busy)
        self.cancel_btn.setEnabled(busy)
        can_export = not busy and self.preview_view.document is not None
        self.export_excel_btn.setEnabled(can_export)
        self.export_pdf_btn.setEnabled(can_export)

    def _cancel_generation(self):
        if self.worker is not None:
            self.worker.cancel()
            self.cancel_btn.setEnabled(False)
            self.status_label.setText("Cancelling generation…")

    def _on_worker_stopped(self):
        worker = self.worker
        self.worker = None
        if worker is not None:
            worker.deleteLater()
        if self._closing:
            self.close()
            return
        self.generate_btn.setText("⚡ Generate Timetable")
        self._set_busy(False)

    def _export_excel(self):
        if self.preview_view.document is None:
            return
        dest, _ = QFileDialog.getSaveFileName(self, "Save Excel", "timetable.xlsx", "Excel Files (*.xlsx)")
        if dest:
            try:
                self.preview_view.document.export_excel(dest)
                self.status_label.setText(f"✅ Exported Excel: {dest}")
                log_success(f"Exported Excel workbook to: {dest}")
            except Exception as exc:
                QMessageBox.critical(self, "Export Failed", str(exc))

    def _export_pdf(self):
        if self.preview_view.document is None:
            return
        dest, _ = QFileDialog.getSaveFileName(self, "Save PDF", "timetable.pdf", "PDF Files (*.pdf)")
        if not dest: return

        try:
            grids = self.preview_view.document.projections()
            markup = "<html><head><style>table, th, td {border: 1px solid black; border-collapse: collapse; padding: 5px; text-align: center;}</style></head><body>"
            markup += "<h1>University Timetable</h1>"
            for sheet_name, df in TimetableExporter.named_grids(*grids):
                markup += f"<h2>{html.escape(sheet_name)}</h2>"
                markup += df.to_html()
                markup += "<br><br>"
            markup += "</body></html>"

            doc = QTextDocument()
            doc.setHtml(markup)
            printer = QPrinter()
            printer.setOutputFormat(QPrinter.PdfFormat)
            printer.setOutputFileName(dest)
            doc.print_(printer)
            self.status_label.setText(f"✅ Exported PDF: {dest}")
            log_success(f"Exported PDF document to: {dest}")
        except Exception as e:
            QMessageBox.critical(self, "Failed", f"Export failed:\n{str(e)}")

    def closeEvent(self, event):
        if self.worker is not None and self.worker.isRunning():
            self._closing = True
            self._cancel_generation()
            event.ignore()
            return
        event.accept()

