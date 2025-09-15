"""
Worker for batch processing title update downloads across multiple games
"""

import os
from pathlib import Path
from typing import List, Dict, Any

from PyQt6.QtCore import QThread, pyqtSignal

from utils.xboxunity import XboxUnity
from utils.settings_manager import SettingsManager
from utils.ftp_client import FTPClient


class BatchTitleUpdateProcessor(QThread):
    """Worker thread for batch processing title updates for multiple games"""

    # Signals
    progress_update = pyqtSignal(int, int)  # current, total
    game_started = pyqtSignal(str)  # game_name
    game_completed = pyqtSignal(str, int)  # game_name, updates_found
    update_downloaded = pyqtSignal(
        str, str, str
    )  # game_name, update_version, file_path
    batch_complete = pyqtSignal(
        int, int
    )  # total_games_processed, total_updates_downloaded
    error_occurred = pyqtSignal(str)  # error_message

    def __init__(self):
        super().__init__()
        self.games_to_process = []
        self.current_mode = "usb"
        self.xbox_unity = XboxUnity()
        self.settings_manager = SettingsManager()
        self.should_stop = False
        self.log_file_path = None

    def setup_batch(self, games: List[Dict[str, Any]], mode: str):
        """Setup the batch processing with games list and mode"""
        self.games_to_process = games
        self.current_mode = mode
        self.should_stop = False

        # Create log file for debugging
        self.log_file_path = "batch_tu_download_log.txt"
        with open(self.log_file_path, "w") as f:
            f.write("Batch Title Update Download Log\n")
            f.write(f"Mode: {mode}\n")
            f.write(f"Total Games: {len(games)}\n")
            f.write("=" * 50 + "\n\n")

    def stop_processing(self):
        """Stop the batch processing"""
        self.should_stop = True

    def run(self):
        """Main processing loop"""
        if not self.games_to_process:
            self.error_occurred.emit("No games to process")
            return

        total_games = len(self.games_to_process)
        total_updates_downloaded = 0

        try:
            for i, game in enumerate(self.games_to_process):
                if self.should_stop:
                    break

                game_name = game.get("name", "Unknown")
                title_id = game.get("title_id", "")
                folder_path = game.get("folder_path", "")

                self.game_started.emit(game_name)
                self.progress_update.emit(i + 1, total_games)

                # Log game processing start
                self._log_message(
                    f"Processing game: {game_name} (Title ID: {title_id})"
                )

                try:
                    # Get media ID from game folder
                    media_id = self._get_media_id_for_game(folder_path, title_id)
                    if not media_id:
                        self._log_message(f"  No media ID found for {game_name}")
                        self.game_completed.emit(game_name, 0)
                        continue

                    # Search for title updates
                    updates = self.xbox_unity.search_title_updates(
                        media_id=media_id, title_id=title_id
                    )

                    if not updates:
                        self._log_message(f"  No title updates found for {game_name}")
                        self.game_completed.emit(game_name, 0)
                        continue

                    # Sort updates by version (highest first)
                    updates = sorted(
                        updates, key=lambda x: int(x.get("version", 0)), reverse=True
                    )

                    # Check if the latest version is already installed
                    latest_version = updates[0] if updates else None
                    if latest_version and self._is_update_installed(
                        title_id, latest_version
                    ):
                        self._log_message(
                            f"  Latest title update (version {latest_version.get('version')}) already installed for {game_name}"
                        )
                        self.game_completed.emit(game_name, 0)
                        continue

                    # Find the highest version that's not installed
                    latest_update = None
                    for update in updates:
                        if not self._is_update_installed(title_id, update):
                            latest_update = update
                            break

                    if not latest_update:
                        self._log_message(
                            f"  All title updates already installed for {game_name}"
                        )
                        self.game_completed.emit(game_name, 0)
                        continue

                    # Download and install the latest missing update
                    version = latest_update.get("version", "N/A")
                    download_url = latest_update.get("downloadUrl", "")

                    self._log_message(
                        f"  Downloading version {version} for {game_name}"
                    )

                    # Download the update
                    destination = os.path.join("cache", "tu", title_id) + os.sep
                    success, filename = self.xbox_unity.download_title_update(
                        download_url, destination
                    )

                    if success:
                        local_path = os.path.join(destination, filename)
                        self._log_message(f"  Downloaded: {local_path}")

                        # Install the update
                        install_success = self._install_update(
                            local_path, title_id, filename
                        )

                        if install_success:
                            self._log_message(
                                f"  Successfully installed version {version} for {game_name}"
                            )
                            self.update_downloaded.emit(game_name, version, local_path)
                            total_updates_downloaded += 1
                        else:
                            self._log_message(
                                f"  Failed to install version {version} for {game_name}"
                            )
                    else:
                        self._log_message(
                            f"  Failed to download version {version} for {game_name}"
                        )

                    self.game_completed.emit(game_name, 1 if success else 0)

                except Exception as e:
                    self._log_message(f"  Error processing {game_name}: {str(e)}")
                    self.game_completed.emit(game_name, 0)

        except Exception as e:
            self.error_occurred.emit(f"Batch processing error: {str(e)}")
            return

        self._log_message(
            f"\nBatch processing complete. Total updates downloaded: {total_updates_downloaded}"
        )
        self.batch_complete.emit(total_games, total_updates_downloaded)

    def _get_media_id_for_game(self, folder_path: str, title_id: str) -> str:
        """Get media ID for a game from its folder"""
        try:
            # Get header path for GoD parsing
            god_header_path = Path(folder_path) / "00007000"
            header_files = list(god_header_path.glob("*"))

            if not header_files:
                return None

            god_header_path = str(header_files[0])
            media_id = XboxUnity.get_media_id(self.xbox_unity, god_header_path)
            return media_id
        except Exception as e:
            self._log_message(f"    Error getting media ID: {str(e)}")
            return None

    def _is_update_installed(self, title_id: str, update: dict) -> bool:
        """Check if an update is already installed"""
        try:
            version = update.get("version", "N/A")
            self._log_message(f"    Checking if version {version} is installed...")

            # Get update info first
            download_url = update.get("downloadUrl", "")
            title_update_info = self.xbox_unity.get_title_update_information(
                download_url
            )

            if not title_update_info:
                self._log_message(
                    f"    Could not get title update info for version {version}"
                )
                return False

            update["cached_info"] = title_update_info

            # Check installation based on current mode
            if self.current_mode == "ftp":
                result = self._is_title_update_installed_ftp(title_id, update)
            else:
                result = self._is_title_update_installed_usb(title_id, update)

            return result

        except Exception as e:
            self._log_message(
                f"    Error checking installation status for version {version}: {str(e)}"
            )
            return False

    def _is_title_update_installed_usb(self, title_id: str, update) -> bool:
        """Check if title update is installed on USB/local storage"""
        try:
            content_folder = self.settings_manager.load_usb_content_directory()
            cache_folder = self.settings_manager.load_usb_cache_directory()

            if content_folder:
                if not content_folder.endswith("0000000000000000"):
                    content_folder = os.path.join(content_folder, "0000000000000000")
            else:
                return False

            possible_paths = [
                os.path.join(content_folder, title_id, "000B0000"),
                cache_folder,
            ]

            title_update_info = update.get("cached_info")
            if not title_update_info:
                return False

            expected_filename = title_update_info.get("fileName", "")
            expected_size = title_update_info.get("size", 0)
            self._log_message(
                f"    Looking for file: {expected_filename} (size: {expected_size})"
            )

            for base_path in possible_paths:
                if base_path and os.path.exists(base_path):
                    for root, dirs, files in os.walk(base_path):
                        for file in files:
                            file_size = os.path.getsize(os.path.join(root, file))
                            if (
                                file.upper() == expected_filename.upper()
                                and file_size == expected_size
                            ):
                                self._log_message(
                                    f"    Found installed title update file: {file} in {root}"
                                )
                                return True
            return False
        except Exception as e:
            self._log_message(f"    Error checking USB installation: {str(e)}")
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
                        self._log_message(
                            f"    Found installed title update file: {filename} at {file_path}"
                        )
                        return True

            return False

        except Exception as e:
            self._log_message(f"    Error checking FTP installation: {str(e)}")
            return False
        finally:
            ftp_client.disconnect()

    def _get_ftp_connection(self):
        """Create and return an FTP connection using settings"""
        try:
            ftp_settings = self.settings_manager.load_ftp_settings()
            ftp_host = ftp_settings.get("host")
            ftp_port = ftp_settings.get("port")
            ftp_user = ftp_settings.get("username")
            ftp_pass = ftp_settings.get("password")

            if not all([ftp_host, ftp_port, ftp_user, ftp_pass]):
                self._log_message("    [ERROR] FTP credentials not configured")
                return None

            ftp_client = FTPClient()
            success, message = ftp_client.connect(
                ftp_host, ftp_user, ftp_pass, int(ftp_port)
            )

            if success:
                return ftp_client
            else:
                self._log_message(f"    [ERROR] FTP connection failed: {message}")
                return None

        except Exception as e:
            self._log_message(f"    [ERROR] Failed to connect to FTP: {e}")
            return None

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
            self._log_message(f"    [DEBUG] Error listing FTP directory {path}: {e}")

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
                    self._log_message(
                        f"    [DEBUG] Could not get size for {filepath}: {e}"
                    )
                    return 0
            else:
                return 0
        except Exception as e:
            self._log_message(
                f"    [DEBUG] Error getting FTP file size for {filepath}: {e}"
            )
            return 0

    def _install_update(self, local_path: str, title_id: str, filename: str) -> bool:
        """Install the downloaded update"""
        try:
            if self.current_mode == "ftp":
                # FTP installation logic would go here
                # For now, just return True as a placeholder
                return True
            else:
                # USB installation
                return self.xbox_unity.install_title_update(local_path, title_id)
        except Exception as e:
            self._log_message(f"    Error installing update: {str(e)}")
            return False

    def _log_message(self, message: str):
        """Log a message to the debug file"""
        try:
            if self.log_file_path:
                with open(self.log_file_path, "a") as f:
                    f.write(f"{message}\n")
        except Exception:
            pass  # Ignore logging errors
