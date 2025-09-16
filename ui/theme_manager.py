import darkdetect  # type: ignore
from PyQt6.QtCore import QObject
from PyQt6.QtWidgets import QApplication
from qdarkstyle.dark.palette import DarkPalette  # type: ignore
from qdarkstyle.light.palette import LightPalette  # type: ignore
from qt_material import apply_stylesheet  # type: ignore


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
        app = QApplication.instance()
        if app is None:
            return ""

        if self.should_use_dark_mode():
            apply_stylesheet(app, theme="dark_teal.xml")
            # Dark theme menu styling
            menu_styling = """
            QMenuBar {
                background-color: #2d2d2d;
                color: #ffffff;
                border: none;
            }
            QMenuBar::item {
                background-color: transparent;
                color: #ffffff;
                padding: 4px 8px;
            }
            QMenuBar::item:selected {
                background-color: #404040;
                color: #ffffff;
            }
            QMenuBar::item:pressed {
                background-color: #505050;
                color: #ffffff;
            }
            QMenu {
                background-color: #2d2d2d;
                color: #ffffff;
                border: 1px solid #555555;
            }
            QMenu::item {
                background-color: transparent !important;
                color: #ffffff !important;
                padding: 3px 8px !important;
            }
            QMenu::item:selected {
                background-color: #404040 !important;
                color: #ffffff !important;
            }
            QMenu::item:pressed {
                background-color: #505050 !important;
                color: #ffffff !important;
            }
            QMenu::separator {
                height: 1px;
                background-color: #555555;
                margin: 2px 0px;
            }
            """
        else:
            apply_stylesheet(app, theme="light_teal.xml", invert_secondary=True)
            # Light theme menu styling with better contrast
            menu_styling = """
            QMenuBar {
                background-color: #ffffff;
                color: #2d2d2d;
                border: none;
            }
            QMenuBar::item {
                background-color: transparent;
                color: #2d2d2d;
                padding: 4px 8px;
            }
            QMenuBar::item:selected {
                background-color: #009688;
                color: #ffffff;
            }
            QMenuBar::item:pressed {
                background-color: #00796b;
                color: #ffffff;
            }
            QMenu {
                background-color: #ffffff;
                color: #2d2d2d;
                border: 1px solid #cccccc;
            }
            QMenu::item {
                background-color: transparent !important;
                color: #2d2d2d !important;
                padding: 6px 16px !important;
            }
            QMenu::item:selected {
                background-color: #009688 !important;
                color: #ffffff !important;
            }
            QMenu::item:pressed {
                background-color: #00796b !important;
                color: #ffffff !important;
            }
            QMenu::separator {
                height: 1px;
                background-color: #cccccc;
                margin: 2px 0px;
            }
            """

        # Apply the custom menu styling
        if app:
            current_stylesheet = app.styleSheet()
            app.setStyleSheet(current_stylesheet + menu_styling)

    def get_palette(self):
        """Get the current color palette"""
        if self.should_use_dark_mode():
            return DarkPalette
        else:
            return LightPalette

    def set_override(self, override_value):
        """Set theme override"""
        self.dark_mode_override = override_value
