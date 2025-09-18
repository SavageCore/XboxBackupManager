#!/usr/bin/env python3
"""
Game Manager - Handles game scanning, filtering, and selection operations
"""

from pathlib import Path
from typing import List, Optional

from PyQt6.QtCore import QObject, pyqtSignal

from models.game_info import GameInfo
from workers.directory_scanner import DirectoryScanner


class GameManager(QObject):
    """Manages game operations: scanning, filtering, selection"""

    # Signals for UI updates
    scan_started = pyqtSignal()
    scan_progress = pyqtSignal(int, int)  # current, total
    scan_complete = pyqtSignal(list)  # List[GameInfo]
    scan_error = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.current_scanner = None
        self.games: List[GameInfo] = []
        self.is_scanning = False

    def start_scan(
        self,
        directory: str,
        platform: str,
    ):
        """Start scanning directory for games"""
        if self.is_scanning:
            return False

        self.is_scanning = True

        self.current_scanner = DirectoryScanner(directory, platform)

        # Connect scanner signals
        self.current_scanner.progress.connect(self.scan_progress.emit)
        self.current_scanner.game_found.connect(self._on_game_found)
        self.current_scanner.finished.connect(self._on_scan_complete)
        self.current_scanner.error.connect(self._on_scan_error)

        self.current_scanner.start()
        self.scan_started.emit()

        return True

    def _on_game_found(self, game: GameInfo):
        """Handle a game found during scanning"""
        # Check if game already exists (by title_id) before adding
        existing_game = self.find_game_by_title_id(game.title_id)
        if not existing_game:
            self.games.append(game)

    def _on_scan_complete(self):
        """Handle scan completion"""
        self.is_scanning = False
        self.current_scanner = None
        self.scan_complete.emit(self.games)

    def _on_scan_error(self, error_message: str):
        """Handle scan error"""
        self.is_scanning = False
        self.current_scanner = None
        self.scan_error.emit(error_message)

    def get_games(self) -> List[GameInfo]:
        """Get current list of games"""
        return self.games.copy()

    def get_selected_games(self, selected_title_ids: List[str]) -> List[GameInfo]:
        """Get games matching the selected title IDs"""
        selected_games = []
        for title_id in selected_title_ids:
            for game in self.games:
                if game.title_id == title_id:
                    selected_games.append(game)
                    break
        return selected_games

    def find_game_by_title_id(self, title_id: str) -> Optional[GameInfo]:
        """Find a game by its title ID"""
        for game in self.games:
            if game.title_id == title_id:
                return game
        return None

    def get_games_count(self) -> int:
        """Get total number of games"""
        return len(self.games)

    def get_total_size(self) -> int:
        """Get total size of all games in bytes"""
        return sum(game.size_bytes for game in self.games)

    def filter_games(self, filter_text: str) -> List[GameInfo]:
        """Filter games by name or title ID"""
        if not filter_text:
            return self.games.copy()

        filter_text = filter_text.lower()
        filtered_games = []

        for game in self.games:
            if filter_text in game.name.lower() or filter_text in game.title_id.lower():
                filtered_games.append(game)

        return filtered_games

    def mark_game_transferred(self, title_id: str):
        """Mark a game as transferred"""
        game = self.find_game_by_title_id(title_id)
        if game:
            game.transferred = True

    def update_transferred_states(self, target_directory: str):
        """Update the transferred state for all games"""
        if not target_directory or not Path(target_directory).exists():
            return

        for game in self.games:
            game.transferred = self._check_if_transferred(game, target_directory)

    def _check_if_transferred(self, game: GameInfo, target_directory: str) -> bool:
        """Check if a game has been transferred to target directory"""
        target_path_by_name = Path(target_directory) / game.name
        target_path_by_id = Path(target_directory) / game.title_id

        return (target_path_by_name.exists() and target_path_by_name.is_dir()) or (
            target_path_by_id.exists() and target_path_by_id.is_dir()
        )

    def clear_games(self):
        """Clear all games"""
        self.games = []

    def refresh_scan(self, directory: str, platform: str):
        """Clear existing games and start fresh scan"""
        self.clear_games()
        return self.start_scan(directory, platform)

    def get_icon_path(self, title_id: str) -> Optional[str]:
        """Get the icon path for a game by title ID"""
        icon_path = Path("cache/icons") / f"{title_id}.png"
        if icon_path.exists():
            return str(icon_path)
        return None
