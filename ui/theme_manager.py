import darkdetect  # type: ignore
import qdarkstyle  # type: ignore
from PyQt6.QtCore import QObject
from qdarkstyle.dark.palette import DarkPalette  # type: ignore
from qdarkstyle.light.palette import LightPalette  # type: ignore


class ThemeManager(QObject):
    """Manages application themes"""

    def __init__(self):
        super().__init__()
        self.dark_mode_override = (
            None  # None = auto, True = force dark, False = force light
        )

    def should_use_dark_mode(self) -> bool:
        """Determine if dark mode should be used"""
        if self.dark_mode_override is not None:
            return self.dark_mode_override
        return darkdetect.isDark()

    def get_stylesheet(self) -> str:
        """Get the current theme stylesheet"""
        if self.should_use_dark_mode():
            stylesheet = qdarkstyle.load_stylesheet(palette=DarkPalette)
        else:
            stylesheet = qdarkstyle.load_stylesheet(palette=LightPalette)

        # Add custom styling
        button_styling = """
        QPushButton#browse_button, QPushButton#scan_button {
            padding: 8px 16px !important;
            font-size: 14px !important;
            min-height: 20px !important;
        }
        QProgressBar {
            border: none;
        }
        QProgressBar::chunk {
            border-radius: 0px !important;
        }
        """
        return stylesheet + button_styling

    def set_override(self, override_value):
        """Set theme override"""
        self.dark_mode_override = override_value
