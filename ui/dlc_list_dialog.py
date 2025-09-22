import os
from pathlib import Path

from PyQt6.QtCore import Qt
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

from utils.dlc_utils import DLCUtils
from utils.ftp_client import FTPClient
from utils.settings_manager import SettingsManager
from utils.system_utils import SystemUtils
from utils.title_update_utils import TitleUpdateUtils
from utils.ui_utils import UIUtils
from utils.xboxunity import XboxUnity


class DLCListDialog(QDialog):
    """Dialog for viewing DLCs"""

    def __init__(self, title_id: str, parent=None):
        super().__init__(parent)
        self.title_id = title_id
        self.dlc_files = []

        self.xbox_unity = XboxUnity()
        self.settings_manager = SettingsManager()
        self.game_manager = parent.game_manager if parent else None
        self.current_mode = parent.current_mode if parent else "usb"

        self.dlc_utils = DLCUtils()
        self.ui_utils = UIUtils()

        self.game_name = (
            self.game_manager.get_game_name(self.title_id) or "Unknown Game"
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

    def _get_ftp_connection(self):
        """Create and return an FTP connection using settings"""
        try:
            self.ftp_settings = self.settings_manager.load_ftp_settings()
            ftp_host = self.ftp_settings.get("host")
            ftp_port = self.ftp_settings.get("port")
            ftp_user = self.ftp_settings.get("username")
            ftp_pass = self.ftp_settings.get("password")

            if not all([ftp_host, ftp_port, ftp_user, ftp_pass]):
                print("[ERROR] FTP credentials not configured")
                return None

            ftp_client = FTPClient()
            success, message = ftp_client.connect(
                ftp_host, ftp_user, ftp_pass, int(ftp_port)
            )

            if success:
                return ftp_client
            else:
                print(f"[ERROR] FTP connection failed: {message}")
                return None

        except Exception as e:
            print(f"[ERROR] Failed to connect to FTP: {e}")
            return None

    def _ftp_file_exists_with_size(self, ftp_client, filepath, expected_size):
        """Check if a file exists on FTP server with the expected size"""
        try:
            # Get directory listing for the parent directory
            parent_dir = str(Path(filepath).parent).replace("\\", "/")
            filename = Path(filepath).name

            success, items, error = ftp_client.list_directory(parent_dir)
            if not success:
                return False

            for item in items:
                if (
                    item["name"].upper() == filename.upper()
                    and not item["is_directory"]
                ):
                    # For FTP, we need to get file size differently
                    # This is a simplified check - you might need to enhance this
                    return True

            return False
        except Exception as e:
            print(f"[DEBUG] Error checking FTP file {filepath}: {e}")
            return False

    def _ftp_list_files_recursive(self, ftp_client, path):
        """Recursively list files in FTP directory with size information"""
        files = []
        try:
            success, items, error = ftp_client.list_directory(path)
            if not success:
                return files

            for item in items:
                if item["is_directory"]:
                    # Recursively list subdirectories
                    files.extend(
                        self._ftp_list_files_recursive(ftp_client, item["full_path"])
                    )
                else:
                    # Get file size using FTP SIZE command
                    file_size = self._get_ftp_file_size(ftp_client, item["full_path"])
                    files.append((item["full_path"], item["name"], file_size))

        except Exception as e:
            print(f"[DEBUG] Error listing FTP directory {path}: {e}")

        return files

    def _get_ftp_file_size(self, ftp_client, filepath):
        """Get the size of a file on FTP server"""
        try:
            # Use the FTP SIZE command if the client supports it
            if hasattr(ftp_client, "_ftp") and ftp_client._ftp:
                try:
                    size = ftp_client._ftp.size(filepath)
                    return size if size is not None else 0
                except Exception as e:
                    print(f"[DEBUG] Could not get size for {filepath}: {e}")
                    return 0
            else:
                return 0
        except Exception as e:
            print(f"[DEBUG] Error getting FTP file size for {filepath}: {e}")
            return 0

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

        return TitleUpdateUtils.find_install_info(
            title_id, update, content_folder, cache_folder, is_ftp=False
        )

    def _get_install_info_ftp(self, title_id: str, update) -> dict:
        """Get install info for FTP server"""
        ftp_client = self._get_ftp_connection()
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

    def _is_dlc_installed(self, title_id: str, dlc) -> bool:
        """Check if a DLC is installed by looking in Content folder"""
        if self.current_mode == "ftp":
            return self._is_dlc_installed_ftp(title_id, dlc)
        else:
            return self._is_dlc_installed_usb(title_id, dlc)

    def _is_dlc_installed_usb(self, title_id: str, dlc) -> bool:
        """Check if DLC is installed on USB/local storage"""
        content_folder = self.settings_manager.load_usb_content_directory()

        if content_folder:
            if not content_folder.endswith("0000000000000000"):
                content_folder = os.path.join(content_folder, "0000000000000000")
        else:
            return False

        possible_paths = [
            f"{content_folder}/{title_id}/00000002",
        ]

        for base_path in possible_paths:
            if base_path and os.path.exists(base_path):
                for root, dirs, files in os.walk(base_path):
                    for file in files:
                        if file.upper() == dlc.get(
                            "file", ""
                        ).upper() and os.path.getsize(
                            os.path.join(root, file)
                        ) == dlc.get(
                            "size", 0
                        ):
                            return True
        return False

    def _is_dlc_installed_ftp(self, title_id: str, dlc) -> bool:
        """Check if DLC is installed on FTP server"""
        ftp_client = self._get_ftp_connection()
        if not ftp_client:
            return False

        try:
            content_folder = self.settings_manager.load_ftp_content_directory()

            if content_folder and not content_folder.endswith("0000000000000000"):
                content_folder = f"{content_folder}/0000000000000000"

            possible_paths = [
                f"{content_folder}/{title_id}/000B0000" if content_folder else None,
            ]

            expected_filename = dlc.get("file", "")
            expected_size = dlc.get("size", 0)

            for base_path in possible_paths:
                if not base_path:
                    continue

                # Get recursive file listing from FTP
                files = self._ftp_list_files_recursive(ftp_client, base_path)

                for file_path, filename, file_size in files:
                    if (
                        filename.upper() == expected_filename.upper()
                        and file_size == expected_size
                    ):
                        return True

            return False

        finally:
            ftp_client.disconnect()

    def _uninstall_dlc(
        self,
        title_id: str,
        button: QPushButton,
        dlc: dict,
    ) -> None:
        """Uninstall a DLC by removing it from Content folder"""
        if self.current_mode == "ftp":
            self._uninstall_dlc_ftp(title_id, button, dlc)
        else:
            self._uninstall_dlc_usb(title_id, button, dlc)

    def _uninstall_dlc_usb(
        self,
        title_id: str,
        button: QPushButton,
        dlc: dict,
    ) -> None:
        """Uninstall DLC from USB/local storage"""
        removed_files = []

        content_folder = self.settings_manager.load_usb_content_directory()

        if content_folder and not content_folder.endswith("0000000000000000"):
            content_folder = os.path.join(content_folder, "0000000000000000")

        possible_paths = [
            f"{content_folder}/{title_id}/00000002" if content_folder else None,
        ]

        for base_path in possible_paths:
            if base_path and os.path.exists(base_path):
                for root, dirs, files in os.walk(base_path):
                    for file in files:
                        if file.upper() == dlc.get(
                            "file", ""
                        ).upper() and os.path.getsize(
                            os.path.join(root, file)
                        ) == dlc.get(
                            "size", 0
                        ):
                            try:
                                os.remove(os.path.join(root, file))
                                removed_files.append(os.path.join(root, file))
                            except Exception as e:
                                print(f"Error removing file {file}: {e}")

        if removed_files:
            button.setText("Install")
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
            # Reconnect to install action
            button.clicked.connect(
                lambda checked, btn=button, dlc=dlc: self._install(btn=btn, dlc=dlc)
            )
        else:
            print("No DLC files found to remove")

    def _uninstall_dlc_ftp(
        self,
        title_id: str,
        button: QPushButton,
        dlc: dict,
    ) -> None:
        """Uninstall DLC from FTP server"""
        ftp_client = self._get_ftp_connection()
        if not ftp_client:
            print("[ERROR] Could not connect to FTP server")
            return

        try:
            removed_files = []

            content_folder = self.settings_manager.load_ftp_content_directory()

            if content_folder and not content_folder.endswith("0000000000000000"):
                content_folder = f"{content_folder}/0000000000000000"

            possible_paths = [
                f"{content_folder}/{title_id}/dlc" if content_folder else None,
            ]

            expected_filename = dlc.get("file", "")

            for base_path in possible_paths:
                if not base_path:
                    continue

                # Get recursive file listing from FTP
                files = self._ftp_list_files_recursive(ftp_client, base_path)

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
                # Reconnect to install action
                button.clicked.connect(
                    lambda checked, btn=button, dlc=dlc: self._install(btn, dlc)
                )
            else:
                print("No title update files found to remove")

        finally:
            ftp_client.disconnect()

    def _install_dlc_ftp(
        self, local_dlc_path: str, title_id: str, filename: str
    ) -> bool:
        """Install DLC to FTP server"""
        ftp_client = self._get_ftp_connection()
        if not ftp_client:
            print("[ERROR] Could not connect to FTP server")
            return False

        try:
            content_folder = self.settings_manager.load_ftp_content_directory()
            if content_folder:
                if not content_folder.endswith("0000000000000000"):
                    content_folder = f"{content_folder}/0000000000000000"
                remote_path = f"{content_folder}/{title_id}/00000002/{filename}"
            else:
                print("[ERROR] FTP Content folder not configured")
                return False

            # Create remote directory structure recursively
            remote_dir = str(Path(remote_path).parent).replace("\\", "/")
            success, message = ftp_client.create_directory_recursive(remote_dir)
            if not success:
                print(f"[ERROR] Failed to create FTP directory structure: {message}")
                return False

            # Upload the file
            success, message = ftp_client.upload_file(local_dlc_path, remote_path)
            if success:
                return True
            else:
                print(f"[ERROR] Failed to upload DLC to FTP: {message}")
                return False

        finally:
            ftp_client.disconnect()

    def _install_dlc_usb(
        self, local_dlc_path: str, title_id: str, filename: str
    ) -> bool:
        """Install DLC to USB"""
        if not os.path.exists(local_dlc_path):
            print(f"[ERROR] Local DLC file not found: {local_dlc_path}")
            return False

        content_folder = self.settings_manager.load_usb_content_directory()
        if content_folder:
            if not content_folder.endswith("0000000000000000"):
                content_folder = os.path.join(content_folder, "0000000000000000")
            remote_path = os.path.join(content_folder, title_id, "00000002", filename)
        else:
            print("[ERROR] USB Content folder not configured")
            return False

        # Create local directory structure if it doesn't exist
        remote_dir = os.path.dirname(remote_path)
        os.makedirs(remote_dir, exist_ok=True)
        try:
            # Copy the file
            with open(local_dlc_path, "rb") as src_file:
                with open(remote_path, "wb") as dest_file:
                    dest_file.write(src_file.read())
            return True
        except Exception as e:
            print(f"[ERROR] Failed to copy DLC to USB: {e}")
            return False

    def _init_ui(self):
        """Initialize the dialog UI"""
        self.setWindowTitle("Manage DLC")
        self.setModal(True)
        self.setMinimumSize(800, 400)  # Increased width for better layout
        self.resize(850, 450)

        # Main layout
        main_layout = QVBoxLayout(self)
        main_layout.setSpacing(10)
        main_layout.setContentsMargins(15, 15, 15, 15)

        # Title header
        title_label = QLabel(f"DLCs for {self.game_name} ({self.title_id})")
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

        # Scroll area for DLCs
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

        dlcs = self.dlc_utils.load_dlc_index(self.title_id)
        if not dlcs:
            return False

        # Process each DLC
        for i, dlc in enumerate(dlcs):
            dlc_name = dlc.get("display_name", "N/A")
            dlc_description = dlc.get("description", "")
            dlc_size = dlc.get("size", "Unknown size")

            size_text = self.ui_utils.format_file_size(dlc_size)

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

            # Left side: Name and description with clean text layout
            left_widget = QWidget()
            left_widget.setFixedWidth(450)
            left_widget.setStyleSheet("background: transparent;")
            left_layout = QVBoxLayout(left_widget)
            left_layout.setSpacing(1)
            left_layout.setContentsMargins(0, 0, 0, 0)

            # DLC Name (bold, larger)
            name_label = QLabel(dlc_name)
            name_label.setStyleSheet(
                """
                    QLabel {
                        border: none;
                        font-size: 14px;
                        font-weight: bold;
                        color: white;
                        margin: 0px;
                        padding: 0px;
                    }
                """
            )
            name_label.setWordWrap(False)
            name_label_text = dlc_name if len(dlc_name) <= 55 else dlc_name[:52] + "..."
            name_label.setText(name_label_text)
            left_layout.addWidget(name_label)

            # Description (if different from name, smaller, muted)
            desc_label = QLabel()
            desc_label.setStyleSheet(
                """
                    QLabel {
                        border: none;
                        font-size: 14px;
                        color: rgba(255,255,255,0.65);
                        margin: 0px;
                        padding: 0px;
                        font-style: italic;
                    }
                """
            )
            display_desc = (
                dlc_description
                if len(dlc_description) <= 65
                else dlc_description[:62] + "..."
            )
            desc_label.setText(display_desc)
            desc_label.setWordWrap(False)

            if len(dlc_description) > 65:
                desc_label.setToolTip(dlc_description)
                desc_label.setToolTipDuration(5000)

            left_layout.addWidget(desc_label)

            # Path info (smallest, most muted)
            file_name = dlc.get("file", "Unknown")
            display_text = f"📁 00000002/{file_name}"
            path_label = QLabel(f"{display_text}")
            path_label.setStyleSheet(
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
            path_label.setTextInteractionFlags(
                Qt.TextInteractionFlag.TextBrowserInteraction
            )
            path_label.setCursor(Qt.CursorShape.PointingHandCursor)
            path_label.mousePressEvent = lambda event: self._open_dlc_in_explorer()
            left_layout.addWidget(path_label)

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

            is_installed = self._is_dlc_installed(self.title_id, dlc)

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

            # Connect button actions
            if is_installed:
                action_button.clicked.connect(
                    lambda checked, btn=action_button, dlc=dlc: self._uninstall_dlc(
                        self.title_id, btn, dlc
                    )
                )
            else:
                action_button.clicked.connect(
                    lambda checked, btn=action_button, dlc=dlc: self._install(btn, dlc)
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

    def _install(self, btn: QPushButton, dlc: dict) -> None:
        """Install the selected DLC"""
        title_id = dlc.get("title_id", "")
        filename = dlc.get("file", "")

        local_dlc_path = f"cache/dlc/{title_id}/{filename}"
        if not local_dlc_path or not os.path.exists(local_dlc_path):
            print(f"[ERROR] Local DLC file not found: {local_dlc_path}")
            return

        if self.current_mode == "ftp":
            success = self._install_dlc_ftp(local_dlc_path, title_id, filename)
        else:
            success = self._install_dlc_usb(local_dlc_path, title_id, filename)

        if success:
            btn.setText("Uninstall")
            # Update button styling to red for uninstall
            btn.setStyleSheet(
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
            btn.clicked.disconnect()
            # Reconnect to uninstall action
            btn.clicked.connect(
                lambda checked, b=btn, d=dlc: self._uninstall_dlc(title_id, b, d)
            )
        else:
            print(f"[ERROR] Failed to install DLC: {filename}")

    def _open_dlc_in_explorer(self):
        """Open the DLC file's containing folder in Explorer"""
        # DLCs are stored in cache/dlc/<title_id>/<file_name>
        dlc_path = os.path.abspath(os.path.join("cache", "dlc", self.title_id))
        if os.path.exists(dlc_path):
            SystemUtils.open_folder_in_explorer(dlc_path, self)
        else:
            UIUtils.show_warning(
                self, "File Not Found", f"DLC file not found:\n{dlc_path}"
            )
