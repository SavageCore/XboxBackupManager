#!/usr/bin/env python3
"""
Directory Manager - Handles directory operations and validation
"""

import os
from pathlib import Path
from typing import Dict, Optional

from PyQt6.QtCore import QFileSystemWatcher, QObject, pyqtSignal
from PyQt6.QtWidgets import QFileDialog

from utils.ui_utils import UIUtils


class DirectoryManager(QObject):
    """Manages directory operations and watching"""

    # Signals for directory changes
    directory_changed = pyqtSignal(str)  # new_directory
    directory_files_changed = pyqtSignal()  # files in directory changed

    def __init__(self, parent=None):
        super().__init__(parent)
        self.platform_directories: Dict[str, str] = {
            "xbox": "",
            "xbox360": "",
            "xbla": "",
        }
        self.usb_target_directories: Dict[str, str] = {
            "xbox": "",
            "xbox360": "",
            "xbla": "",
        }
        self.ftp_target_directories: Dict[str, str] = {
            "xbox": "/",
            "xbox360": "/",
            "xbla": "/",
        }

        self.current_directory = ""
        self.current_target_directory = ""
        self.usb_cache_directory = ""
        self.usb_content_directory = ""

        # File system watcher for directory changes
        self.file_watcher = QFileSystemWatcher()
        self.file_watcher.directoryChanged.connect(self.directory_files_changed.emit)

    def browse_directory(
        self, parent_widget, platform_name: str, start_dir: str = None
    ) -> Optional[str]:
        """Open directory selection dialog"""
        start_dir = start_dir or self.current_directory or os.path.expanduser("~")

        directory = QFileDialog.getExistingDirectory(
            parent_widget,
            f"Select {platform_name} Games Directory",
            start_dir,
        )

        if directory:
            normalized_directory = os.path.normpath(directory)
            return normalized_directory

        return None

    def set_current_directory(self, directory: str, platform: str) -> bool:
        """Set and validate current directory"""
        if not UIUtils.validate_directory_exists(directory):
            return False

        # Stop watching old directory
        self.stop_watching_directory()

        # Set new directory
        self.current_directory = directory
        self.platform_directories[platform] = directory

        # Start watching new directory
        self.start_watching_directory()

        self.directory_changed.emit(directory)
        return True

    def set_target_directory(self, directory: str, mode: str = "usb") -> bool:
        """Set and validate target directory"""
        if not self._validate_target_directory(directory):
            return False

        self.current_target_directory = directory
        return True

    def _validate_target_directory(self, directory: str) -> bool:
        """Validate target directory accessibility"""
        if not directory:
            return False

        normalized_directory = os.path.normpath(directory)

        try:
            # Test directory accessibility
            test_path = Path(normalized_directory)
            if test_path.exists() and test_path.is_dir():
                # Try to list contents to test accessibility
                list(test_path.iterdir())
                return True
        except (PermissionError, OSError):
            return False

        return False

    def start_watching_directory(self):
        """Start watching the current directory for changes"""
        if self.current_directory and os.path.exists(self.current_directory):
            if self.current_directory not in self.file_watcher.directories():
                self.file_watcher.addPath(self.current_directory)

    def stop_watching_directory(self):
        """Stop watching the current directory"""
        if self.file_watcher.directories():
            self.file_watcher.removePaths(self.file_watcher.directories())

    def get_platform_directory(self, platform: str) -> str:
        """Get directory for specified platform"""
        return self.platform_directories.get(platform, "")

    def set_platform_directory(self, platform: str, directory: str):
        """Set directory for specified platform"""
        self.platform_directories[platform] = directory

    def get_target_directory(self, mode: str, platform: str) -> str:
        """Get target directory for mode and platform"""
        if mode == "ftp":
            return self.ftp_target_directories.get(platform, "/")
        else:
            return self.usb_target_directories.get(platform, "")

    def set_target_directory_for_platform(
        self, mode: str, platform: str, directory: str
    ):
        """Set target directory for specific mode and platform"""
        if mode == "ftp":
            self.ftp_target_directories[platform] = directory
        else:
            self.usb_target_directories[platform] = directory

    def load_directories_from_settings(self, settings_manager):
        """Load directory settings"""
        self.platform_directories = settings_manager.load_platform_directories()
        self.usb_target_directories = settings_manager.load_usb_target_directories()
        self.ftp_target_directories = settings_manager.load_ftp_target_directories()
        self.usb_cache_directory = settings_manager.load_usb_cache_directory()
        self.usb_content_directory = settings_manager.load_usb_content_directory()

    def save_directories_to_settings(self, settings_manager):
        """Save directory settings"""
        settings_manager.save_platform_directories(self.platform_directories)
        settings_manager.save_usb_target_directories(self.usb_target_directories)
        settings_manager.save_ftp_target_directories(self.ftp_target_directories)
        settings_manager.save_usb_cache_directory(self.usb_cache_directory)
        settings_manager.save_usb_content_directory(self.usb_content_directory)
