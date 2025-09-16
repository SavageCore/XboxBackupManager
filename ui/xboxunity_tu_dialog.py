import os
from pathlib import Path

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import (
    QDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
)

from utils.ftp_client import FTPClient
from utils.settings_manager import SettingsManager
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
        # Sort updates by version number (descending) - highest version first
        self.updates = sorted(
            self.updates, key=lambda x: int(x.get("version", 0)), reverse=True
        )
        self.current_mode = parent.current_mode if parent else "usb"

        # Initialize download worker
        self.download_worker = TitleUpdateDownloadWorker()
        self.download_worker.download_progress.connect(self.download_progress.emit)
        self.download_worker.download_complete.connect(self._on_download_complete)
        self.download_worker.download_error.connect(self.download_error.emit)

        self._init_ui()

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
        ftp_client = self._get_ftp_connection()
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
            print(f"Removed title update files: {removed_files}")
            button.setText("Download")
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
        ftp_client = self._get_ftp_connection()
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
                print(f"Removed title update files: {removed_files}")
                button.setText("Download")
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
        ftp_client = self._get_ftp_connection()
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
        self.setMinimumWidth(400)

        layout = QVBoxLayout(self)

        updates_group = QGroupBox(f"Title Updates for {self.title_id}")
        updates_layout = QFormLayout(updates_group)

        for update in self.updates:
            version = update.get("version", "N/A")
            media_id = update.get("mediaId", "")
            download_url = update.get("downloadUrl", "")
            title_update_info = self.xbox_unity.get_title_update_information(
                download_url
            )
            update["cached_info"] = title_update_info

            version_input = QLineEdit()
            version_input.setText(version)
            version_input.setReadOnly(True)

            size_input = QLineEdit()
            size_input.setText(f"{int(update.get('size', 0)) / 1024:.2f} MB")
            size_input.setReadOnly(True)

            date_input = QLineEdit()
            date_input.setText(update.get("uploadDate", "N/A"))
            date_input.setReadOnly(True)

            # Check if title update is already installed
            is_installed = self._is_title_update_installed(self.title_id, update)

            download_input = QPushButton("Uninstall" if is_installed else "Download")

            update_layout = QHBoxLayout()
            update_layout.addWidget(version_input)
            update_layout.addWidget(size_input)
            update_layout.addWidget(date_input)

            destination = f"cache/tu/{self.title_id}/"

            if is_installed:
                # Connect uninstall action
                download_input.clicked.connect(
                    lambda checked, ver=version, mid=media_id, btn=download_input, upd=update: self._uninstall_title_update(
                        self.title_id, ver, mid, btn, upd
                    )
                )
            else:
                # Connect download and install action
                download_input.clicked.connect(
                    lambda checked, url=download_url, btn=download_input, ver=version, mid=media_id, upd=update: self._download_and_install(
                        url, destination, self.title_id, btn, ver, mid, upd
                    )
                )

            update_layout.addWidget(download_input)
            updates_layout.addRow(f"Version {version}:", update_layout)

        layout.addWidget(updates_group)

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
                print("Failed to install title update")
                self.download_error.emit(update_name, "Installation failed")
        else:
            button.setText("Download")
            button.setEnabled(True)
            print("Failed to download title update")

        # Clean up pending install info
        del self._pending_installs[update_name]
