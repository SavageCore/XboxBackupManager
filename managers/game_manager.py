#!/usr/bin/env python3
"""
Game Manager - Handles game scanning, filtering, and selection operations
"""

import json
from pathlib import Path
from typing import Dict, List, Optional

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
        self.parent = parent

    def start_scan(
        self,
        directory: str,
        platform: str,
        cache_data: Optional[Dict] = None,
    ):
        """Start scanning directory for games"""
        if self.is_scanning:
            return False

        self.is_scanning = True

        self.current_scanner = DirectoryScanner(
            directory, platform, self.parent, cache_data
        )

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

        # Safely clean up the scanner thread
        if self.current_scanner:
            # Disconnect signals to prevent any late emissions
            self.current_scanner.disconnect()
            # Wait for thread to finish properly
            if self.current_scanner.isRunning():
                self.current_scanner.wait(2000)  # Wait up to 2 seconds
            # Clear reference
            self.current_scanner = None

        self.scan_complete.emit(self.games)

    def _on_scan_error(self, error_message: str):
        """Handle scan error"""
        self.is_scanning = False

        # Safely clean up the scanner thread
        if self.current_scanner:
            # Disconnect signals to prevent any late emissions
            self.current_scanner.disconnect()
            # Wait for thread to finish properly
            if self.current_scanner.isRunning():
                self.current_scanner.wait(2000)  # Wait up to 2 seconds
            # Clear reference
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
        print(f"[DEBUG] Searching for game with Title ID: {title_id}")
        for game in self.games:
            if game.title_id == title_id:
                print(f"[DEBUG] Found game: {game.name}")
                return game
        return None

    def get_game_name(self, title_id: str) -> Optional[str]:
        """Get the name of a game by its title ID"""
        print(f"[DEBUG] Looking up game name for Title ID: {title_id}")
        game = self.find_game_by_title_id(title_id)
        if game:
            print(f"[DEBUG] Found game name: {game.name}")
            return game.name
        return None

    def get_games_count(self) -> int:
        """Get total number of games"""
        return len(self.games)

    def get_total_size(self) -> int:
        """Get total size of all games in bytes"""
        return sum(game.size_bytes for game in self.games)

    def increment_dlc_count(self, title_id: str):
        """Increment the DLC count for a game by title ID"""
        game = self.find_game_by_title_id(title_id)
        if game:
            game.dlc_count += 1
            return True
        return False

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

    def stop_scan(self):
        """Stop the current scan safely"""
        if self.is_scanning and self.current_scanner:
            # Set stop flag
            self.current_scanner.should_stop = True

            # Disconnect signals to prevent issues during cleanup
            self.current_scanner.disconnect()

            # Terminate and wait for thread to finish
            self.current_scanner.terminate()
            if not self.current_scanner.wait(3000):  # Wait up to 3 seconds
                # Force quit if still running after 3 seconds
                self.current_scanner.quit()
                self.current_scanner.wait(1000)

            # Clear scanner reference
            self.current_scanner = None

        # Always reset scanning state
        self.is_scanning = False

    def clear_games(self):
        """Clear all games"""
        self.games = []

    def refresh_scan(
        self, directory: str, platform: str, cache_data: Optional[Dict] = None
    ):
        """Clear existing games and start fresh scan"""
        self.clear_games()
        return self.start_scan(directory, platform, cache_data)

    def get_icon_path(self, title_id: str) -> Optional[str]:
        """Get the icon path for a game by title ID"""
        icon_path = Path("cache/icons") / f"{title_id}.png"
        if icon_path.exists():
            return str(icon_path)
        return None

    def get_game_name_from_cache(self, title_id: str, platform: str) -> Optional[str]:
        """Get game name from cache file for a given title ID

        Checks the specified platform's cache first, then checks other platform caches
        as fallback (useful when target directory contains mixed platform games).
        Note: Only XBLA and Xbox 360 support title updates, so only check those caches.
        """
        cache_dir = Path("cache")

        # Build list of cache patterns to check - specified platform first, then others
        # Note: Only XBLA and Xbox 360 support title updates
        cache_patterns = []

        if platform == "xbla":
            cache_patterns = [
                "scan_cache_xbla_*.json",
                "scan_cache_xbox360_*.json",  # Fallback: Xbox 360 games might be in target
            ]
        elif platform == "xbox360":
            cache_patterns = [
                "scan_cache_xbox360_*.json",
                "scan_cache_xbla_*.json",  # Fallback: XBLA games might be in target
            ]
        elif platform == "xbox":
            # Original Xbox doesn't have title updates, but still check XBLA/360 in case
            cache_patterns = [
                "scan_cache_xbox_*.json",
                "scan_cache_xbox360_*.json",
                "scan_cache_xbla_*.json",
            ]
        else:
            return None

        # Try each cache pattern in order
        for cache_pattern in cache_patterns:
            cache_files = list(cache_dir.glob(cache_pattern))
            if not cache_files:
                continue

            # Use the first (and should be only) cache file for this pattern
            cache_file = cache_files[0]

            try:
                with open(cache_file, "r", encoding="utf-8") as f:
                    cache_data = json.load(f)

                # Cache format is a dict with metadata and "games" key containing the list
                if isinstance(cache_data, dict):
                    games_list = cache_data.get("games", [])

                    for game_entry in games_list:
                        entry_title_id = game_entry.get("title_id")
                        if entry_title_id == title_id:
                            name = game_entry.get("name")
                            return name

                elif isinstance(cache_data, list):
                    for game_entry in cache_data:
                        entry_title_id = game_entry.get("title_id")
                        if entry_title_id == title_id:
                            name = game_entry.get("name")
                            return name

            except Exception:
                continue

        return None
