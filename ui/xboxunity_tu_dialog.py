import os
from pathlib import Path

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


class XboxUnityTitleUpdatesDialog(QDialog):
    """Dialog for viewing Xbox Unity title updates"""

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

    def _create_ftp_directory_recursive(self, ftp_client, path):
        """Recursively create FTP directory structure"""
        if not path or path == "/" or path == ".":
            return True

        # Split the path into parts
        parts = [p for p in path.split("/") if p]
        current_path = ""

        for part in parts:
            current_path = f"{current_path}/{part}" if current_path else part

            # Try to create the directory
            success, message = ftp_client.create_directory(current_path)
            if success:
                print(f"[INFO] Created FTP directory: {current_path}")
            elif (
                "already exists" in message.lower() or "file exists" in message.lower()
            ):
                print(f"[DEBUG] FTP directory already exists: {current_path}")
            else:
                print(
                    f"[ERROR] Failed to create FTP directory {current_path}: {message}"
                )
                return False

        return True

    def _is_title_update_installed(self, title_id: str, update) -> bool:
        """Check if a title update is installed by looking in Content and Cache folders"""
        print(
            f"[INFO] Checking if title update {update.get('fileName')} is installed..."
        )

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
            print("[INFO] No cached title update info available.")
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
                            print(
                                f"[INFO] Found installed title update file: {file} in {root}"
                            )
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
                print("[INFO] No cached title update info available.")
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
                        print(
                            f"[INFO] Found installed title update file: {filename} at {file_path} (size: {file_size})"
                        )
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
            print("[INFO] No cached title update info available.")
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
                                print(
                                    f"[INFO] Removed file: {os.path.join(root, file)}"
                                )
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
                print("[INFO] No cached title update info available.")
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
                            print(f"[INFO] Removed file: {file_path}")
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
                print(
                    "[INFO] Detected lowercase TU filename - installing to Content folder"
                )
                content_folder = self.settings_manager.load_ftp_content_directory()
                if content_folder:
                    if not content_folder.endswith("0000000000000000"):
                        content_folder = f"{content_folder}/0000000000000000"
                    remote_path = f"{content_folder}/{title_id}/000B0000/{filename}"
                else:
                    print("[ERROR] FTP Content folder not configured")
                    return False
            elif filename.isupper():
                print(
                    "[INFO] Detected uppercase TU filename - installing to Cache folder"
                )
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
            self._create_ftp_directory_recursive(ftp_client, remote_dir)

            # Upload the file
            print(f"[INFO] Uploading TU to FTP: {remote_path}")

            # Use the FTP client's built-in upload method if available
            # If not, we'll need to implement manual upload
            try:
                # Manual FTP upload since our FTPClient doesn't have upload method exposed
                with open(local_tu_path, "rb") as f:
                    # Get the internal FTP connection
                    if hasattr(ftp_client, "_ftp") and ftp_client._ftp:
                        ftp_client._ftp.storbinary(f"STOR {remote_path}", f)
                        print(f"[INFO] Successfully uploaded TU to FTP: {remote_path}")
                        return True
                    else:
                        print("[ERROR] FTP connection not available")
                        return False
            except Exception as e:
                print(f"[ERROR] Failed to upload TU to FTP: {e}")
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
        """Download and install a title update, then update button state"""
        button.setText("Downloading...")
        button.setEnabled(False)

        success, tu_filename = self.xbox_unity.download_title_update(url, destination)
        if success:
            local_tu_path = destination + tu_filename

            # Install based on current mode
            if self.current_mode == "ftp":
                install_success = self._install_title_update_ftp(
                    local_tu_path, title_id, tu_filename
                )
            else:
                install_success = self.xbox_unity.install_title_update(
                    local_tu_path, title_id
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
            else:
                button.setText("Download")
                button.setEnabled(True)
                print("Failed to install title update")
        else:
            button.setText("Download")
            button.setEnabled(True)
            print("Failed to download title update")
