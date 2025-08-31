import darkdetect  # type: ignore
from PyQt6.QtCore import QObject
from PyQt6.QtGui import QColor


class ThemeManager(QObject):
    """Manages application themes"""

    def __init__(self):
        super().__init__()
        self.dark_mode_override = (
            None  # None = auto, True = force dark, False = force light
        )

    def get_palette(self):
        """Get the appropriate palette based on dark mode setting"""
        theme = (
            "catppuccin_mocha" if self.should_use_dark_mode() else "catppuccin_latte"
        )

        # Latte
        # {
        #     "primary": "#8839ef",
        #     "secondary": "#1e66f5",
        #     "magenta": "#8839ef",
        #     "red": "#d20f39",
        #     "orange": "#fe640b",
        #     "yellow": "#df8e1d",
        #     "green": "#40a02b",
        #     "cyan": "#04a5e5",
        #     "blue": "#1e66f5",
        #     "text": "#4c4f69",
        #     "subtext1": "#5c5f77",
        #     "subtext0": "#6c6f85",
        #     "overlay2": "#7c7f93",
        #     "overlay1": "#8c8fa1",
        #     "overlay0": "#9ca0b0",
        #     "surface2": "#acb0be",
        #     "surface1": "#bcc0cc",
        #     "surface0": "#ccd0da",
        #     "base": "#dce0e8",
        #     "mantle": "#e6e9ef",
        #     "crust": "#eff1f5",
        # }

        # Mocha
        # {
        #     "primary": "#cba6f7",
        #     "secondary": "#89b4fa",
        #     "magenta": "#cba6f7",
        #     "red": "#f38ba8",
        #     "orange": "#fab387",
        #     "yellow": "#f9e2af",
        #     "green": "#a6e3a1",
        #     "cyan": "#89dceb",
        #     "blue": "#89b4fa",
        #     "text": "#cdd6f4",
        #     "subtext1": "#bac2de",
        #     "subtext0": "#a6adc8",
        #     "overlay2": "#9399b2",
        #     "overlay1": "#7f849c",
        #     "overlay0": "#6c7086",
        #     "surface2": "#585b70",
        #     "surface1": "#45475a",
        #     "surface0": "#313244",
        #     "base": "#1e1e2e",
        #     "mantle": "#181825",
        #     "crust": "#11111b",
        # }

        if theme == "catppuccin_mocha":
            palette = {
                "primary": "#cba6f7",
                "secondary": "#89b4fa",
                "magenta": "#cba6f7",
                "red": "#f38ba8",
                "orange": "#fab387",
                "yellow": "#f9e2af",
                "green": "#a6e3a1",
                "cyan": "#89dceb",
                "blue": "#89b4fa",
                "text": "#cdd6f4",
                "subtext1": "#bac2de",
                "subtext0": "#a6adc8",
                "overlay2": "#9399b2",
                "overlay1": "#7f849c",
                "overlay0": "#6c7086",
                "surface2": "#585b70",
                "surface1": "#45475a",
                "surface0": "#313244",
                "base": "#1e1e2e",
                "mantle": "#181825",
                "crust": "#11111b",
            }
        else:
            palette = {
                "primary": "#8839ef",
                "secondary": "#1e66f5",
                "magenta": "#8839ef",
                "red": "#d20f39",
                "orange": "#fe640b",
                "yellow": "#df8e1d",
                "green": "#40a02b",
                "cyan": "#04a5e5",
                "blue": "#1e66f5",
                "text": "#4c4f69",
                "subtext1": "#5c5f77",
                "subtext0": "#6c6f85",
                "overlay2": "#7c7f93",
                "overlay1": "#8c8fa1",
                "overlay0": "#9ca0b0",
                "surface2": "#acb0be",
                "surface1": "#bcc0cc",
                "surface0": "#ccd0da",
                "base": "#dce0e8",
                "mantle": "#e6e9ef",
                "crust": "#eff1f5",
            }

        return palette

    def get_qcolor_palette(self):
        """Get the palette with QColor objects instead of hex strings"""
        hex_palette = self.get_palette()
        qcolor_palette = {}

        for key, hex_value in hex_palette.items():
            qcolor_palette[key] = QColor(hex_value)

        return qcolor_palette

    def should_use_dark_mode(self) -> bool:
        """Determine if dark mode should be used"""
        if self.dark_mode_override is not None:
            return self.dark_mode_override
        return darkdetect.isDark()

    def set_override(self, override_value):
        """Set theme override"""
        self.dark_mode_override = override_value
