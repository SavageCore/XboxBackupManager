import os
from pathlib import Path
from typing import Dict, Optional

from PyQt6.QtCore import QThread, pyqtSignal

from models.game_info import GameInfo


class DirectoryScanner(QThread):
    """Thread to scan directory for Xbox games"""

    progress = pyqtSignal(int, int)  # current, total
    game_found = pyqtSignal(GameInfo)
    finished = pyqtSignal()
    error = pyqtSignal(str)

    def __init__(
        self,
        directory: str,
        title_database: Dict[str, str],
        platform: str = "xbox360",
        xbox_database=None,
    ):
        super().__init__()
        self.directory = directory
        self.title_database = title_database  # Xbox 360 database
        self.xbox_database = xbox_database  # Xbox database
        self.platform = platform
        self.should_stop = False

    def run(self):
        """Main scanning logic"""
        try:
            if not os.path.exists(self.directory):
                self.error.emit(f"Directory does not exist: {self.directory}")
                return

            if self.platform == "xbox":
                self._scan_xbox_directory()
            else:
                self._scan_xbox360_directory()

        except Exception as e:
            if not self.should_stop:  # Only emit error if not intentionally stopped
                self.error.emit(f"Scanning error: {str(e)}")

    def _scan_xbox_directory(self):
        """Scan directory for original Xbox games"""
        folders = []

        # Get all subdirectories
        for item in os.listdir(self.directory):
            if self.should_stop:
                return
            item_path = os.path.join(self.directory, item)
            if os.path.isdir(item_path):
                folders.append(item_path)

        total_folders = len(folders)
        self.progress.emit(0, total_folders)

        for i, folder_path in enumerate(folders):
            if self.should_stop:
                return

            # Look for default.xbe file
            xbe_path = os.path.join(folder_path, "default.xbe")
            if os.path.exists(xbe_path):
                game_info = self._process_xbox_game(folder_path, xbe_path)
                if game_info and not self.should_stop:
                    self.game_found.emit(game_info)

            if not self.should_stop:
                self.progress.emit(i + 1, total_folders)

        if not self.should_stop:
            self.finished.emit()

    def _process_xbox_game(self, folder_path: str, xbe_path: str) -> Optional[GameInfo]:
        """Process an Xbox game folder"""
        try:
            # Get title info from XBE MD5
            if hasattr(self, "xbox_database") and self.xbox_database:
                title_info = self.xbox_database.get_full_title_info_by_xbe_path(
                    xbe_path
                )

                if title_info:
                    title_id = title_info["title_id"]
                    name = title_info["name"]
                else:
                    # Fallback: use folder name as title ID and name
                    folder_name = os.path.basename(folder_path)
                    title_id = folder_name
                    name = f"Unknown Xbox Game ({folder_name})"
            else:
                # No database available - use folder name
                folder_name = os.path.basename(folder_path)
                title_id = folder_name
                name = f"Xbox Game ({folder_name})"

            # Calculate folder size
            size_bytes = self._calculate_directory_size(folder_path)

            # Create GameInfo object
            game_info = GameInfo(
                title_id=title_id,
                name=name,
                folder_path=folder_path,
                size_bytes=size_bytes,
            )

            return game_info

        except Exception as e:
            print(f"Error processing Xbox game {folder_path}: {e}")
            return None

    def _process_xbox360_game(
        self, folder_path: str, title_id: str
    ) -> Optional[GameInfo]:
        """Process an Xbox 360/XBLA game folder"""
        try:
            # Get title name from database
            name = self.title_database.get(title_id, f"Unknown XBLA Game ({title_id})")

            # Calculate folder size
            size_bytes = self._calculate_directory_size(folder_path)

            # Create GameInfo object
            game_info = GameInfo(
                title_id=title_id,
                name=name,
                folder_path=folder_path,
                size_bytes=size_bytes,
            )

            return game_info

        except Exception as e:
            print(f"Error processing Xbox 360 game {folder_path}: {e}")
            return None

    def _scan_xbox360_directory(self):
        """Scan directory for Xbox 360/XBLA games (existing logic)"""
        folders = []

        # Get all subdirectories that look like title IDs
        for item in os.listdir(self.directory):
            if self.should_stop:
                return
            item_path = os.path.join(self.directory, item)
            if os.path.isdir(item_path):
                # For Xbox 360/XBLA, we expect 8-character hex title IDs
                if len(item) == 8 and all(c in "0123456789ABCDEFabcdef" for c in item):
                    folders.append((item_path, item.upper()))

        total_folders = len(folders)
        self.progress.emit(0, total_folders)

        for i, (folder_path, title_id) in enumerate(folders):
            if self.should_stop:
                return

            game_info = self._process_xbox360_game(folder_path, title_id)
            if game_info and not self.should_stop:
                self.game_found.emit(game_info)

            if not self.should_stop:
                self.progress.emit(i + 1, total_folders)

        if not self.should_stop:
            self.finished.emit()

    def _calculate_directory_size(self, directory: Path) -> int:
        """Calculate total size of directory in bytes"""
        total_size = 0
        for dirpath, _, filenames in os.walk(directory):
            for filename in filenames:
                file_path = Path(dirpath) / filename
                if file_path.is_file():
                    total_size += file_path.stat().st_size
        return total_size

    def _format_size(self, size_bytes: int) -> str:
        """Format size in bytes to a human-readable string"""
        for unit in ["B", "KB", "MB", "GB"]:
            if size_bytes < 1024:
                return f"{size_bytes:.2f} {unit}"
            size_bytes /= 1024
        return f"{size_bytes:.2f} TB"
