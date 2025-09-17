from pathlib import Path

from PyQt6.QtCore import QThread, pyqtSignal


class FileTransferWorker(QThread):
    progress = pyqtSignal(int, int, str)  # current_game, total_games, game_name
    file_progress = pyqtSignal(str, int)  # game_name, percentage
    game_transferred = pyqtSignal(str)  # title_id
    transfer_complete = pyqtSignal()
    transfer_error = pyqtSignal(str)

    def __init__(
        self,
        games_to_transfer,
        target_directory,
        max_workers=2,
        buffer_size=2 * 1024 * 1024,
        current_platform=None,
    ):
        super().__init__()
        self.games_to_transfer = games_to_transfer
        self.target_directory = target_directory
        self.max_workers = max_workers
        self.buffer_size = buffer_size
        self.current_game_index = 0
        self.current_platform = current_platform

    def run(self):
        try:
            total_games = len(self.games_to_transfer)

            for i, game in enumerate(self.games_to_transfer):
                self.current_game_index = i
                self.progress.emit(i, total_games, game.name)

                # Transfer the game with per-file progress
                self._transfer_game_with_progress(game)

                self.game_transferred.emit(game.title_id)

            self.transfer_complete.emit()

        except Exception as e:
            self.transfer_error.emit(str(e))

    def _transfer_game_with_progress(self, game):
        """Transfer a single game with file-level progress tracking"""
        source_path = Path(game.folder_path)

        if self.current_platform == "xbla":
            target_path = Path(self.target_directory) / game.title_id
        elif self.current_platform == "xbox360":
            if game.is_extracted_iso:
                target_path = Path(self.target_directory) / game.name
            else:
                target_path = Path(self.target_directory) / game.title_id
        else:  # Xbox
            target_path = Path(self.target_directory) / game.name

        # Calculate total size and file count for this game
        total_files = 0
        total_size = 0

        for file_path in source_path.rglob("*"):
            if file_path.is_file():
                total_files += 1
                total_size += file_path.stat().st_size

        if total_files == 0:
            return

        # Copy files with progress tracking
        copied_size = 0
        copied_files = 0

        target_path.mkdir(parents=True, exist_ok=True)

        for file_path in source_path.rglob("*"):
            if file_path.is_file():
                # Calculate relative path for target
                rel_path = file_path.relative_to(source_path)
                target_file = target_path / rel_path

                # Create parent directories if needed
                target_file.parent.mkdir(parents=True, exist_ok=True)

                # Copy file with buffered reading for large files
                file_size = file_path.stat().st_size
                self._copy_file_with_progress(
                    file_path,
                    target_file,
                    file_size,
                    game.name,
                    copied_size,
                    total_size,
                )

                copied_size += file_size
                copied_files += 1

                # Emit progress based on total size copied
                if total_size > 0:
                    progress_percent = int((copied_size / total_size) * 100)
                    self.file_progress.emit(game.name, progress_percent)

    def _copy_file_with_progress(
        self, source_file, target_file, file_size, game_name, current_copied, total_size
    ):
        """Copy a single file with progress updates"""
        try:
            # Check if file already exists and has the same size
            if target_file.exists():
                existing_size = target_file.stat().st_size

                if existing_size == file_size:
                    return

            with open(source_file, "rb") as src, open(target_file, "wb") as dst:
                copied = 0
                while True:
                    chunk = src.read(self.buffer_size)
                    if not chunk:
                        break

                    dst.write(chunk)
                    copied += len(chunk)

                    # Update progress for large files
                    if file_size > 50 * 1024 * 1024:  # Only for files > 50MB
                        overall_copied = current_copied + copied
                        if total_size > 0:
                            progress_percent = int((overall_copied / total_size) * 100)
                            self.file_progress.emit(game_name, progress_percent)

        except Exception as e:
            raise Exception(f"Failed to copy {source_file}: {str(e)}")
