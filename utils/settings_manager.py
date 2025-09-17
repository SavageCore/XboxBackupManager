from typing import Dict

from PyQt6.QtCore import QSettings


class SettingsManager:
    """Manages application settings persistence"""

    def __init__(self):
        settings_file = "XboxBackupManager.ini"
        self.settings = QSettings(settings_file, QSettings.Format.IniFormat)

    def save_window_state(self, window):
        """Save window geometry and state"""
        self.settings.setValue("geometry", window.saveGeometry())
        self.settings.setValue("windowState", window.saveState())

    def restore_window_state(self, window):
        """Restore window geometry and state"""
        geometry = self.settings.value("geometry")
        if geometry:
            window.restoreGeometry(geometry)
        else:
            window.setGeometry(100, 100, 1000, 600)

        window_state = self.settings.value("windowState")
        if window_state:
            window.restoreState(window_state)

    def save_platform_directories(self, platform_directories):
        """Save platform directories"""
        for plat, directory in platform_directories.items():
            if directory:
                self.settings.setValue(f"{plat}_directory", directory)

    def load_platform_directories(self):
        """Load platform directories"""
        directories = {}
        for plat in ["xbox", "xbox360", "xbla"]:
            directory = self.settings.value(f"{plat}_directory", "")
            directories[plat] = directory
        return directories

    def save_theme_preference(self, theme_override):
        """Save theme preference"""
        if theme_override is None:
            self.settings.setValue("dark_mode_override", "auto")
        else:
            self.settings.setValue("dark_mode_override", str(theme_override).lower())

    def load_theme_preference(self):
        """Load theme preference"""
        dark_mode_setting = self.settings.value("dark_mode_override")
        if dark_mode_setting == "true":
            return True
        elif dark_mode_setting == "false":
            return False
        else:
            return None

    def save_table_settings(self, platform, header, sort_column, sort_order):
        """Save table column widths and sort settings"""
        show_dlcs = platform in ["xbla"]
        column_count = 6 if show_dlcs else 5

        for i in range(column_count):
            self.settings.setValue(
                f"{platform}_column_{i}_width",
                header.sectionSize(i),
            )

        self.settings.setValue(f"{platform}_sort_column", sort_column)
        self.settings.setValue(f"{platform}_sort_order", sort_order.value)

    def load_table_settings(self, platform):
        """Load table settings"""
        show_dlcs = platform in ["xbla"]
        column_count = 6 if show_dlcs else 5

        column_widths = {}
        for i in range(column_count):
            width = self.settings.value(f"{platform}_column_{i}_width")
            if width:
                column_widths[i] = int(width)

        sort_column = self.settings.value(f"{platform}_sort_column", 3)
        sort_order = self.settings.value(
            f"{platform}_sort_order", 0
        )  # Qt.SortOrder.AscendingOrder

        return column_widths, int(sort_column), int(sort_order)

    def save_current_platform(self, platform):
        """Save current platform selection"""
        self.settings.setValue("current_platform", platform)

    def load_current_platform(self):
        """Load current platform selection"""
        return self.settings.value("current_platform", "xbox360")

    def save_current_mode(self, mode: str):
        """Save current mode selection (ftp/usb)"""
        self.settings.setValue("current_mode", mode)

    def load_current_mode(self) -> str:
        """Load current mode selection"""
        return self.settings.value("current_mode", "usb")

    def save_usb_directories(self, usb_directories: Dict[str, str]):
        """Save USB directories for all platforms"""
        self.settings.setValue("usb_directories", usb_directories)

    def load_usb_directories(self) -> Dict[str, str]:
        """Load USB directories for all platforms"""
        default_directories = {"xbox": "", "xbox360": "", "xbla": ""}
        saved_directories = self.settings.value("usb_directories", {})

        # Ensure all platforms are present, merging saved with defaults
        if isinstance(saved_directories, dict):
            # Update defaults with saved values, keeping any missing keys
            default_directories.update(saved_directories)

        return default_directories

    def save_usb_target_directories(self, usb_target_directories: Dict[str, str]):
        """Save USB target directories for all platforms as individual keys"""
        for platform, directory in usb_target_directories.items():
            self.settings.setValue(f"usb_target_{platform}_directory", directory)

    def load_usb_target_directories(self) -> Dict[str, str]:
        """Load USB target directories for all platforms from individual keys"""
        directories = {}
        for platform in ["xbox", "xbox360", "xbla"]:
            directory = self.settings.value(f"usb_target_{platform}_directory", "")
            directories[platform] = directory
        return directories

    def save_usb_cache_directory(self, directory: str):
        """Save USB cache directory"""
        self.settings.setValue("usb_cache_directory", directory)

    def load_usb_cache_directory(self) -> str:
        """Load USB cache directory"""
        return self.settings.value("usb_cache_directory", "")

    def save_usb_content_directory(self, directory: str):
        """Save USB content directory"""
        self.settings.setValue("usb_content_directory", directory)

    def load_usb_content_directory(self) -> str:
        """Load USB content directory"""
        return self.settings.value("usb_content_directory", "")

    def save_ftp_settings(self, ftp_settings: dict):
        """Save FTP connection settings"""
        for key, value in ftp_settings.items():
            self.settings.setValue(f"ftp_{key}", value)

    def load_ftp_settings(self) -> dict:
        """Load FTP connection settings"""
        return {
            "host": self.settings.value("ftp_host", ""),
            "port": int(self.settings.value("ftp_port", 21)),
            "username": self.settings.value("ftp_username", ""),
            "password": self.settings.value("ftp_password", ""),
        }

    def save_xboxunity_settings(self, xboxunity_settings: dict):
        """Save Xbox Unity settings"""
        for key, value in xboxunity_settings.items():
            self.settings.setValue(f"xboxunity_{key}", value)

    def load_xboxunity_settings(self) -> dict:
        """Load Xbox Unity settings"""
        return {
            "username": self.settings.value("xboxunity_username", ""),
            "password": self.settings.value("xboxunity_password", ""),
            "api_key": self.settings.value("xboxunity_api_key", ""),
        }

    def save_ftp_target_directories(self, ftp_target_directories: dict):
        """Save FTP target directories for all platforms"""
        for platform, directory in ftp_target_directories.items():
            self.settings.setValue(f"ftp_target_{platform}_directory", directory)

    def load_ftp_target_directories(self) -> dict:
        """Load FTP target directories for all platforms"""
        directories = {}
        for platform in ["xbox", "xbox360", "xbla"]:
            directory = self.settings.value(f"ftp_target_{platform}_directory", "/")
            directories[platform] = directory
        return directories

    def save_ftp_cache_directory(self, directory: str):
        """Save FTP cache directory"""
        self.settings.setValue("ftp_cache_directory", directory)

    def load_ftp_cache_directory(self) -> str:
        """Load FTP cache directory"""
        return self.settings.value("ftp_cache_directory", "")

    def save_ftp_content_directory(self, directory: str):
        """Save FTP content directory"""
        self.settings.setValue("ftp_content_directory", directory)

    def load_ftp_content_directory(self) -> str:
        """Load FTP content directory"""
        return self.settings.value("ftp_content_directory", "")
