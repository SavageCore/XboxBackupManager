"""
Worker for batch processing DLC installation across multiple games
"""

from typing import Any, Dict, List

from PyQt6.QtCore import QThread, pyqtSignal

from managers.game_manager import GameManager
from utils.dlc_utils import DLCUtils
from utils.settings_manager import SettingsManager


class BatchDLCInstallProcessor(QThread):
    """Worker thread for batch processing DLC installation for multiple games"""

    # Signals
    progress_update = pyqtSignal(int, int)  # current, total
    game_started = pyqtSignal(str)  # game_name
    game_completed = pyqtSignal(str, int)  # game_name, dlcs_installed
    dlc_installed = pyqtSignal(str, str)  # game_name, dlc_file
    batch_complete = pyqtSignal(int, int)  # total_games_processed, total_dlcs_installed
    error_occurred = pyqtSignal(str)  # error_message

    def __init__(self, parent=None):
        super().__init__()
        self.games_to_process = []
        self.current_mode = "usb"
        self.settings_manager = SettingsManager()
        self.dlc_utils = DLCUtils(parent)
        self.game_manager = GameManager()
        self.directory_manager = parent.directory_manager if parent else None
        self.should_stop = False
        self.log_file_path = None

    def setup_batch(self, games: List[Dict[str, Any]], mode: str):
        """Setup the batch processing with games list and mode"""
        self.games_to_process = games
        self.current_mode = mode
        self.should_stop = False

        # Create log file for debugging
        self.log_file_path = "batch_dlc_install_log.txt"
        with open(self.log_file_path, "w") as f:
            f.write("Batch DLC Install Log\n")
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
        total_dlcs_installed = 0

        try:
            for i, game in enumerate(self.games_to_process):
                if self.should_stop:
                    break

                game_name = game.get("name", "Unknown")
                title_id = game.get("title_id", "")

                self.game_started.emit(game_name)
                self.progress_update.emit(i + 1, total_games)
                self._log_message("")
                self._log_message(
                    f"Processing game: {game_name} (Title ID: {title_id})"
                )

                try:
                    # Get all DLCs for this game
                    dlc_list = self.dlc_utils.get_dlcs_for_title(title_id)
                    if not dlc_list:
                        self._log_message(f"  No DLCs found for {game_name}")
                        self.game_completed.emit(game_name, 0)
                        continue

                    dlcs_installed = 0
                    for dlc in dlc_list:
                        if self.should_stop:
                            break
                        title_id = dlc.get("title_id", "")
                        filename = dlc.get("file", "")

                        local_dlc_path = f"{self.directory_manager.dlc_directory}/{title_id}/{filename}"

                        if not filename:
                            continue
                        # Install the DLC
                        if self.current_mode == "ftp":
                            success, message = self.dlc_utils._install_dlc_ftp(
                                local_dlc_path, title_id, filename
                            )
                        else:
                            success, message = self.dlc_utils._install_dlc_usb(
                                local_dlc_path, title_id, filename
                            )
                        if success:
                            self._log_message(f"  Installed DLC: {filename}")
                            self.dlc_installed.emit(game_name, filename)
                            dlcs_installed += 1
                        elif message == "DLC file already exists":
                            self._log_message(f"  DLC already exists: {filename}")
                        else:
                            self._log_message(
                                f"  Failed to install DLC: {filename} - {message}"
                            )
                    self.game_completed.emit(game_name, dlcs_installed)
                    total_dlcs_installed += dlcs_installed
                except Exception as e:
                    self._log_message(f"  Error processing {game_name}: {str(e)}")
                    self.game_completed.emit(game_name, 0)
        except Exception as e:
            self.error_occurred.emit(f"Batch processing error: {str(e)}")
            return

        self._log_message(
            f"\nBatch processing complete. Total DLCs installed: {total_dlcs_installed}"
        )
        self.batch_complete.emit(total_games, total_dlcs_installed)

    def _install_dlc(self, title_id: str, dlc_file: str) -> bool:
        """Install the DLC file for the given game (simulate or call actual logic)"""
        try:
            return self.dlc_utils.install_dlc(title_id, dlc_file)
        except Exception:
            return False

    def _log_message(self, message: str):
        """Log a message to the debug file"""
        try:
            if self.log_file_path:
                with open(self.log_file_path, "a") as f:
                    f.write(f"{message}\n")
        except Exception:
            pass  # Ignore logging errors
