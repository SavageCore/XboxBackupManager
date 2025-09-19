#!/usr/bin/env python3
"""
UI Utilities - Consolidated UI helper functions to reduce code duplication
"""

from pathlib import Path
from typing import Optional, Union

from PyQt6.QtWidgets import QMessageBox, QWidget


class UIUtils:
    """Consolidated UI utility functions to avoid code duplication"""

    @staticmethod
    def show_warning(
        parent: Optional[QWidget],
        title: str,
        message: str,
        detailed_text: Optional[str] = None,
    ) -> None:
        """
        Show a standardized warning message box.

        Args:
            parent: Parent widget
            title: Dialog title
            message: Main message text
            detailed_text: Optional detailed text
        """
        msg_box = QMessageBox(parent)
        msg_box.setWindowTitle(title)
        msg_box.setText(message)
        msg_box.setIcon(QMessageBox.Icon.Warning)

        if detailed_text:
            msg_box.setDetailedText(detailed_text)

        msg_box.exec()

    @staticmethod
    def show_information(
        parent: Optional[QWidget],
        title: str,
        message: str,
        detailed_text: Optional[str] = None,
    ) -> None:
        """
        Show a standardized information message box.

        Args:
            parent: Parent widget
            title: Dialog title
            message: Main message text
            detailed_text: Optional detailed text
        """
        msg_box = QMessageBox(parent)
        msg_box.setWindowTitle(title)
        msg_box.setText(message)
        msg_box.setIcon(QMessageBox.Icon.Information)

        if detailed_text:
            msg_box.setDetailedText(detailed_text)

        msg_box.exec()

    @staticmethod
    def show_critical(
        parent: Optional[QWidget],
        title: str,
        message: str,
        detailed_text: Optional[str] = None,
    ) -> None:
        """
        Show a standardized critical error message box.

        Args:
            parent: Parent widget
            title: Dialog title
            message: Main message text
            detailed_text: Optional detailed text
        """
        msg_box = QMessageBox(parent)
        msg_box.setWindowTitle(title)
        msg_box.setText(message)
        msg_box.setIcon(QMessageBox.Icon.Critical)

        if detailed_text:
            msg_box.setDetailedText(detailed_text)

        msg_box.exec()

    @staticmethod
    def show_question(
        parent: Optional[QWidget],
        title: str,
        message: str,
        detailed_text: Optional[str] = None,
    ) -> bool:
        """
        Show a standardized question dialog with Yes/No buttons.

        Args:
            parent: Parent widget
            title: Dialog title
            message: Main message text
            detailed_text: Optional detailed text

        Returns:
            bool: True if Yes was clicked, False if No was clicked
        """
        msg_box = QMessageBox(parent)
        msg_box.setWindowTitle(title)
        msg_box.setText(message)
        msg_box.setIcon(QMessageBox.Icon.Question)
        msg_box.setStandardButtons(
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        msg_box.setDefaultButton(QMessageBox.StandardButton.Yes)

        if detailed_text:
            msg_box.setDetailedText(detailed_text)

        return msg_box.exec() == QMessageBox.StandardButton.Yes

    @staticmethod
    def validate_directory_exists(
        path: Union[str, Path],
        parent: Optional[QWidget] = None,
        action_description: str = "perform this action",
    ) -> bool:
        """
        Validate that a directory exists and show appropriate error message if not.

        Args:
            path: Path to validate
            parent: Parent widget for error dialog
            action_description: Description of what action requires the directory

        Returns:
            bool: True if directory exists and is accessible, False otherwise
        """
        if not path:
            UIUtils.show_warning(
                parent,
                "No Directory Selected",
                f"Please select a directory to {action_description}.",
            )
            return False

        path_obj = Path(path)

        if not path_obj.exists():
            UIUtils.show_warning(
                parent,
                "Directory Not Found",
                f"The directory does not exist:\n{path}\n\n"
                f"Please select a valid directory to {action_description}.",
            )
            return False

        if not path_obj.is_dir():
            UIUtils.show_warning(
                parent,
                "Invalid Directory",
                f"The path is not a directory:\n{path}\n\n"
                f"Please select a valid directory to {action_description}.",
            )
            return False

        # Test if directory is accessible
        try:
            list(path_obj.iterdir())
        except PermissionError:
            UIUtils.show_warning(
                parent,
                "Directory Not Accessible",
                f"The directory is not accessible:\n{path}\n\n"
                "Please ensure you have proper permissions and try again.",
            )
            return False
        except OSError as e:
            UIUtils.show_warning(
                parent,
                "Directory Access Error",
                f"Cannot access the directory:\n{path}\n\n"
                f"Error: {str(e)}\n\n"
                "Please ensure the device is properly connected and try again.",
            )
            return False

        return True

    @staticmethod
    def format_file_size(size_bytes: int) -> str:
        """
        Format file size in bytes to human readable format.

        Args:
            size_bytes: Size in bytes

        Returns:
            str: Formatted size string (e.g., "1.5 GB")
        """
        if size_bytes == 0:
            return "0 B"

        size_formatted = float(size_bytes)
        for unit in ["B", "KB", "MB", "GB", "TB", "PB"]:
            if size_formatted < 1024.0:
                break
            size_formatted /= 1024.0

        # Use appropriate decimal places based on size
        if size_formatted < 10:
            return f"{size_formatted:.2f} {unit}"
        elif size_formatted < 100:
            return f"{size_formatted:.1f} {unit}"
        else:
            return f"{size_formatted:.0f} {unit}"

    @staticmethod
    def build_target_path(
        base_path: str,
        platform: str,
        game_name: str,
        title_id: str,
        is_extracted_iso: bool = False,
    ) -> str:
        """
        Build target path for game transfers based on platform and game type.

        Args:
            base_path: Base target directory
            platform: Platform name (xbox, xbox360, xbla)
            game_name: Game name
            title_id: Game title ID
            is_extracted_iso: Whether this is an extracted ISO game

        Returns:
            str: Constructed target path
        """
        base = base_path.rstrip("/")

        if platform == "xbla":
            # XBLA always uses title ID
            return f"{base}/{title_id}"
        elif platform == "xbox360":
            # Xbox 360 uses game name for extracted ISOs, title ID for GoD
            if is_extracted_iso:
                return f"{base}/{game_name}"
            else:
                return f"{base}/{title_id}"
        else:  # xbox
            # Xbox uses game name
            return f"{base}/{game_name}"
