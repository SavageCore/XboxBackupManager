import os
from PyQt6.QtCore import QThread, pyqtSignal

from utils.xboxunity import XboxUnity


class TitleUpdateDownloadWorker(QThread):
    """Worker thread for downloading title updates in the background"""

    # Signals
    download_progress = pyqtSignal(str, int)  # title_update_name, percentage
    download_complete = pyqtSignal(
        str, bool, str, str
    )  # title_update_name, success, filename, local_path
    download_error = pyqtSignal(str, str)  # title_update_name, error_message

    def __init__(self, parent=None):
        super().__init__(parent)
        self.xbox_unity = XboxUnity()
        self.downloads = []  # List of downloads to process

    def add_download(self, title_update_name: str, url: str, destination: str):
        """Add a download to the queue"""
        self.downloads.append(
            {"name": title_update_name, "url": url, "destination": destination}
        )

    def run(self):
        """Process all downloads in the queue"""
        for download in self.downloads:
            self._download_single_update(download)

        # Clear the queue after processing
        self.downloads.clear()

    def _download_single_update(self, download):
        """Download a single title update"""
        name = download["name"]
        url = download["url"]
        destination = download["destination"]

        try:
            # Download with progress callback
            success, filename = self.xbox_unity.download_title_update(
                url,
                destination,
                progress_callback=lambda downloaded, total: self._progress_callback(
                    name, downloaded, total
                ),
            )

            if success:
                local_path = os.path.join(os.path.dirname(destination), filename)
                self.download_complete.emit(name, True, filename, local_path)
            else:
                self.download_error.emit(name, "Download failed")

        except Exception as e:
            self.download_error.emit(name, str(e))

    def _progress_callback(self, name: str, downloaded: int, total: int):
        """Handle download progress updates"""
        if total > 0:
            percentage = int((downloaded / total) * 100)
            self.download_progress.emit(name, percentage)
