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
                self.ftp_host,
                self.ftp_username,
                self.ftp_password,
                self.ftp_port,
                self.ftp_use_tls,
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
        ftp_client.create_directory(target_ftp_path)

        # Calculate total size for progress
        total_size = 0
        file_list = []

        for file_path in source_path.rglob("*"):
            if file_path.is_file():
                file_list.append(file_path)
                total_size += file_path.stat().st_size

        if not file_list:
            return

        # Upload files
        uploaded_size = 0

        for file_path in file_list:
            if self.should_stop:
                break

            # Calculate relative path for FTP
            rel_path = file_path.relative_to(source_path)
            ftp_file_path = f"{target_ftp_path}/{str(rel_path).replace(os.sep, '/')}"

            # Create parent directories on FTP server
            ftp_dir = "/".join(ftp_file_path.split("/")[:-1])
            ftp_client.create_directory(ftp_dir)

            # Upload file
            file_path.stat().st_size

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
