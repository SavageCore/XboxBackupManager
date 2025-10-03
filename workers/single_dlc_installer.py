"""
Worker for installing a single DLC in the background
"""

from PyQt6.QtCore import QThread, pyqtSignal


class SingleDLCInstaller(QThread):
    """Worker thread for installing a single DLC without blocking the UI"""

    # Signals
    progress = pyqtSignal(int, int)  # current_bytes, total_bytes
    finished = pyqtSignal(bool, str)  # success, error_message

    def __init__(
        self,
        dlc_utils,
        local_dlc_path: str,
        title_id: str,
        filename: str,
        mode: str,
        parent=None,
    ):
        super().__init__(parent)
        self.dlc_utils = dlc_utils
        self.local_dlc_path = local_dlc_path
        self.title_id = title_id
        self.filename = filename
        self.mode = mode
        self._should_stop = False

    def stop(self):
        """Request the worker to stop"""
        self._should_stop = True

    def run(self):
        """Install the DLC in background thread"""
        try:
            if self._should_stop:
                self.finished.emit(False, "Cancelled")
                return

            # Create progress callback that emits signals with bytes transferred
            def progress_callback(current_bytes, total_bytes):
                if not self._should_stop:
                    self.progress.emit(current_bytes, total_bytes)

            # Install DLC
            if self.mode == "ftp":
                success, message = self.dlc_utils._install_dlc_ftp(
                    self.local_dlc_path,
                    self.title_id,
                    self.filename,
                    progress_callback=progress_callback,
                )
            else:
                success, message = self.dlc_utils._install_dlc_usb(
                    self.local_dlc_path,
                    self.title_id,
                    self.filename,
                    progress_callback=progress_callback,
                )

            if not self._should_stop:
                self.finished.emit(success, message or "")

        except Exception as e:
            if not self._should_stop:
                self.finished.emit(False, str(e))
