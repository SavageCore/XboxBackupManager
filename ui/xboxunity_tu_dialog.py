import locale
import os
from datetime import datetime
from pathlib import Path

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from utils.ftp_client import FTPClient
from utils.ftp_connection_manager import get_ftp_manager
from utils.settings_manager import SettingsManager
from utils.system_utils import SystemUtils
from utils.title_update_utils import TitleUpdateUtils
from utils.ui_utils import UIUtils
from utils.xboxunity import XboxUnity
from workers.title_update_downloader import TitleUpdateDownloadWorker


class XboxUnityTitleUpdatesDialog(QDialog):
    """Dialog for viewing Xbox Unity title updates"""

    # Signals to communicate with main window
    download_started = pyqtSignal(str)  # title_update_name
    download_progress = pyqtSignal(str, int)  # title_update_name, percentage
    download_complete = pyqtSignal(
        str, bool, str, str
    )  # title_update_name, success, filename, local_path
    download_error = pyqtSignal(str, str)  # title_update_name, error_message

    def __init__(self, parent=None, title_id=None, updates=None):
        super().__init__(parent)
        self.title_id = title_id
        self.updates = updates or []
        self.xbox_unity = XboxUnity()
        self.settings_manager = SettingsManager()
        self.game_manager = parent.game_manager if parent else None
        # Sort updates by version number (descending) - highest version first
        self.updates = sorted(
            self.updates, key=lambda x: int(x.get("version", 0)), reverse=True
        )
        self.current_mode = parent.current_mode if parent else "usb"

        self.ftp_client = FTPClient()

        # Initialize download worker
        self.download_worker = TitleUpdateDownloadWorker()
        self.download_worker.download_progress.connect(self.download_progress.emit)
        self.download_worker.download_complete.connect(self._on_download_complete)
        self.download_worker.download_error.connect(self.download_error.emit)

        self.game_name = (
            self.game_manager.get_game_name(self.title_id)
            if self.game_manager
            else "Unknown Game"
        )

        self._init_ui()

    def _create_path_label(self, display_text: str):
        """Create a plain path label (not clickable)"""
        label = QLabel(display_text)
        label.setStyleSheet(
            """
            QLabel {
                font-size: 9px;
                color: rgba(255,255,255,0.6);
                font-family: monospace;
            }
            """
        )
        label.setWordWrap(True)
        return label

    def _get_install_info(self, title_id: str, update) -> dict:
        """Get installation information (filename and path) for an installed title update"""
        if self.current_mode == "ftp":
            return self._get_install_info_ftp(title_id, update)
        else:
            return self._get_install_info_usb(title_id, update)

    def _get_install_info_usb(self, title_id: str, update) -> dict:
        """Get install info for USB/local storage"""
        content_folder = self.settings_manager.load_usb_content_directory()
        cache_folder = self.settings_manager.load_usb_cache_directory()

        result = TitleUpdateUtils.find_install_info(
            title_id, update, content_folder, cache_folder, is_ftp=False
        )
        return result

    def _get_install_info_ftp(self, title_id: str, update) -> dict:
        """Get install info for FTP server"""
        ftp_client = get_ftp_manager().get_connection()
        if not ftp_client:
            return None

        try:
            content_folder = self.settings_manager.load_ftp_content_directory()
            cache_folder = self.settings_manager.load_ftp_cache_directory()

            return TitleUpdateUtils.find_install_info(
                title_id,
                update,
                content_folder,
                cache_folder,
                is_ftp=True,
                ftp_client=ftp_client,
            )
        finally:
            ftp_client.disconnect()

    def _is_title_update_installed(self, title_id: str, update) -> bool:
        """Check if a title update is installed by looking in Content and Cache folders"""
        if self.current_mode == "ftp":
            return self._is_title_update_installed_ftp(title_id, update)
        else:
            return self._is_title_update_installed_usb(title_id, update)

    def _is_title_update_installed_usb(self, title_id: str, update) -> bool:
        """Check if title update is installed on USB/local storage"""
        content_folder = self.settings_manager.load_usb_content_directory()
        cache_folder = self.settings_manager.load_usb_cache_directory()

        if content_folder:
            if not content_folder.endswith("0000000000000000"):
                content_folder = os.path.join(content_folder, "0000000000000000")
        else:
            return False

        possible_paths = [
            f"{content_folder}/{title_id}/000B0000",
            cache_folder,
        ]

        title_update_info = update.get("cached_info")
        if not title_update_info:
            return False

        for base_path in possible_paths:
            if base_path and os.path.exists(base_path):
                for root, dirs, files in os.walk(base_path):
                    for file in files:
                        if file.upper() == title_update_info.get(
                            "fileName", ""
                        ).upper() and os.path.getsize(
                            os.path.join(root, file)
                        ) == title_update_info.get(
                            "size", 0
                        ):
                            return True
        return False

    def _is_title_update_installed_ftp(self, title_id: str, update) -> bool:
        """Check if title update is installed on FTP server"""
        ftp_client = get_ftp_manager().get_connection()
        if not ftp_client:
            return False

        try:
            content_folder = self.settings_manager.load_ftp_content_directory()
            cache_folder = self.settings_manager.load_ftp_cache_directory()

            if content_folder and not content_folder.endswith("0000000000000000"):
                content_folder = f"{content_folder}/0000000000000000"

            possible_paths = [
                f"{content_folder}/{title_id}/000B0000" if content_folder else None,
                cache_folder,
            ]

            title_update_info = update.get("cached_info")
            if not title_update_info:
                return False

            expected_filename = title_update_info.get("fileName", "")
            expected_size = title_update_info.get("size", 0)

            for base_path in possible_paths:
                if not base_path:
                    continue

                # Get recursive file listing from FTP
                files = self.ftp_client._ftp_list_files_recursive(ftp_client, base_path)

                for file_path, filename, file_size in files:
                    if (
                        filename.upper() == expected_filename.upper()
                        and file_size == expected_size
                    ):
                        return True

            return False

        finally:
            ftp_client.disconnect()

    def _uninstall_title_update(
        self,
        title_id: str,
        version: str,
        media_id: str,
        button: QPushButton,
        update: dict,
    ) -> None:
        """Uninstall a title update by removing it from Content and Cache folders"""
        if self.current_mode == "ftp":
            self._uninstall_title_update_ftp(
                title_id, version, media_id, button, update
            )
        else:
            self._uninstall_title_update_usb(
                title_id, version, media_id, button, update
            )

    def _uninstall_title_update_usb(
        self,
        title_id: str,
        version: str,
        media_id: str,
        button: QPushButton,
        update: dict,
    ) -> None:
        """Uninstall title update from USB/local storage"""
        removed_files = []

        content_folder = self.settings_manager.load_usb_content_directory()
        cache_folder = self.settings_manager.load_usb_cache_directory()

        if content_folder and not content_folder.endswith("0000000000000000"):
            content_folder = os.path.join(content_folder, "0000000000000000")

        possible_paths = [
            f"{content_folder}/{title_id}/000B0000" if content_folder else None,
            cache_folder,
        ]

        title_update_info = update.get("cached_info")
        if not title_update_info:
            return

        for base_path in possible_paths:
            if base_path and os.path.exists(base_path):
                for root, dirs, files in os.walk(base_path):
                    for file in files:
                        if file.upper() == title_update_info.get(
                            "fileName", ""
                        ).upper() and os.path.getsize(
                            os.path.join(root, file)
                        ) == title_update_info.get(
                            "size", 0
                        ):
                            try:
                                os.remove(os.path.join(root, file))
                                removed_files.append(os.path.join(root, file))
                            except Exception as e:
                                print(f"Error removing file {file}: {e}")

        if removed_files:
            button.setText("Download")
            # Update button styling to blue for download
            button.setStyleSheet(
                """
                QPushButton {
                    background-color: #3498db;
                    color: white;
                    border: none;
                    border-radius: 5px;
                    padding: 8px 16px;
                    font-size: 12px;
                    font-weight: 500;
                }
                QPushButton:hover {
                    background-color: #2980b9;
                }
                QPushButton:pressed {
                    background-color: #21618c;
                }
                QPushButton:disabled {
                    background-color: #95a5a6;
                    color: #ecf0f1;
                }
            """
            )
            button.clicked.disconnect()
            # Reconnect to download action
            download_url = update.get("downloadUrl", "")
            destination = f"cache/tu/{title_id}/"
            button.clicked.connect(
                lambda checked, url=download_url, btn=button, ver=version, mid=media_id, upd=update: self._download_and_install(
                    url, destination, title_id, btn, ver, mid, upd
                )
            )
        else:
            print("No title update files found to remove")

    def _uninstall_title_update_ftp(
        self,
        title_id: str,
        version: str,
        media_id: str,
        button: QPushButton,
        update: dict,
    ) -> None:
        """Uninstall title update from FTP server"""
        ftp_client = get_ftp_manager().get_connection()
        if not ftp_client:
            print("[ERROR] Could not connect to FTP server")
            return

        try:
            removed_files = []

            content_folder = self.settings_manager.load_ftp_content_directory()
            cache_folder = self.settings_manager.load_ftp_cache_directory()

            if content_folder and not content_folder.endswith("0000000000000000"):
                content_folder = f"{content_folder}/0000000000000000"

            possible_paths = [
                f"{content_folder}/{title_id}/000B0000" if content_folder else None,
                cache_folder,
            ]

            title_update_info = update.get("cached_info")
            if not title_update_info:
                return

            expected_filename = title_update_info.get("fileName", "")

            for base_path in possible_paths:
                if not base_path:
                    continue

                # Get recursive file listing from FTP
                files = self.ftp_client._ftp_list_files_recursive(ftp_client, base_path)

                for file_path, filename, file_size in files:
                    if filename.upper() == expected_filename.upper():
                        success, message = ftp_client.remove_file(file_path)
                        if success:
                            removed_files.append(file_path)
                        else:
                            print(
                                f"[ERROR] Failed to remove file {file_path}: {message}"
                            )

            if removed_files:
                button.setText("Download")
                # Update button styling to blue for download
                button.setStyleSheet(
                    """
                    QPushButton {
                        background-color: #3498db;
                        color: white;
                        border: none;
                        border-radius: 5px;
                        padding: 8px 16px;
                        font-size: 12px;
                        font-weight: 500;
                    }
                    QPushButton:hover {
                        background-color: #2980b9;
                    }
                    QPushButton:pressed {
                        background-color: #21618c;
                    }
                    QPushButton:disabled {
                        background-color: #95a5a6;
                        color: #ecf0f1;
                    }
                """
                )
                button.clicked.disconnect()
                # Reconnect to download action
                download_url = update.get("downloadUrl", "")
                destination = f"cache/tu/{title_id}/"
                button.clicked.connect(
                    lambda checked, url=download_url, btn=button, ver=version, mid=media_id, upd=update: self._download_and_install(
                        url, destination, title_id, btn, ver, mid, upd
                    )
                )
            else:
                print("No title update files found to remove")

        finally:
            ftp_client.disconnect()

    def _install_title_update_ftp(
        self, local_tu_path: str, title_id: str, filename: str
    ) -> bool:
        """Install title update to FTP server"""
        ftp_client = get_ftp_manager().get_connection()
        if not ftp_client:
            print("[ERROR] Could not connect to FTP server")
            return False

        try:
            # Determine destination based on filename case (same logic as USB)
            if filename.islower():
                content_folder = self.settings_manager.load_ftp_content_directory()
                if content_folder:
                    if not content_folder.endswith("0000000000000000"):
                        content_folder = f"{content_folder}/0000000000000000"
                    remote_path = f"{content_folder}/{title_id}/000B0000/{filename}"
                else:
                    print("[ERROR] FTP Content folder not configured")
                    return False
            elif filename.isupper():
                cache_folder = self.settings_manager.load_ftp_cache_directory()
                if cache_folder:
                    remote_path = f"{cache_folder}/{filename}"
                else:
                    print("[ERROR] FTP Cache folder not configured")
                    return False
            else:
                print(
                    "[ERROR] Unable to determine TU destination based on filename case"
                )
                return False

            # Create remote directory structure recursively
            remote_dir = str(Path(remote_path).parent).replace("\\", "/")
            success, message = ftp_client.create_directory_recursive(remote_dir)
            if not success:
                print(f"[ERROR] Failed to create FTP directory structure: {message}")
                return False

            # Upload the file
            success, message = ftp_client.upload_file(local_tu_path, remote_path)
            if success:
                return True
            else:
                print(f"[ERROR] Failed to upload TU to FTP: {message}")
                return False

        finally:
            ftp_client.disconnect()

    def _init_ui(self):
        """Initialize the dialog UI"""
        self.setWindowTitle("Xbox Unity Title Updates")
        self.setModal(True)
        self.setMinimumSize(800, 400)  # Increased width for better layout
        self.resize(850, 450)

        # Main layout
        main_layout = QVBoxLayout(self)
        main_layout.setSpacing(10)
        main_layout.setContentsMargins(15, 15, 15, 15)

        # Title header
        title_label = QLabel(f"Title Updates for {self.game_name} ({self.title_id})")
        title_label.setStyleSheet(
            """
                    QLabel {
                        font-size: 16px;
                        font-weight: bold;
                        padding: 5px 0px;
                    }
                """
        )
        main_layout.addWidget(title_label)

        # Scroll area for Title Updates
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll_area.setStyleSheet(
            """
                    QScrollArea {
                        border: 1px solid rgba(255,255,255,0.1);
                        border-radius: 5px;
                        background-color: transparent;
                    }
                """
        )

        # Content widget for scroll area
        content_widget = QWidget()
        content_layout = QVBoxLayout(content_widget)
        content_layout.setSpacing(8)
        content_layout.setContentsMargins(8, 8, 8, 8)

        # Process each Title Update
        for i, update in enumerate(self.updates):
            version = update.get("version", "N/A")
            media_id = update.get("mediaId", "")
            download_url = update.get("downloadUrl", "")

            # Get cached title update info
            title_update_info = self.xbox_unity.get_title_update_information(
                download_url
            )
            update["cached_info"] = title_update_info

            # Format date with system locale
            upload_date = update.get("uploadDate", "")
            try:
                if upload_date and upload_date != "N/A":
                    # Parse the date (format: 2014-02-12 00:00:00)
                    dt = datetime.strptime(upload_date, "%Y-%m-%d %H:%M:%S")

                    # Use system locale for date formatting
                    try:
                        # Try to use locale-specific formatting
                        locale.setlocale(locale.LC_TIME, "")  # Use system default
                        date_text = dt.strftime(
                            "%x"
                        )  # Short date format according to locale

                        # If the result looks too short/numeric, use a longer format
                        if (
                            len(date_text) < 8
                            or date_text.count("/") >= 2
                            or date_text.count("-") >= 2
                        ):
                            # Use a more readable medium format
                            date_text = dt.strftime("%d %b %Y")  # e.g., "12 Feb 2014"
                    except (locale.Error, OSError):
                        # Fallback to a universal format if locale fails
                        date_text = dt.strftime("%d %b %Y")  # e.g., "12 Feb 2014"
                else:
                    date_text = "Unknown date"
            except Exception:
                date_text = upload_date if upload_date else "Unknown date"

            # Format size - try multiple sources for size data
            size_bytes = 0
            if title_update_info and title_update_info.get("size"):
                size_bytes = title_update_info.get("size", 0)
            elif update.get("size"):
                size_bytes = update.get("size", 0)

            if size_bytes > 0:
                size_mb = size_bytes / (1024 * 1024)
                size_text = f"{size_mb:.1f} MB"
            else:
                size_text = "Unknown size"

            # Create update card with fixed height - restore alternating backgrounds
            update_frame = QFrame()
            update_frame.setFixedHeight(80)  # Fixed height for consistency
            update_frame.setStyleSheet(
                f"""
                        QFrame {{
                            background-color: {'rgba(255,255,255,0.05)' if i % 2 == 0 else 'rgba(255,255,255,0.02)'};
                            border: 1px solid rgba(255,255,255,0.1);
                            border-radius: 6px;
                            margin: 1px;
                        }}
                    """
            )

            card_layout = QHBoxLayout(update_frame)
            card_layout.setSpacing(12)
            card_layout.setContentsMargins(12, 8, 12, 8)

            # Left side: Version, Date, Path
            left_widget = QWidget()
            left_widget.setFixedWidth(450)
            left_widget.setStyleSheet("background: transparent;")
            left_layout = QVBoxLayout(left_widget)
            left_layout.setSpacing(1)
            left_layout.setContentsMargins(0, 0, 0, 0)

            # Version
            version_label = QLabel(f"Version {version}")
            version_label.setStyleSheet(
                """
                        QLabel {
                            font-size: 14px;
                            font-weight: 600;
                            border: none;
                            margin: 0px;
                            padding: 0px;
                        }
                    """
            )
            version_label.setWordWrap(False)
            left_layout.addWidget(version_label)

            # Date
            date_label = QLabel(date_text)
            date_label.setStyleSheet(
                """
                        QLabel {
                            border: none;
                            margin: 0px;
                            padding: 0px;
                        }
                    """
            )
            date_label.setWordWrap(False)
            left_layout.addWidget(date_label)

            # Path info (smallest, most muted)
            is_installed = self._is_title_update_installed(self.title_id, update)

            if is_installed:
                install_info = self._get_install_info(self.title_id, update)
                filename = install_info["filename"]
                if install_info:
                    if install_info["location"] == "Content":
                        display_text = f"📁 Content/{self.title_id}/000B0000/{filename}"
                        full_text = f"Content/0000000000000000/{self.title_id}/000B0000/{filename}"
                    else:
                        display_text = f"📁 {install_info['location']}/{filename}"
                        full_text = f"{install_info['location']}/{filename}"
                    path_filename_label = self._create_path_label(display_text)
            else:
                # Show predicted install location for non-installed updates
                title_update_info = update.get("cached_info")
                if title_update_info:
                    filename = title_update_info.get("fileName", "Unknown")

                    # Determine installation path based on filename case
                    if filename.islower():
                        display_text = f"📁 Content/{self.title_id}/000B0000/{filename}"
                        full_text = f"Content/0000000000000000/{self.title_id}/000B0000/{filename}"
                    elif filename.isupper():
                        display_text = f"📁 Cache/{filename}"
                        full_text = f"Cache/{filename}"
                    path_filename_label = self._create_path_label(display_text)
                else:
                    path_filename_label = self._create_path_label("Unknown/Unknown")

            path_filename_label.setToolTip(full_text)
            path_filename_label.setStyleSheet(
                """
                        QLabel {
                            border: none;
                            font-size: 14px;
                            color: rgba(255,255,255,0.4);
                            margin: 0px;
                            padding: 0px;
                            font-family: 'Consolas', 'Monaco', monospace;
                        }
                        QLabel:hover {
                            color: #4FC3F7;
                            text-decoration: underline;
                        }
                    """
            )
            path_filename_label.setTextInteractionFlags(
                Qt.TextInteractionFlag.TextBrowserInteraction
            )
            path_filename_label.setCursor(Qt.CursorShape.PointingHandCursor)
            path_filename_label.mousePressEvent = (
                lambda event: self._open_tu_in_explorer()
            )
            left_layout.addWidget(path_filename_label)

            # Push content to top
            left_layout.addStretch()

            size_widget = QWidget()
            size_widget.setFixedWidth(110)
            size_widget.setStyleSheet("background: transparent;")
            size_layout = QVBoxLayout(size_widget)
            size_layout.setContentsMargins(0, 0, 0, 0)

            size_button = QPushButton(size_text)
            size_button.setFixedSize(100, 32)
            size_button.setEnabled(False)  # Disable interaction
            size_button.setStyleSheet(
                """
                        QPushButton {
                            font-size: 12px;
                            color: rgba(255,255,255,0.85);
                            font-weight: 600;
                            background-color: rgba(255,255,255,0.08);
                            border: 1px solid rgba(255,255,255,0.15);
                            border-radius: 5px;
                            margin: 0px;
                            padding: 0px;
                        }
                    """
            )

            # Center the button vertically
            size_layout.addStretch()
            size_layout.addWidget(size_button, alignment=Qt.AlignmentFlag.AlignCenter)
            size_layout.addStretch()

            # Right side: Action button (clean, no extra containers)
            button_widget = QWidget()
            button_widget.setStyleSheet("background: transparent;")
            button_widget.setFixedWidth(110)
            button_layout = QVBoxLayout(button_widget)
            button_layout.setContentsMargins(0, 0, 0, 0)

            action_button = QPushButton("Uninstall" if is_installed else "Install")
            action_button.setFixedSize(100, 32)
            action_button.setStyleSheet(
                f"""
                        QPushButton {{
                            background-color: {'#e74c3c' if is_installed else '#3498db'};
                            color: white;
                            border: none;
                            border-radius: 5px;
                            font-size: 12px;
                            font-weight: 500;
                            margin: 0px;
                        }}
                        QPushButton:hover {{
                            background-color: {'#c0392b' if is_installed else '#2980b9'};
                        }}
                        QPushButton:pressed {{
                            background-color: {'#a93226' if is_installed else '#21618c'};
                        }}
                        QPushButton:disabled {{
                            background-color: #95a5a6;
                            color: #ecf0f1;
                        }}
                    """
            )

            # Center the button vertically
            button_layout.addStretch()
            button_layout.addWidget(
                action_button, alignment=Qt.AlignmentFlag.AlignCenter
            )
            button_layout.addStretch()

            destination = f"cache/tu/{self.title_id}/"

            if is_installed:
                # Connect uninstall action
                action_button.clicked.connect(
                    lambda checked, ver=version, mid=media_id, btn=action_button, upd=update: self._uninstall_title_update(
                        self.title_id, ver, mid, btn, upd
                    )
                )
            else:
                # Connect download and install action
                action_button.clicked.connect(
                    lambda checked, url=download_url, btn=action_button, ver=version, mid=media_id, upd=update: self._download_and_install(
                        url, destination, self.title_id, btn, ver, mid, upd
                    )
                )

            # Add all widgets to card layout with proper stretch factors
            card_layout.addWidget(left_widget, 0)  # Fixed size, no stretch
            card_layout.addWidget(size_widget, 0)  # Fixed size, no stretch
            card_layout.addWidget(button_widget, 0)  # Fixed size, no stretch
            # Remove the addStretch that was causing layout issues

            content_layout.addWidget(update_frame)

        # Add stretch to push everything to the top
        content_layout.addStretch()

        # Set the content widget to scroll area
        scroll_area.setWidget(content_widget)
        main_layout.addWidget(scroll_area)

        # Close button at bottom
        close_button = QPushButton("Close")
        close_button.setStyleSheet(
            """
                    QPushButton {
                        background-color: #95a5a6;
                        color: white;
                        border: none;
                        border-radius: 5px;
                        padding: 10px 20px;
                        font-size: 12px;
                        font-weight: 500;
                    }
                    QPushButton:hover {
                        background-color: #7f8c8d;
                    }
                """
        )
        close_button.clicked.connect(self.close)

        button_layout = QHBoxLayout()
        button_layout.addStretch()
        button_layout.addWidget(close_button)

        main_layout.addLayout(button_layout)

    def _open_tu_in_explorer(self):
        """Open the TU file's containing folder in Explorer"""
        # TUs are stored in cache/tu/<title_id>/<file_name>
        tu_path = os.path.abspath(os.path.join("cache/tu", self.title_id))
        if os.path.exists(tu_path):
            SystemUtils.open_folder_in_explorer(tu_path, self)
        else:
            UIUtils.show_warning(
                self, "File Not Found", f"TU file not found:\n{tu_path}"
            )

    def _init_ui_old(self):
        """Initialize the dialog UI with modern design"""
        self.setWindowTitle("Manage Title Updates")
        self.setModal(True)
        self.setMinimumSize(600, 400)
        self.resize(650, 450)

        # Main layout
        main_layout = QVBoxLayout(self)
        main_layout.setSpacing(10)
        main_layout.setContentsMargins(15, 15, 15, 15)

        # Title header
        title_label = QLabel(f"Title Updates for {self.game_name} ({self.title_id})")
        title_label.setStyleSheet(
            """
            QLabel {
                font-size: 16px;
                font-weight: bold;
                padding: 5px 0px;
            }
        """
        )
        main_layout.addWidget(title_label)

        # Scroll area for updates
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll_area.setStyleSheet(
            """
            QScrollArea {
                border: 1px solid rgba(255,255,255,0.1);
                border-radius: 5px;
                background-color: transparent;
            }
        """
        )

        # Content widget for scroll area
        content_widget = QWidget()
        content_layout = QVBoxLayout(content_widget)
        content_layout.setSpacing(8)
        content_layout.setContentsMargins(8, 8, 8, 8)

        # Process each update
        for i, update in enumerate(self.updates):
            version = update.get("version", "N/A")
            media_id = update.get("mediaId", "")
            download_url = update.get("downloadUrl", "")

            # Get cached title update info
            title_update_info = self.xbox_unity.get_title_update_information(
                download_url
            )
            update["cached_info"] = title_update_info

            # Format size - try multiple sources for size data
            size_bytes = 0
            if title_update_info and title_update_info.get("size"):
                size_bytes = title_update_info.get("size", 0)
            elif update.get("size"):
                size_bytes = update.get("size", 0)

            if size_bytes > 0:
                size_mb = size_bytes / (1024 * 1024)
                size_text = f"{size_mb:.1f} MB"
            else:
                size_text = "Unknown size"

            # Format date with system locale
            upload_date = update.get("uploadDate", "")
            try:
                if upload_date and upload_date != "N/A":
                    # Parse the date (format: 2014-02-12 00:00:00)
                    dt = datetime.strptime(upload_date, "%Y-%m-%d %H:%M:%S")

                    # Use system locale for date formatting
                    try:
                        # Try to use locale-specific formatting
                        locale.setlocale(locale.LC_TIME, "")  # Use system default
                        date_text = dt.strftime(
                            "%x"
                        )  # Short date format according to locale

                        # If the result looks too short/numeric, use a longer format
                        if (
                            len(date_text) < 8
                            or date_text.count("/") >= 2
                            or date_text.count("-") >= 2
                        ):
                            # Use a more readable medium format
                            date_text = dt.strftime("%d %b %Y")  # e.g., "12 Feb 2014"
                    except (locale.Error, OSError):
                        # Fallback to a universal format if locale fails
                        date_text = dt.strftime("%d %b %Y")  # e.g., "12 Feb 2014"
                else:
                    date_text = "Unknown date"
            except Exception:
                date_text = upload_date if upload_date else "Unknown date"

            # Create update card
            update_frame = QFrame()
            update_frame.setStyleSheet(
                f"""
                QFrame {{
                    background-color: {'rgba(255,255,255,0.05)' if i % 2 == 0 else 'rgba(255,255,255,0.02)'};
                    border: 1px solid rgba(255,255,255,0.1);
                    border-radius: 6px;
                    margin: 1px;
                }}
            """
            )

            card_layout = QHBoxLayout(update_frame)
            card_layout.setSpacing(12)
            card_layout.setContentsMargins(10, 8, 10, 8)

            # Version info (left side)
            version_layout = QVBoxLayout()
            version_layout.setSpacing(2)

            version_label = QLabel(f"Version {version}")
            version_label.setStyleSheet(
                """
                QLabel {
                    font-size: 13px;
                    font-weight: bold;
                    color: white;
                    border: none;
                }
            """
            )

            date_label = QLabel(date_text)
            date_label.setStyleSheet(
                """
                QLabel {
                    font-size: 10px;
                    color: rgba(255,255,255,0.7);
                    border: none;
                }
            """
            )

            version_layout.addWidget(version_label)
            version_layout.addWidget(date_label)

            # Size info (center)
            size_label = QLabel(size_text)
            size_label.setStyleSheet(
                """
                QLabel {
                    font-size: 11px;
                    color: rgba(255,255,255,0.8);
                    font-weight: 500;
                    border: none;
                }
            """
            )
            size_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            size_label.setMinimumWidth(70)  # Reduce minimum width

            # Action button (right side)
            is_installed = self._is_title_update_installed(self.title_id, update)

            # Add path/filename info for all updates in single line format
            # First check if it's actually installed to get real info
            if is_installed:
                install_info = self._get_install_info(self.title_id, update)
                filename = (
                    os.path.basename(install_info["path"])
                    if install_info
                    else "Unknown"
                )
                if install_info:
                    display_text = f"📁 {install_info['location']}/{filename}"
                    path_filename_label = self._create_path_label(display_text)
                else:
                    # Fallback if we can't get install info
                    title_update_info = update.get("cached_info")
                    filename = (
                        title_update_info.get("fileName", "Unknown")
                        if title_update_info
                        else "Unknown"
                    )
                    display_text = f"Unknown/{filename}"
                    path_filename_label = self._create_path_label(display_text)
            else:
                # Show predicted install location for non-installed updates
                title_update_info = update.get("cached_info")
                if title_update_info:
                    filename = title_update_info.get("fileName", "Unknown")

                    # Determine installation path based on filename case
                    if filename.islower():
                        display_text = f"Content/0000000000000000/{self.title_id}/000B0000/{filename}"
                    elif filename.isupper():
                        display_text = f"Cache/{filename}"
                    else:
                        display_text = f"Unknown/{filename}"
                    path_filename_label = self._create_path_label(display_text)
                else:
                    path_filename_label = self._create_path_label("Unknown/Unknown")

            # Add the label to the layout
            version_layout.addWidget(path_filename_label)

            action_button = QPushButton("Uninstall" if is_installed else "Download")
            action_button.setFixedWidth(100)  # Fixed width for consistent sizing
            action_button.setStyleSheet(
                f"""
                QPushButton {{
                    background-color: {'#e74c3c' if is_installed else '#3498db'};
                    color: white;
                    border: none;
                    border-radius: 5px;
                    padding: 8px 16px;
                    font-size: 12px;
                    font-weight: 500;
                }}
                QPushButton:hover {{
                    background-color: {'#c0392b' if is_installed else '#2980b9'};
                }}
                QPushButton:pressed {{
                    background-color: {'#a93226' if is_installed else '#21618c'};
                }}
                QPushButton:disabled {{
                    background-color: #95a5a6;
                    color: #ecf0f1;
                }}
            """
            )

            destination = f"cache/tu/{self.title_id}/"

            if is_installed:
                # Connect uninstall action
                action_button.clicked.connect(
                    lambda checked, ver=version, mid=media_id, btn=action_button, upd=update: self._uninstall_title_update(
                        self.title_id, ver, mid, btn, upd
                    )
                )
            else:
                # Connect download and install action
                action_button.clicked.connect(
                    lambda checked, url=download_url, btn=action_button, ver=version, mid=media_id, upd=update: self._download_and_install(
                        url, destination, self.title_id, btn, ver, mid, upd
                    )
                )

            # Add widgets to card layout
            card_layout.addLayout(version_layout, 2)  # Take up more space
            card_layout.addWidget(size_label, 1)
            card_layout.addWidget(action_button, 0)  # Fixed size

            content_layout.addWidget(update_frame)

        # Add stretch to push everything to the top
        content_layout.addStretch()

        # Set the content widget to scroll area
        scroll_area.setWidget(content_widget)
        main_layout.addWidget(scroll_area)

        # Close button at bottom
        close_button = QPushButton("Close")
        close_button.setStyleSheet(
            """
            QPushButton {
                background-color: #95a5a6;
                color: white;
                border: none;
                border-radius: 5px;
                padding: 10px 20px;
                font-size: 12px;
                font-weight: 500;
            }
            QPushButton:hover {
                background-color: #7f8c8d;
            }
        """
        )
        close_button.clicked.connect(self.close)

        button_layout = QHBoxLayout()
        button_layout.addStretch()
        button_layout.addWidget(close_button)

        main_layout.addLayout(button_layout)

    def _download_and_install(
        self,
        url: str,
        destination: str,
        title_id: str,
        button: QPushButton,
        version: str,
        media_id: str,
        update: dict,
    ) -> None:
        """Download and install a title update using background worker"""
        button.setText("Downloading...")
        button.setEnabled(False)

        # Store button and update info for later use
        update_name = f"{title_id}_v{version}"
        self._pending_installs = getattr(self, "_pending_installs", {})
        self._pending_installs[update_name] = {
            "button": button,
            "title_id": title_id,
            "version": version,
            "media_id": media_id,
            "update": update,
            "destination": destination,
        }

        # Emit signal to main window to show progress
        self.download_started.emit(update_name)

        # Add download to worker queue and start
        self.download_worker.add_download(update_name, url, destination)
        if not self.download_worker.isRunning():
            self.download_worker.start()

    def _on_download_complete(
        self, update_name: str, success: bool, filename: str, local_path: str
    ):
        """Handle download completion and proceed with installation"""
        if (
            not hasattr(self, "_pending_installs")
            or update_name not in self._pending_installs
        ):
            return

        install_info = self._pending_installs[update_name]
        button = install_info["button"]
        title_id = install_info["title_id"]
        version = install_info["version"]
        media_id = install_info["media_id"]
        update = install_info["update"]

        if success:
            button.setText("Installing...")

            # Install based on current mode
            if self.current_mode == "ftp":
                install_success = self._install_title_update_ftp(
                    local_path, title_id, filename
                )
            else:
                install_success = self.xbox_unity.install_title_update(
                    local_path, title_id
                )

            if install_success:
                button.setText("Uninstall")
                button.setEnabled(True)
                # Update button styling to red for uninstall
                button.setStyleSheet(
                    """
                    QPushButton {
                        background-color: #e74c3c;
                        color: white;
                        border: none;
                        border-radius: 5px;
                        padding: 8px 16px;
                        font-size: 12px;
                        font-weight: 500;
                    }
                    QPushButton:hover {
                        background-color: #c0392b;
                    }
                    QPushButton:pressed {
                        background-color: #a93226;
                    }
                    QPushButton:disabled {
                        background-color: #95a5a6;
                        color: #ecf0f1;
                    }
                """
                )
                button.clicked.disconnect()
                button.clicked.connect(
                    lambda checked, upd=update: self._uninstall_title_update(
                        title_id, version, media_id, button, upd
                    )
                )

                # Emit success signal to main window
                self.download_complete.emit(update_name, True, filename, local_path)
            else:
                button.setText("Download")
                button.setEnabled(True)
                # Update button styling to blue for download
                button.setStyleSheet(
                    """
                    QPushButton {
                        background-color: #3498db;
                        color: white;
                        border: none;
                        border-radius: 5px;
                        padding: 8px 16px;
                        font-size: 12px;
                        font-weight: 500;
                    }
                    QPushButton:hover {
                        background-color: #2980b9;
                    }
                    QPushButton:pressed {
                        background-color: #21618c;
                    }
                    QPushButton:disabled {
                        background-color: #95a5a6;
                        color: #ecf0f1;
                    }
                """
                )
                print("Failed to install title update")
                self.download_error.emit(update_name, "Installation failed")
        else:
            button.setText("Download")
            button.setEnabled(True)
            # Update button styling to blue for download
            button.setStyleSheet(
                """
                QPushButton {
                    background-color: #3498db;
                    color: white;
                    border: none;
                    border-radius: 5px;
                    padding: 8px 16px;
                    font-size: 12px;
                    font-weight: 500;
                }
                QPushButton:hover {
                    background-color: #2980b9;
                }
                QPushButton:pressed {
                    background-color: #21618c;
                }
                QPushButton:disabled {
                    background-color: #95a5a6;
                    color: #ecf0f1;
                }
            """
            )
            print("Failed to download title update")

        # Clean up pending install info
        del self._pending_installs[update_name]
