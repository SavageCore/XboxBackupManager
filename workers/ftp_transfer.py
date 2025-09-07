import os
from pathlib import Path

from PyQt6.QtCore import QThread, pyqtSignal

from utils.ftp_client import FTPClient


class FTPTransferWorker(QThread):
    progress = pyqtSignal(int, int, str)  # current_game, total_games, game_name
    file_progress = pyqtSignal(str, int)  # game_name, percentage
    game_transferred = pyqtSignal(str)  # title_id
    transfer_complete = pyqtSignal()
    transfer_error = pyqtSignal(str)

    def __init__(
        self,
        games_to_transfer,
        ftp_host,
        ftp_username,
        ftp_password,
        ftp_target_path,
        ftp_port=21,
        buffer_size=8192,
    ):
        super().__init__()
        self.games_to_transfer = games_to_transfer
        self.ftp_host = ftp_host
        self.ftp_username = ftp_username
        self.ftp_password = ftp_password
        self.ftp_target_path = ftp_target_path
        self.ftp_port = ftp_port
        self.buffer_size = buffer_size
        self.current_game_index = 0
        self.should_stop = False

    def run(self):
        ftp_client = FTPClient()

        try:
            # Connect to FTP server
            success, message = ftp_client.connect(
                self.ftp_host, self.ftp_username, self.ftp_password, self.ftp_port
            )

            if not success:
                self.transfer_error.emit(f"FTP Connection failed: {message}")
                return

            total_games = len(self.games_to_transfer)

            for i, game in enumerate(self.games_to_transfer):
                if self.should_stop:
                    break

                self.current_game_index = i
                self.progress.emit(i, total_games, game.name)

                # Transfer the game
                self._transfer_game_via_ftp(ftp_client, game)

                self.game_transferred.emit(game.title_id)

            if not self.should_stop:
                self.transfer_complete.emit()

        except Exception as e:
            self.transfer_error.emit(str(e))
        finally:
            ftp_client.disconnect()

    def _transfer_game_via_ftp(self, ftp_client: FTPClient, game):
        """Transfer a single game via FTP"""
        source_path = Path(game.folder_path)

        # Create target directory on FTP server
        target_ftp_path = f"{self.ftp_target_path.rstrip('/')}/{source_path.name}"
        success, message = ftp_client.create_directory(target_ftp_path)
        if not success:
            raise Exception(
                f"Failed to create game directory {target_ftp_path}: {message}"
            )

        # Calculate total size for progress (only for files that need to be transferred)
        total_size = 0
        files_to_transfer = []

        for file_path in source_path.rglob("*"):
            if file_path.is_file():
                # Calculate relative path for FTP
                rel_path = file_path.relative_to(source_path)
                ftp_file_path = (
                    f"{target_ftp_path}/{str(rel_path).replace(os.sep, '/')}"
                )

                # Check if file already exists on FTP server
                file_exists = self._check_ftp_file_exists(
                    ftp_client, ftp_file_path, file_path
                )

                if not file_exists:
                    files_to_transfer.append((file_path, ftp_file_path))
                    total_size += file_path.stat().st_size

        if not files_to_transfer:
            # All files already exist, emit 100% progress and return
            self.file_progress.emit(game.name, 100)
            return

        # Keep track of created directories to avoid redundant creation
        created_dirs = set()
        created_dirs.add(target_ftp_path)

        # Upload files that don't exist
        uploaded_size = 0

        for file_path, ftp_file_path in files_to_transfer:
            if self.should_stop:
                break

            # Create parent directories on FTP server if needed
            ftp_dir = "/".join(ftp_file_path.split("/")[:-1])

            # Create all parent directories recursively
            if ftp_dir not in created_dirs:
                self._create_ftp_directories_recursive(
                    ftp_client, ftp_dir, created_dirs
                )

            try:
                with open(file_path, "rb") as local_file:
                    # Use callback for progress tracking
                    uploaded_bytes = 0

                    def upload_callback(data):
                        nonlocal uploaded_bytes, uploaded_size
                        uploaded_bytes += len(data)
                        uploaded_size += len(data)

                        if total_size > 0:
                            progress_percent = int((uploaded_size / total_size) * 100)
                            self.file_progress.emit(game.name, progress_percent)

                    ftp_client._ftp.storbinary(
                        f"STOR {ftp_file_path}", local_file, callback=upload_callback
                    )

            except Exception as e:
                raise Exception(f"Failed to upload {file_path}: {str(e)}")

    def _check_ftp_file_exists(
        self, ftp_client: FTPClient, ftp_file_path: str, local_file_path: Path
    ) -> bool:
        """Check if a file exists on the FTP server and optionally compare size"""
        try:
            # Try to get file size from FTP server
            ftp_client._ftp.voidcmd("TYPE I")  # Set binary mode for size command
            ftp_size = ftp_client._ftp.size(ftp_file_path)

            if ftp_size is not None:
                # Compare with local file size
                local_size = local_file_path.stat().st_size
                return ftp_size == local_size

            return False

        except Exception:
            # If any error occurs (file doesn't exist, size command not supported, etc.)
            # assume file doesn't exist or needs to be re-uploaded
            return False

    def _create_ftp_directories_recursive(
        self, ftp_client: FTPClient, ftp_path: str, created_dirs: set
    ):
        """Create FTP directories recursively"""
        if ftp_path in created_dirs or ftp_path in ["/", ""]:
            return

        # Get parent directory
        parent_dir = "/".join(ftp_path.split("/")[:-1])
        if parent_dir and parent_dir not in created_dirs:
            self._create_ftp_directories_recursive(ftp_client, parent_dir, created_dirs)

        # Create current directory
        success, message = ftp_client.create_directory(ftp_path)
        if success:
            created_dirs.add(ftp_path)
        else:
            # If creation fails but directory exists, that's ok
            if "exists" not in message.lower():
                raise Exception(f"Failed to create directory {ftp_path}: {message}")
            else:
                created_dirs.add(ftp_path)
