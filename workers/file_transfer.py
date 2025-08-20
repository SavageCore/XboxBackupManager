import shutil
from pathlib import Path
from typing import List

from PyQt6.QtCore import QThread, pyqtSignal

from models.game_info import GameInfo


class FileTransferWorker(QThread):
    """Worker thread for transferring game files"""

    progress = pyqtSignal(int, int, str)  # current, total, current_game
    game_transferred = pyqtSignal(str)  # title_id
    transfer_complete = pyqtSignal()
    transfer_error = pyqtSignal(str)  # error_message

    def __init__(self, games_to_transfer: List[GameInfo], target_directory: str):
        super().__init__()
        self._games_to_transfer = games_to_transfer
        self._target_directory = target_directory

    def run(self):
        """Run the transfer process"""
        try:
            total_games = len(self._games_to_transfer)

            for i, game in enumerate(self._games_to_transfer):
                current_game = f"{game.name} ({game.title_id})"
                self.progress.emit(i, total_games, current_game)

                # Copy game directory
                source_path = Path(game.folder_path)
                target_path = Path(self._target_directory) / source_path.name

                if target_path.exists():
                    # Skip if already exists
                    continue

                # Copy directory tree
                shutil.copytree(str(source_path), str(target_path))

                # Emit game transferred signal
                self.game_transferred.emit(game.title_id)

            self.transfer_complete.emit()

        except Exception as e:
            self.transfer_error.emit(str(e))
