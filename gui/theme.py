"""
Theme and styling for the Time Table Maker using PySide6.
Modern, clean design with professional color palette.
(Exact design match to Exam Seating Planner / Datesheet Maker)
"""

# =============================================================================
# COLOR PALETTE
# =============================================================================

COLORS = {
    # Primary brand
    "primary": "#2563EB",
    "primary_hover": "#1D4ED8",
    "primary_light": "#DBEAFE",
    
    # Success
    "success": "#16A34A",
    "success_hover": "#15803D",
    
    # Warning
    "warning": "#D97706",
    
    # Danger
    "danger": "#DC2626",
    "danger_hover": "#B91C1C",
    
    # Backgrounds
    "bg_primary": "#FFFFFF",
    "bg_secondary": "#F9FAFB",
    "bg_tertiary": "#F3F4F6",
    "bg_dark": "#111827",
    
    # Text
    "text_primary": "#111827",
    "text_secondary": "#4B5563",
    "text_muted": "#9CA3AF",
    "text_white": "#FFFFFF",
    
    # Borders
    "border": "#E5E7EB",
    "border_dark": "#374151",
    
    # Empty/neutral
    "empty": "#E5E7EB",
}

# =============================================================================
# STYLESHEETS
# =============================================================================

def get_main_stylesheet() -> str:
    """Return the main application stylesheet."""
    return f"""
        QMainWindow {{
            background-color: {COLORS['bg_secondary']};
        }}
        
        QWidget {{
            font-family: 'Segoe UI', sans-serif;
            font-size: 12px;
        }}
        
        QLabel {{
            color: {COLORS['text_primary']};
        }}
        
        QLabel[class="heading"] {{
            font-size: 16px;
            font-weight: bold;
            color: {COLORS['text_primary']};
        }}
        
        QLabel[class="subheading"] {{
            font-size: 13px;
            font-weight: bold;
        }}
        
        QLabel[class="muted"] {{
            color: {COLORS['text_muted']};
            font-size: 11px;
        }}
        
        QPushButton {{
            background-color: {COLORS['primary']};
            color: white;
            border: none;
            border-radius: 6px;
            padding: 8px 16px;
            font-weight: bold;
        }}
        
        QPushButton:hover {{
            background-color: {COLORS['primary_hover']};
        }}
        
        QPushButton:disabled {{
            background-color: {COLORS['border']};
            color: {COLORS['text_muted']};
        }}
        
        QPushButton[class="secondary"] {{
            background-color: {COLORS['success']};
        }}
        
        QPushButton[class="secondary"]:hover {{
            background-color: {COLORS['success_hover']};
        }}
        
        QPushButton[class="danger"] {{
            background-color: {COLORS['danger']};
        }}
        
        QPushButton[class="danger"]:hover {{
            background-color: {COLORS['danger_hover']};
        }}
        
        QPushButton[class="icon"] {{
            background-color: {COLORS['bg_tertiary']};
            color: {COLORS['text_primary']};
            padding: 8px;
            min-width: 36px;
            max-width: 36px;
        }}
        
        QPushButton[class="icon"]:hover {{
            background-color: {COLORS['border']};
        }}
        
        QFrame[class="card"] {{
            background-color: {COLORS['bg_primary']};
            border: 1px solid {COLORS['border']};
            border-radius: 8px;
        }}
        
        QFrame[class="panel"] {{
            background-color: {COLORS['bg_secondary']};
            border-radius: 10px;
        }}
        
        QScrollArea {{
            border: none;
            background-color: transparent;
        }}
        
        QScrollBar:vertical {{
            background-color: {COLORS['bg_tertiary']};
            width: 10px;
            border-radius: 5px;
        }}
        
        QScrollBar::handle:vertical {{
            background-color: {COLORS['border']};
            border-radius: 5px;
            min-height: 20px;
        }}
        
        QScrollBar::handle:vertical:hover {{
            background-color: {COLORS['text_muted']};
        }}
        
        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
            height: 0px;
        }}
        
        QCheckBox {{
            spacing: 8px;
        }}
        
        QCheckBox::indicator {{
            width: 18px;
            height: 18px;
            border-radius: 4px;
            border: 2px solid {COLORS['border']};
        }}
        
        QCheckBox::indicator:checked {{
            background-color: {COLORS['primary']};
            border-color: {COLORS['primary']};
        }}
        
        QCheckBox::indicator:disabled {{
            background-color: {COLORS['bg_tertiary']};
            border-color: {COLORS['border']};
        }}
        
        QStatusBar {{
            background-color: {COLORS['bg_secondary']};
            color: {COLORS['text_secondary']};
        }}
    """


def get_header_stylesheet() -> str:
    """Stylesheet for the header bar."""
    return f"""
        QFrame {{
            background-color: {COLORS['bg_secondary']};
        }}
        QLabel {{
            color: {COLORS['text_primary']};
        }}
    """


def get_mode_toggle_stylesheet(is_selected: bool) -> str:
    """Stylesheet for mode toggle buttons."""
    if is_selected:
        return f"""
            QPushButton {{
                background-color: {COLORS['primary']};
                color: white;
                border: none;
                border-radius: 4px;
                padding: 6px 12px;
                font-weight: bold;
                font-size: 11px;
            }}
        """
    else:
        return f"""
            QPushButton {{
                background-color: {COLORS['bg_tertiary']};
                color: {COLORS['text_secondary']};
                border: none;
                border-radius: 4px;
                padding: 6px 12px;
                font-size: 11px;
            }}
            QPushButton:hover {{
                background-color: {COLORS['border']};
            }}
        """
