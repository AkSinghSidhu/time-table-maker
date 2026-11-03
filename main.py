import sys
from PySide6.QtWidgets import QApplication
from gui.app import TimeTableApp

def main():
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    app = QApplication(sys.argv)
    
    # Optional: Apply high DPI scaling settings if not done by default
    # It depends on the exact PySide6 version, mostly default in 6
    app.setStyle("Fusion")
    
    window = TimeTableApp()
    window.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
