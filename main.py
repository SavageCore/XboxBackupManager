import sys

from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import QApplication

from ui.main_window import XboxBackupManager  # type: ignore


def main():
    """Main application entry point"""
    app = QApplication(sys.argv)
    app.setApplicationName("Xbox 360 Backup Manager")
    app.setApplicationVersion("1.0")

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
