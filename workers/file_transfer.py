import shutil
import os
from pathlib import Path
from typing import List
import concurrent.futures
from concurrent.futures import ThreadPoolExecutor
import threading

from PyQt6.QtCore import QThread, pyqtSignal

from models.game_info import GameInfo


class FileTransferWorker(QThread):
    """Optimized worker thread for transferring game files"""

    progress = pyqtSignal(int, int, str)  # current, total, current_game
    game_transferred = pyqtSignal(str)  # title_id
    transfer_complete = pyqtSignal()
    transfer_error = pyqtSignal(str)  # error_message

    def __init__(
        self,
        games_to_transfer: List[GameInfo],
        target_directory: str,
        max_workers: int = 4,
        buffer_size: int = 1024 * 1024,
    ):
        super().__init__()
        self._games_to_transfer = games_to_transfer
        self._target_directory = target_directory
        self._max_workers = max_workers
        self._buffer_size = buffer_size
        self._lock = threading.Lock()
        self._completed_games = 0

    def _copy_file_optimized(self, src: Path, dst: Path) -> None:
        """Optimized file copying with larger buffer"""
        dst.parent.mkdir(parents=True, exist_ok=True)

        # Use larger buffer for better performance
        with open(src, "rb") as fsrc, open(dst, "wb") as fdst:
            while chunk := fsrc.read(self._buffer_size):
                fdst.write(chunk)

        # Preserve metadata
        shutil.copystat(str(src), str(dst))

    def _copy_directory_parallel(
        self, source_path: Path, target_path: Path, game_name: str
    ) -> None:
        """Copy directory using parallel file copying"""
        if target_path.exists():
            return

        # Create target directory structure first
        target_path.mkdir(parents=True, exist_ok=True)

        # Collect all files to copy
        files_to_copy = []
        for root, dirs, files in os.walk(source_path):
            root_path = Path(root)
            rel_path = root_path.relative_to(source_path)
            target_dir = target_path / rel_path

            # Create directories
            target_dir.mkdir(parents=True, exist_ok=True)

            # Add files to copy list
            for file in files:
                src_file = root_path / file
                dst_file = target_dir / file
                files_to_copy.append((src_file, dst_file))

        # Copy files in parallel (but limit workers for disk I/O)
        file_workers = min(self._max_workers, 2)  # Limit for disk I/O
        with ThreadPoolExecutor(max_workers=file_workers) as executor:
            futures = [
                executor.submit(self._copy_file_optimized, src, dst)
                for src, dst in files_to_copy
            ]

            # Wait for all files to complete
            concurrent.futures.wait(futures)

            # Check for errors
            for future in futures:
                if future.exception():
                    raise future.exception()

    def _copy_directory_fast(self, source_path: Path, target_path: Path) -> None:
        """Fastest copy method - uses system calls when possible"""
        if target_path.exists():
            return

        try:
            # On Windows, try to use robocopy for maximum speed
            if os.name == "nt":
                import subprocess

                cmd = [
                    "robocopy",
                    str(source_path),
                    str(target_path),
                    "/E",  # Copy subdirectories including empty ones
                    "/MT:8",  # Multi-threaded (8 threads)
                    "/R:0",  # No retries on failed copies
                    "/W:0",  # No wait time between retries
                    "/NFL",  # No file list (reduces output)
                    "/NDL",  # No directory list
                    "/NJH",  # No job header
                    "/NJS",  # No job summary
                ]

                result = subprocess.run(cmd, capture_output=True, text=True)
                # Robocopy return codes: 0-7 are success, 8+ are errors
                if result.returncode >= 8:
                    raise Exception(f"Robocopy failed: {result.stderr}")
                return
        except (ImportError, FileNotFoundError, Exception):
            pass

        # Fallback to parallel copying
        self._copy_directory_parallel(source_path, target_path, "")

    def run(self):
        """Run the optimized transfer process"""
        try:
            total_games = len(self._games_to_transfer)

            # Option 1: Copy games sequentially but with optimized per-game copying
            for i, game in enumerate(self._games_to_transfer):
                current_game = f"{game.name} ({game.title_id})"
                self.progress.emit(i, total_games, current_game)

                source_path = Path(game.folder_path)
                target_path = Path(self._target_directory) / source_path.name

                if target_path.exists():
                    continue

                # Use the fastest copy method
                self._copy_directory_fast(source_path, target_path)

                self.game_transferred.emit(game.title_id)

            self.transfer_complete.emit()

        except Exception as e:
            self.transfer_error.emit(str(e))


class ParallelFileTransferWorker(QThread):
    """Alternative: Copy multiple games in parallel (use with caution on HDDs)"""

    progress = pyqtSignal(int, int, str)
    game_transferred = pyqtSignal(str)
    transfer_complete = pyqtSignal()
    transfer_error = pyqtSignal(str)

    def __init__(
        self,
        games_to_transfer: List[GameInfo],
        target_directory: str,
        max_concurrent_games: int = 2,
    ):
        super().__init__()
        self._games_to_transfer = games_to_transfer
        self._target_directory = target_directory
        self._max_concurrent_games = max_concurrent_games
        self._lock = threading.Lock()
        self._completed_games = 0

    def _copy_single_game(self, game: GameInfo) -> None:
        """Copy a single game"""
        source_path = Path(game.folder_path)
        target_path = Path(self._target_directory) / source_path.name

        if target_path.exists():
            with self._lock:
                self._completed_games += 1
            return

        # Use robocopy on Windows for best performance
        if os.name == "nt":
            import subprocess

            cmd = [
                "robocopy",
                str(source_path),
                str(target_path),
                "/E",
                "/MT:4",
                "/R:0",
                "/W:0",
                "/NFL",
                "/NDL",
                "/NJH",
                "/NJS",
            ]
            result = subprocess.run(cmd, capture_output=True)
            if result.returncode >= 8:
                raise Exception(f"Failed to copy {game.name}")
        else:
            # Fallback to shutil
            shutil.copytree(str(source_path), str(target_path))

        with self._lock:
            self._completed_games += 1
            self.game_transferred.emit(game.title_id)

    def run(self):
        """Run parallel game transfers"""
        try:
            total_games = len(self._games_to_transfer)

            with ThreadPoolExecutor(max_workers=self._max_concurrent_games) as executor:
                futures = [
                    executor.submit(self._copy_single_game, game)
                    for game in self._games_to_transfer
                ]

                # Monitor progress
                while self._completed_games < total_games:
                    self.progress.emit(
                        self._completed_games,
                        total_games,
                        f"Copying {self._max_concurrent_games} games in parallel...",
                    )
                    self.msleep(500)  # Update every 500ms

                # Wait for completion and check for errors
                for future in concurrent.futures.as_completed(futures):
                    if future.exception():
                        raise future.exception()

            self.transfer_complete.emit()

        except Exception as e:
            self.transfer_error.emit(str(e))
