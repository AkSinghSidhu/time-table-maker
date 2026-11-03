from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame,
    QTableWidget, QTableWidgetItem, QHeaderView, QTabWidget, QPushButton, QMessageBox
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont, QColor
from gui.theme import COLORS
from engine.schedule import ScheduleDocument
from engine.exporter import TimetableExporter

class PreviewView(QWidget):
    """Main visualization panel — displays generated datesheet in tabs with real-time validation."""

    def __init__(self):
        super().__init__()
        self.document = None
        self.view_keys = []
        self.tables = []
        self._setup_ui()

    def _setup_ui(self):
        """Set up the panel UI."""
        self.setStyleSheet(f"background-color: {COLORS['bg_secondary']}; border-radius: 10px;")

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(12, 12, 12, 12)
        main_layout.setSpacing(8)

        # Header
        header = QWidget()
        header.setStyleSheet("background-color: transparent;")
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(0, 0, 0, 0)

        title = QLabel("TIMETABLE PREVIEW")
        title.setFont(QFont("Segoe UI", 14, QFont.Bold))
        title.setStyleSheet(f"color: {COLORS['text_primary']};")
        header_layout.addWidget(title)

        header_layout.addStretch()

        # Swap Button
        self.swap_btn = QPushButton("🔄 Swap / Move Sessions")
        self.swap_btn.setToolTip("Select two cells in one view. Labs move as complete two-period blocks; conflicting changes are rejected.")
        self.swap_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {COLORS['primary']};
                color: white;
                border: none;
                border-radius: 6px;
                padding: 6px 12px;
                font-weight: bold;
            }}
            QPushButton:hover {{ background-color: {COLORS['primary_hover']}; }}
            QPushButton:disabled {{ background-color: {COLORS['border']}; color: {COLORS['text_muted']}; }}
        """)
        self.swap_btn.setEnabled(False)
        self.swap_btn.clicked.connect(self._swap_selected)
        header_layout.addWidget(self.swap_btn)

        main_layout.addWidget(header)

        # Validation status banner
        self.val_banner = QLabel("")
        self.val_banner.setFont(QFont("Segoe UI", 10, QFont.Bold))
        self.val_banner.setWordWrap(True)
        self.val_banner.setStyleSheet("padding: 8px 12px; border-radius: 6px;")
        self.val_banner.hide()
        main_layout.addWidget(self.val_banner)

        self.content_widget = QWidget()
        self.content_widget.setStyleSheet(
            f"background-color: {COLORS['bg_primary']}; border-radius: 8px;"
        )
        self.content_layout = QVBoxLayout(self.content_widget)
        self.content_layout.setContentsMargins(8, 8, 8, 8)
        self.content_layout.setSpacing(10)

        main_layout.addWidget(self.content_widget, 1)

        # Show empty state
        self._show_empty_state()

    def _show_empty_state(self):
        """Show the empty state message."""
        self._clear_content()
        self.swap_btn.setEnabled(False)
        self.val_banner.hide()
        self.document = None
        self.tables = []
        self.view_keys = []

        empty_widget = QWidget()
        empty_layout = QVBoxLayout(empty_widget)
        empty_layout.setContentsMargins(0, 60, 0, 60)

        icon = QLabel("📅")
        icon.setAlignment(Qt.AlignCenter)
        icon.setFont(QFont("Segoe UI Emoji", 48))
        empty_layout.addWidget(icon)

        text = QLabel("No timetable generated yet.\n\nConfigure settings and click\n'Generate' to create one.")
        text.setAlignment(Qt.AlignCenter)
        text.setFont(QFont("Segoe UI", 12))
        text.setStyleSheet(f"color: {COLORS['text_muted']};")
        empty_layout.addWidget(text)

        self.content_layout.addWidget(empty_widget)
        self.content_layout.addStretch()

    def _clear_content(self):
        """Clear all content."""
        while self.content_layout.count():
            item = self.content_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

    def display_schedule(self, master_schedule, data):
        self.document = ScheduleDocument(master_schedule, data)
        self._render()

    def _render(self, current_index=0):
        """Render all projections from the same validated schedule."""
        self._clear_content()
        self.tables = []
        self.view_keys = []

        try:
            class_grids, teacher_grids = self.document.projections()
            self.view_keys = [("class_id", key) for key in class_grids] + [("teacher_id", key) for key in teacher_grids]

            self.tab_widget = QTabWidget()
            self.tab_widget.setStyleSheet(f"""
                QTabWidget::pane {{
                    border: 1px solid {COLORS['border']};
                    background: white;
                    border-radius: 4px;
                }}
                QTabBar::tab {{
                    background: {COLORS['bg_tertiary']};
                    color: {COLORS['text_secondary']};
                    padding: 8px 16px;
                    border: 1px solid {COLORS['border']};
                    border-bottom: none;
                    border-top-left-radius: 4px;
                    border-top-right-radius: 4px;
                    margin-right: 2px;
                }}
                QTabBar::tab:selected {{
                    background: white;
                    color: {COLORS['primary']};
                    font-weight: bold;
                }}
                QTabBar::tab:hover {{
                    background: {COLORS['primary_light']};
                    color: {COLORS['primary']};
                }}
            """)

            for sheet_name, df in TimetableExporter.named_grids(class_grids, teacher_grids):

                table = QTableWidget()
                self.tables.append(table)
                table.setRowCount(df.shape[0])
                table.setColumnCount(df.shape[1])
                table.setHorizontalHeaderLabels([str(c) for c in df.columns])
                table.setVerticalHeaderLabels([str(i) for i in df.index])

                # Insert data
                for row in range(df.shape[0]):
                    for col in range(df.shape[1]):
                        val = str(df.iloc[row, col])
                        if val == 'nan':
                            val = ""
                        item = QTableWidgetItem(val)
                        item.setFlags(item.flags() & ~Qt.ItemIsEditable)
                        item.setTextAlignment(Qt.AlignCenter)

                        if val == "LUNCH BREAK" or val == "BREAK":
                            item.setBackground(QColor(COLORS['warning']))
                            item.setForeground(QColor("white"))
                            item.setFont(QFont("Segoe UI", 11, QFont.Bold))
                        elif "[LAB]" in val:
                            item.setBackground(QColor(COLORS['danger']))
                            item.setForeground(QColor("white"))
                            item.setFont(QFont("Segoe UI", 10, QFont.Bold))
                        elif val == "Free":
                            item.setBackground(QColor(COLORS['empty']))
                            item.setForeground(QColor(COLORS['text_muted']))
                        else:
                            if row % 2 == 0:
                                item.setBackground(QColor(COLORS['bg_tertiary']))
                            else:
                                item.setBackground(QColor(COLORS['bg_primary']))
                        table.setItem(row, col, item)

                table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
                table.verticalHeader().setVisible(True)
                table.setAlternatingRowColors(False)
                table.setSelectionMode(QTableWidget.ExtendedSelection)
                table.setEditTriggers(QTableWidget.NoEditTriggers)

                table.setStyleSheet(f"""
                    QTableWidget {{
                        border: none;
                        background-color: white;
                        color: {COLORS['text_primary']};
                        gridline-color: {COLORS['border']};
                        selection-background-color: {COLORS['primary_light']};
                        selection-color: {COLORS['text_primary']};
                    }}
                    QHeaderView::section {{
                        background-color: {COLORS['bg_secondary']};
                        color: {COLORS['text_primary']};
                        padding: 6px;
                        border: 1px solid {COLORS['border']};
                        font-weight: bold;
                    }}
                """)

                self.tab_widget.addTab(table, sheet_name)

            self.content_layout.addWidget(self.tab_widget)
            self.tab_widget.setCurrentIndex(current_index)
            self.swap_btn.setEnabled(True)

            self.val_banner.setText("✅ Schedule Verified — 0 Hard Constraint Violations.")
            self.val_banner.setStyleSheet("background-color: #D1FAE5; color: #065F46; padding: 8px 12px; border-radius: 6px;")
            self.val_banner.show()

        except Exception as e:
            self._show_error(f"Error loading preview: {str(e)}")
            raise

    def _swap_selected(self):
        """Apply a validated change to the model and refresh every view."""
        if not hasattr(self, 'tab_widget') or not self.tables: return

        current_table = self.tables[self.tab_widget.currentIndex()]
        selected_items = current_table.selectedItems()

        if len(selected_items) != 2:
            QMessageBox.warning(self, "Invalid Selection", "Please select exactly 2 cells to swap.")
            return

        item1, item2 = selected_items[0], selected_items[1]

        if any(current_table.horizontalHeaderItem(item.column()).text() == "BREAK" for item in (item1, item2)):
            QMessageBox.warning(self, "Cannot Swap Break", "You cannot swap a lunch break period.")
            return

        def slot(item):
            day = current_table.verticalHeaderItem(item.row()).text()
            period = int(current_table.horizontalHeaderItem(item.column()).text().split()[-1])
            return day, period

        index = self.tab_widget.currentIndex()
        try:
            self.document.swap(*self.view_keys[index], slot(item1), slot(item2))
        except ValueError as exc:
            QMessageBox.warning(self, "Cannot Apply Change", str(exc))
            return
        self._render(index)

    def _show_error(self, message: str):
        """Show error message."""
        self._clear_content()
        self.swap_btn.setEnabled(False)
        self.val_banner.hide()
        error = QFrame()
        error.setStyleSheet(f"""
            background-color: {COLORS['danger']};
            border-radius: 10px;
        """)
        error_layout = QHBoxLayout(error)
        error_layout.setContentsMargins(16, 16, 16, 16)

        text = QLabel(f"❌ {message}")
        text.setFont(QFont("Segoe UI", 12, QFont.Bold))
        text.setStyleSheet("color: white;")
        error_layout.addWidget(text, 0, Qt.AlignCenter)

        self.content_layout.addWidget(error)
        self.content_layout.addStretch()
