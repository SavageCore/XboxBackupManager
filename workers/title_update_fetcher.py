from PyQt6.QtCore import QThread, pyqtSignal

from utils.xboxunity import XboxUnity


class TitleUpdateFetchWorker(QThread):
    """Worker thread for fetching title updates from XboxUnity API in the background"""

    # Signals
    fetch_complete = pyqtSignal(str, list)  # media_id, updates_list
    fetch_error = pyqtSignal(str)  # error_message
    media_id_fetched = pyqtSignal(str)  # media_id
    status_update = pyqtSignal(str)  # status_message

    def __init__(self, folder_path: str, title_id: str, parent=None):
        super().__init__(parent)
        self.folder_path = folder_path
        self.title_id = title_id
        self.xbox_unity = XboxUnity()

    def run(self):
        """Fetch media ID and title updates from XboxUnity API"""
        try:
            # Get media ID (reads from disk)
            self.status_update.emit("Reading game data from disk...")
            media_id = self.xbox_unity.get_media_id(self.folder_path)

            if not media_id:
                self.fetch_error.emit(
                    f"No media ID found for Title ID: {self.title_id}"
                )
                return

            self.media_id_fetched.emit(media_id)

            # Search for title updates (network call)
            self.status_update.emit("Fetching title updates from XboxUnity...")
            updates = self.xbox_unity.search_title_updates(
                media_id=media_id, title_id=self.title_id
            )

            if not updates:
                self.fetch_error.emit(
                    f"No title updates found for Title ID: {self.title_id}"
                )
                return

            # Emit success with updates
            self.fetch_complete.emit(media_id, updates)

        except Exception as e:
            self.fetch_error.emit(f"Error fetching title updates: {str(e)}")
