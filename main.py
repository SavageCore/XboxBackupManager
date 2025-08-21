import sys

from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import QApplication

from constants import APP_NAME, VERSION
from ui.main_window import XboxBackupManager  # type: ignore
from utils.github import auto_update  # type: ignore


def main():
    """Main application entry point"""
    # Check for updates
    auto_update()

    # Initialize the application
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setApplicationVersion(VERSION)

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
