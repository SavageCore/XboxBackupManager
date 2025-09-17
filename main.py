import sys

from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import QApplication
from qt_material import apply_stylesheet  # type: ignore

from constants import APP_NAME, VERSION
from ui.main_window import XboxBackupManager  # type: ignore


def main():
    """Main application entry point"""
    # Initialize the application
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setApplicationVersion(VERSION)

    apply_stylesheet(app, theme="dark_teal.xml")

    # Set application icon if available
    try:
        app.setWindowIcon(QIcon("icon.ico"))
    except Exception:
        pass

    window = XboxBackupManager()
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
