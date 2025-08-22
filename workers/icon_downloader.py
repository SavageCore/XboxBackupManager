import urllib.error
import urllib.request
from pathlib import Path
from typing import List

from PyQt6.QtCore import QThread, pyqtSignal
from PyQt6.QtGui import QPixmap


class IconDownloader(QThread):
    """Thread to download game icons"""

    icon_downloaded = pyqtSignal(str, QPixmap)  # title_id, pixmap
    download_failed = pyqtSignal(str)  # title_id

    def __init__(self, title_ids: List[str], platform: str = "xbox360"):
        super().__init__()
        self.title_ids = title_ids
        self.platform = platform
        self.cache_dir = Path("cache/icons")
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def run(self):
        for title_id in self.title_ids:
            try:
                pixmap = self._get_or_download_icon(title_id)
                if pixmap:
                    self.icon_downloaded.emit(title_id, pixmap)
                else:
                    self.download_failed.emit(title_id)
            except Exception:
                self.download_failed.emit(title_id)

    def _get_or_download_icon(self, title_id: str) -> QPixmap:
        """Get icon from cache or download it"""
        cache_file = self.cache_dir / f"{title_id}.png"

        # Check if cached version exists
        if cache_file.exists():
            pixmap = QPixmap(str(cache_file))
            if not pixmap.isNull():
                return pixmap

        # Download from Xbox Unity or MobCat
        try:
            if self.platform == "xbox360":
                # url = f"https://xboxunity.net/Resources/Lib/Icon.php?tid={title_id}&custom=1"
                url = f"https://raw.githubusercontent.com/UncreativeXenon/XboxUnity-Scraper/refs/heads/master/Icons/{title_id}.png"
            else:
                url = f"https://raw.githubusercontent.com/MobCat/MobCats-original-xbox-game-list/main/icon/{title_id[:4]}/{title_id}.png"
            urllib.request.urlretrieve(url, str(cache_file))

            pixmap = QPixmap(str(cache_file))
            if not pixmap.isNull():
                return pixmap
        except (urllib.error.URLError, urllib.error.HTTPError, Exception):
            pass

        return QPixmap()  # Return empty pixmap on failure
