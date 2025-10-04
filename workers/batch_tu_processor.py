"""
Worker for batch processing title update downloads across multiple games
"""

import os
import time
from pathlib import Path
from typing import Any, Dict, List

from PyQt6.QtCore import QThread, pyqtSignal

from utils.ftp_connection_manager import get_ftp_manager
from utils.settings_manager import SettingsManager
from utils.title_update_utils import TitleUpdateUtils
from utils.xboxunity import XboxUnity


class BatchTitleUpdateProcessor(QThread):
    """Worker thread for batch processing title updates for multiple games"""

    # Signals
    progress_update = pyqtSignal(int, int)  # current, total
    game_started = pyqtSignal(str)  # game_name
    game_completed = pyqtSignal(str, int)  # game_name, updates_found
    update_downloaded = pyqtSignal(
        str, str, str
    )  # game_name, update_version, file_path
    update_progress = pyqtSignal(str, int)  # update_name, progress_percentage
    update_speed = pyqtSignal(str, float)  # update_name, speed_in_bytes_per_sec
    update_progress_bytes = pyqtSignal(
        str, int, int
    )  # update_name, current_bytes, total_bytes
    status_update = pyqtSignal(str)  # status_message
    searching = pyqtSignal(bool)  # True when searching, False when done
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

        # Fast FTP check if mode is ftp
        if self.current_mode == "ftp":
            ftp_manager = get_ftp_manager()
            ftp_client = ftp_manager.get_connection()
            if not ftp_client or not ftp_client.is_connected():
                self._log_message("FTP server not available, switching to USB mode.")
                self.status_update.emit(
                    "FTP server not available, switching to USB mode."
                )
                self.current_mode = "usb"

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

                # Log game processing start with spacing
                self._log_message("")  # Add spacing between games
                self._log_message(
                    f"Processing game: {game_name} (Title ID: {title_id})"
                )

                try:
                    # Get media ID from game folder (only for local paths)
                    media_id = None
                    if folder_path and Path(folder_path).exists():
                        self.searching.emit(True)  # Start indeterminate progress
                        self.status_update.emit(f"Getting media ID for {game_name}...")
                        media_id = self.xbox_unity.get_media_id(folder_path)

                        if not media_id:
                            self._log_message(
                                f"  Could not extract media ID from {game_name}"
                            )
                            # Continue anyway - media_id is optional
                    else:
                        # For FTP or non-existent paths, skip media_id extraction
                        self._log_message(
                            "  Skipping media ID extraction (remote/FTP path)"
                        )

                    # Search for title updates (media_id is optional, title_id is required)
                    self.status_update.emit(
                        f"Searching for title updates for {game_name}..."
                    )
                    updates = self.xbox_unity.search_title_updates(
                        media_id=media_id, title_id=title_id
                    )

                    if not updates:
                        self._log_message(f"  No title updates found for {game_name}")
                        self.status_update.emit(
                            f"No title updates found for {game_name}"
                        )
                        self.searching.emit(False)  # Stop indeterminate progress
                        self.game_completed.emit(game_name, 0)
                        continue

                    # Sort updates by version (highest first)
                    updates = sorted(
                        updates, key=lambda x: int(x.get("version", 0)), reverse=True
                    )

                    self.status_update.emit(
                        f"Found {len(updates)} update(s) for {game_name}, checking installation status..."
                    )

                    # Check if any update is already installed (highest version first)
                    installed_version = None
                    for update in updates:
                        if self._is_update_installed(title_id, update):
                            installed_version = int(update.get("version", 0))
                            break

                    if installed_version is not None:
                        self._log_message(
                            f"  Latest title update (version {installed_version}) already installed for {game_name}"
                        )
                        self.searching.emit(False)  # Stop indeterminate progress
                        self.game_completed.emit(game_name, 0)
                        continue

                    # No update installed, install the latest available version
                    latest_update = updates[0]
                    version = latest_update.get("version", "N/A")
                    self._log_message(
                        f"  Installing latest available version {version} for {game_name}"
                    )
                    self.status_update.emit(
                        f"Downloading version {version} for {game_name}..."
                    )
                    self.searching.emit(
                        False
                    )  # Stop indeterminate, start download progress
                    download_url = latest_update.get("downloadUrl", "")

                    # Initialize speed tracking for this download
                    start_time = time.time()
                    last_speed_update = time.time()
                    last_progress_update = time.time()
                    update_name = f"{game_name} v{version}"

                    # Create progress callback for this download
                    def progress_callback(downloaded, total):
                        nonlocal last_speed_update, last_progress_update
                        if total > 0:
                            current_time = time.time()

                            # Throttle updates to every 0.2 seconds to avoid UI overload
                            if current_time - last_progress_update >= 0.2:
                                progress = int((downloaded / total) * 100)
                                self.update_progress.emit(update_name, progress)
                                # Emit bytes for time remaining calculation
                                self.update_progress_bytes.emit(
                                    update_name, downloaded, total
                                )
                                last_progress_update = current_time

                            # Calculate and emit speed (update every 0.5 seconds)
                            if current_time - last_speed_update >= 0.5:
                                elapsed = current_time - start_time
                                if elapsed > 0:
                                    speed_bps = downloaded / elapsed
                                    self.update_speed.emit(update_name, speed_bps)
                                    last_speed_update = current_time

                    # Download the update
                    destination = os.path.join("cache", "tu", title_id) + os.sep
                    success, filename = self.xbox_unity.download_title_update(
                        download_url, destination, progress_callback=progress_callback
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

    def _is_update_installed(self, title_id: str, update: dict) -> bool:
        """Check if an update is already installed"""
        self._log_message(
            f"    Checking installation status for version {update.get('version', 'N/A')}"
        )
        try:
            version = update.get("version", "N/A")

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

            # Check installation
            result = TitleUpdateUtils._is_title_update_installed(
                title_id, update, self.current_mode, self.settings_manager
            )

            if result:
                self._log_message(f"    Version {version} is already installed")
                return True

            # If not installed, we need to download and install
            self._log_message(f"    Version {version} is not installed")
            return False

        except Exception as e:
            self._log_message(
                f"    Error checking installation status for version {version}: {str(e)}"
            )
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
                    # Size is now included in list_directory results
                    file_size = item.get("size", 0)
                    files.append((item["full_path"], item["name"], file_size))

        except Exception:
            pass

        return files

    def _install_update(self, local_path: str, title_id: str, filename: str) -> bool:
        """Install the downloaded update"""
        try:
            if self.current_mode == "ftp":
                # FTP installation logic
                return self._install_update_ftp(local_path, title_id, filename)
            else:
                # USB installation
                return self.xbox_unity.install_title_update(local_path, title_id)
        except Exception as e:
            self._log_message(f"    Error installing update: {str(e)}")
            return False

    def _install_update_ftp(
        self, local_path: str, title_id: str, filename: str
    ) -> bool:
        """Install title update to FTP server"""
        try:
            ftp_client = get_ftp_manager().get_connection()
            if not ftp_client:
                self._log_message("    [ERROR] Could not get FTP connection")
                return False

            # Determine destination based on filename case (same logic as USB)
            if filename.islower():
                # Move to Content folder
                # Example path: Content/0000000000000000/{TITLE_ID}/000B0000
                content_folder = self.settings_manager.load_ftp_content_directory()
                if not content_folder:
                    self._log_message(
                        "    [ERROR] FTP Content folder not found in settings."
                    )
                    return False

                # Ensure we're set to Content/0000000000000000/
                if not content_folder.endswith("0000000000000000"):
                    content_folder = f"{content_folder.rstrip('/')}/0000000000000000"

                destination_dir = f"{content_folder.rstrip('/')}/{title_id}/000B0000"
                destination_file = f"{destination_dir}/{filename}"

                # Create directory structure if it doesn't exist
                success, message = ftp_client.create_directory_recursive(
                    destination_dir
                )
                if not success:
                    self._log_message(
                        f"    Failed to create FTP directory {destination_dir}: {message}"
                    )
                    return False

                # Upload the file
                success, message = ftp_client.upload_file(local_path, destination_file)
                if success:
                    self._log_message(
                        f"    Installed title update to Content: {destination_file}"
                    )
                    return True
                else:
                    self._log_message(f"    Failed to upload to Content: {message}")
                    return False

            elif filename.isupper():
                # Move to Cache folder
                cache_folder = self.settings_manager.load_ftp_cache_directory()
                if not cache_folder:
                    self._log_message(
                        "    [ERROR] FTP Cache folder not found in settings."
                    )
                    return False

                destination_file = f"{cache_folder.rstrip('/')}/{filename}"
                cache_dir = cache_folder.rstrip("/")

                # Ensure cache directory exists
                success, message = ftp_client.create_directory_recursive(cache_dir)
                if not success:
                    self._log_message(
                        f"    Failed to create FTP cache directory {cache_dir}: {message}"
                    )
                    return False

                # Upload the file
                success, message = ftp_client.upload_file(local_path, destination_file)
                if success:
                    self._log_message(
                        f"    Installed title update to Cache: {destination_file}"
                    )
                    return True
                else:
                    self._log_message(f"    Failed to upload to Cache: {message}")
                    return False
            else:
                self._log_message(f"    Unknown filename format: {filename}")
                return False
            # Note: Don't disconnect - using persistent connection manager

        except Exception as e:
            self._log_message(f"    Error during FTP installation: {str(e)}")
            return False

    def _log_message(self, message: str):
        """Log a message to the debug file"""
        try:
            if self.log_file_path:
                with open(self.log_file_path, "a") as f:
                    f.write(f"{message}\n")
        except Exception:
            pass  # Ignore logging errors
