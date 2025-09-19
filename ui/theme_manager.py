import darkdetect  # type: ignore
from PyQt6.QtCore import QObject
from PyQt6.QtWidgets import QApplication

# from qdarkstyle.dark.palette import DarkPalette  # type: ignore
# from qdarkstyle.light.palette import LightPalette  # type: ignore
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
                background-color: #262a2e;
                color: #ffffff;
                border: none;
            }
            QMenuBar::item {
                background-color: transparent;
                color: #ffffff;
                padding: 4px 8px;
            }
            QMenuBar::item:selected {
                background-color: #1de9b6;
                color: #2d2d2d;
            }
            QMenuBar::item:pressed {
                background-color: #33ebbd;
                color: #2d2d2d;
            }
            QMenu {
                background-color: #2d2d2d;
                color: #ffffff;
                border: 1px solid #2d2d2d;
            }
            QMenu::item {
                background-color: transparent !important;
                color: #ffffff !important;
                padding: 3px 8px !important;
            }
            QMenu::item:selected {
                background-color: #1de9b6 !important;
                color: #2d2d2d !important;
            }
            QMenu::item:pressed {
                background-color: #33ebbd !important;
                color: #2d2d2d !important;
            }
            QMenu::separator {
                height: 1px;
                background-color: #535353;
                margin: 2px 0px;
            }
            QStatusBar {
                background-color: #262a2e;
            }
            """
        else:
            apply_stylesheet(app, theme="light_teal.xml", invert_secondary=True)
            # Light theme menu styling with better contrast
            menu_styling = """
            QMenuBar {
                background-color: #f5f5f5;
                color: #2d2d2d;
                border: none;
            }
            QMenuBar::item {
                background-color: transparent;
                color: #2d2d2d;
                padding: 4px 8px;
            }
            QMenuBar::item:selected {
                background-color: #1de9b6;
            }
            QMenuBar::item:pressed {
                background-color: #1de9b6;
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
                background-color: #1de9b6 !important;
            }
            QMenu::item:pressed {
                background-color: #1de9b6 !important;
            }
            QMenu::separator {
                height: 1px;
                background-color: #cccccc;
                margin: 2px 0px;
            }
            QStatusBar {
                background-color: #f0f0f0;
            }
            """

        # Apply the custom menu styling
        if app:
            current_stylesheet = app.styleSheet()
            app.setStyleSheet(current_stylesheet + menu_styling)

    # def get_palette(self):
    #     """Get the current color palette"""
    #     if self.should_use_dark_mode():
    #         return DarkPalette
    #     else:
    #         return LightPalette

    def set_override(self, override_value):
        """Set theme override"""
        self.dark_mode_override = override_value
