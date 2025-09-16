import base64
import urllib.error
import urllib.request
from pathlib import Path
from typing import List

from PyQt6.QtCore import QThread, pyqtSignal
from PyQt6.QtGui import QPixmap

from utils.system_utils import SystemUtils


class IconDownloader(QThread):
    """Thread to download game icons"""

    icon_downloaded = pyqtSignal(str, QPixmap)  # title_id, pixmap
    download_failed = pyqtSignal(str)  # title_id

    def __init__(
        self,
        title_ids: List[str],
        platform: str = "xbox360",
        current_directory: str = None,
    ):
        super().__init__()
        self.title_ids = title_ids
        self.platform = platform
        self.current_directory = Path(current_directory) if current_directory else None
        self.cache_dir = Path("cache/icons")
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.system_utils = SystemUtils()

    def run(self):
        for title_id, folder_name in self.title_ids:
            try:
                pixmap = self._get_or_download_icon(title_id, folder_name)
                if pixmap:
                    self.icon_downloaded.emit(title_id, pixmap)
                else:
                    self.download_failed.emit(title_id)
            except Exception:
                self.download_failed.emit(title_id)

    def _get_or_download_icon(self, title_id: str, folder_name: str) -> QPixmap:
        """Get icon from cache or download it"""
        cache_file = self.cache_dir / f"{title_id}.png"

        # Check if cached version exists
        if cache_file.exists():
            pixmap = QPixmap(str(cache_file))
            if not pixmap.isNull():
                return pixmap

        # Check if this is an extracted ISO game (default.xex) and we have a current directory
        if (
            self.platform == "xbox360"
            and self.current_directory
            and self.current_directory.exists()
        ):
            # Look for the game in the current directory
            game_dir = self.current_directory / folder_name
            xex_path = game_dir / "default.xex"

            if xex_path.exists():
                icon_pixmap = self._extract_icon_from_xex(xex_path, title_id)
                if not icon_pixmap.isNull():
                    return icon_pixmap

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

    def _extract_icon_from_xex(self, xex_path: Path, expected_title_id: str) -> QPixmap:
        """Extract icon from XEX file using xextool"""
        try:
            xex_info = self.system_utils.extract_xex_info(str(xex_path))
            if not xex_info:
                return QPixmap()

            # Verify this XEX belongs to the title we're looking for
            extracted_title_id = xex_info.get("title_id")
            if extracted_title_id != expected_title_id:
                return QPixmap()

            # Get the icon data
            icon_base64 = xex_info.get("icon_base64")
            if not icon_base64:
                return QPixmap()

            # Decode base64 and create pixmap
            icon_data = base64.b64decode(icon_base64)
            pixmap = QPixmap()
            pixmap.loadFromData(icon_data)

            # Cache the icon for future use
            if not pixmap.isNull():
                cache_file = self.cache_dir / f"{expected_title_id}.png"
                pixmap.save(str(cache_file), "PNG")

            return pixmap

        except Exception:
            return QPixmap()
