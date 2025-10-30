#!/usr/bin/env python3
"""
Transfer Manager - Handles all game transfer operations
"""

from pathlib import Path
from typing import List

from PyQt6.QtCore import QObject, pyqtSignal

from models.game_info import GameInfo
from utils.ui_utils import UIUtils
from workers.file_transfer import FileTransferWorker
from workers.ftp_transfer import FTPTransferWorker


class TransferManager(QObject):
    """Manages game transfers for both USB and FTP modes"""

    # Signals for UI updates
    transfer_started = pyqtSignal()
    transfer_progress = pyqtSignal(int, int, str)  # current, total, game_name
    file_progress = pyqtSignal(str, int)  # game_name, percentage
    transfer_speed = pyqtSignal(str, float)  # game_name, speed_bps
    current_file = pyqtSignal(str, str)  # game_name, filename
    game_transferred = pyqtSignal(str)  # title_id
    transfer_complete = pyqtSignal()
    transfer_error = pyqtSignal(str)
    transfer_cancelled = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.current_worker = None
        self.is_transferring = False

    def start_transfer(
        self,
        games_to_transfer: List[GameInfo],
        target_directory: str,
        current_mode: str,
        current_platform: str,
        ftp_settings: dict = None,
    ):
        """Start transferring games"""
        if self.is_transferring:
            return False

        self.is_transferring = True

        if current_mode == "ftp":
            self.current_worker = FTPTransferWorker(
                games_to_transfer,
                ftp_settings["host"],
                ftp_settings["username"],
                ftp_settings["password"],
                target_directory,
                ftp_settings.get("port", 21),
                current_platform=current_platform,
            )
        else:
            self.current_worker = FileTransferWorker(
                games_to_transfer, target_directory, current_platform=current_platform
            )

        # Connect worker signals
        self._connect_worker_signals()

        # Start the worker
        self.current_worker.start()
        self.transfer_started.emit()

        return True

    def cancel_transfer(self):
        """Cancel the current transfer"""
        if self.current_worker and self.is_transferring:
            self.current_worker.stop()
            self.current_worker.wait()
            self.is_transferring = False
            self.transfer_cancelled.emit()

    def _connect_worker_signals(self):
        """Connect worker signals to manager signals"""
        if not self.current_worker:
            return

        self.current_worker.progress.connect(self.transfer_progress.emit)
        self.current_worker.file_progress.connect(self.file_progress.emit)
        self.current_worker.game_transferred.connect(self.game_transferred.emit)
        self.current_worker.transfer_complete.connect(self._on_transfer_complete)
        self.current_worker.transfer_error.connect(self.transfer_error.emit)

        # Connect transfer speed and current file signals if available
        if hasattr(self.current_worker, "transfer_speed"):
            self.current_worker.transfer_speed.connect(self.transfer_speed.emit)
        if hasattr(self.current_worker, "current_file"):
            self.current_worker.current_file.connect(self.current_file.emit)

    def _on_transfer_complete(self):
        """Handle transfer completion"""
        self.is_transferring = False
        self.current_worker = None
        self.transfer_complete.emit()

    def get_available_disk_space(self, path: str) -> int:
        """Get available disk space for a path"""
        try:
            if Path(path).exists():
                stat = Path(path).stat()
                return (
                    stat.st_size
                )  # This is simplified - would need actual disk space logic
            return 0
        except Exception:
            return 0

    def validate_transfer_requirements(
        self, games_to_transfer: List[GameInfo], target_directory: str
    ) -> tuple[bool, str]:
        """
        Validate that transfer can proceed

        Returns:
            tuple: (is_valid, error_message)
        """
        if not games_to_transfer:
            return False, "No games selected for transfer"

        if not UIUtils.validate_directory_exists(target_directory):
            return False, f"Target directory does not exist: {target_directory}"

        # Calculate total size
        total_size = sum(game.size_bytes for game in games_to_transfer)
        available_space = self.get_available_disk_space(target_directory)

        if total_size > available_space:
            return (
                False,
                f"Insufficient disk space. Need {UIUtils.format_file_size(total_size)}, have {UIUtils.format_file_size(available_space)}",
            )

        return True, ""
