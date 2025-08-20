from pathlib import Path
from typing import Dict

from PyQt6.QtCore import QThread, pyqtSignal

from models.game_info import GameInfo


class DirectoryScanner(QThread):
    """Thread to scan directory for Xbox games"""

    progress = pyqtSignal(int, int)  # current, total
    game_found = pyqtSignal(GameInfo)
    finished = pyqtSignal()
    error = pyqtSignal(str)

    def __init__(self, directory: str, title_database: Dict[str, str]):
        super().__init__()
        self.directory = directory
        self.title_database = title_database

    def run(self):
        try:
            path = Path(self.directory)
            if not path.exists():
                self.error.emit("Directory does not exist")
                return

            # Get all subdirectories (assumed to be Title IDs)
            # Skip Cache
            subdirs = [d for d in path.iterdir() if d.is_dir() and d.name != "Cache"]
            total_dirs = len(subdirs)

            for i, subdir in enumerate(subdirs):
                title_id = subdir.name.upper()
                size = self._calculate_directory_size(subdir)
                game_name = self.title_database.get(title_id, f"Unknown ({title_id})")

                game_info = GameInfo(
                    title_id=title_id,
                    name=game_name,
                    size_bytes=size,
                    folder_path=str(subdir),
                )

                self.game_found.emit(game_info)
                self.progress.emit(i + 1, total_dirs)

            self.finished.emit()

        except Exception as e:
            self.error.emit(str(e))

    def _calculate_directory_size(self, directory: Path) -> int:
        """Calculate total size of directory in bytes"""
        total_size = 0
        try:
            for file_path in directory.rglob("*"):
                if file_path.is_file():
                    total_size += file_path.stat().st_size
        except (OSError, PermissionError):
            pass  # Skip files we can't access
        return total_size
