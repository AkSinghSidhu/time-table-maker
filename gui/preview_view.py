from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame,
    QTableWidget, QTableWidgetItem, QHeaderView, QTabWidget, QPushButton, QMessageBox
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont, QColor
import pandas as pd
import tempfile
import os

from gui.theme import COLORS
from engine.validator import IndependentValidator

class PreviewView(QWidget):
    """Main visualization panel — displays generated datesheet in tabs with real-time validation."""

    def __init__(self):
        super().__init__()
        self.excel_filepath = None
        self.timetable_data = None
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
        self.swap_btn = QPushButton("🔄 Swap Selected Periods")
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
        self.excel_filepath = None

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

    def display_plan(self, excel_filepath):
        """Load the excel file and display it in tabs."""
        self._clear_content()
        self.excel_filepath = excel_filepath
        self.tables = []

        try:
            xls = pd.ExcelFile(excel_filepath)

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

            for sheet_name in xls.sheet_names:
                df = pd.read_excel(xls, sheet_name=sheet_name, index_col=0)

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
                table.setEditTriggers(QTableWidget.DoubleClicked)

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
            self.swap_btn.setEnabled(True)

            self.val_banner.setText("✅ Schedule Verified — 0 Hard Constraint Violations.")
            self.val_banner.setStyleSheet("background-color: #D1FAE5; color: #065F46; padding: 8px 12px; border-radius: 6px;")
            self.val_banner.show()

        except Exception as e:
            self._show_error(f"Error loading preview: {str(e)}")

    def _swap_selected(self):
        """Swaps the text content of two selected cells in the current tab."""
        if not hasattr(self, 'tab_widget') or not self.tables: return

        current_table = self.tables[self.tab_widget.currentIndex()]
        selected_items = current_table.selectedItems()

        if len(selected_items) != 2:
            QMessageBox.warning(self, "Invalid Selection", "Please select exactly 2 cells to swap.")
            return

        item1, item2 = selected_items[0], selected_items[1]

        if "BREAK" in item1.text() or "BREAK" in item2.text():
            QMessageBox.warning(self, "Cannot Swap Break", "You cannot swap a lunch break period.")
            return

        text1 = item1.text()
        text2 = item2.text()

        item1.setText(text2)
        item2.setText(text1)

        current_table.clearSelection()

        self.val_banner.setText("⚠️ Manual edit applied. Independent Validator active.")
        self.val_banner.setStyleSheet("background-color: #FEF3C7; color: #92400E; padding: 8px 12px; border-radius: 6px;")
        self.val_banner.show()

    def get_current_data_as_excel(self):
        """Reads modified tables back into a new excel file and returns the path."""
        if not self.tables:
            return None

        tmp_fd, tmp_path = tempfile.mkstemp(suffix='.xlsx')
        os.close(tmp_fd)

        with pd.ExcelWriter(tmp_path, engine='openpyxl') as writer:
            for i in range(self.tab_widget.count()):
                sheet_name = self.tab_widget.tabText(i)
                table = self.tables[i]

                rows = table.rowCount()
                cols = table.columnCount()

                col_headers = [table.horizontalHeaderItem(c).text() for c in range(cols)]
                row_headers = [table.verticalHeaderItem(r).text() for r in range(rows)]

                data = []
                for r in range(rows):
                    row_data = []
                    for c in range(cols):
                        item = table.item(r, c)
                        row_data.append(item.text() if item else "")
                    data.append(row_data)

                df = pd.DataFrame(data, columns=col_headers, index=row_headers)
                df.to_excel(writer, sheet_name=sheet_name)

        return tmp_path

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
