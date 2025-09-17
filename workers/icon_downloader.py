import base64
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import List

from PyQt6.QtCore import QThread, pyqtSignal
from PyQt6.QtGui import QPixmap

from utils.system_utils import SystemUtils
from utils.xboxunity import XboxUnity


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
        self.xbox_unity = XboxUnity()

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

        # Check if this is an extracted ISO game (default.xex), GoD game, or Xbox game (default.xbe)
        if self.current_directory and self.current_directory.exists():
            # Look for the game in the current directory
            game_dir = self.current_directory / folder_name
            xex_path = game_dir / "default.xex"
            if self.platform == "xbox360":
                god_header_path = game_dir / "00007000"
            elif self.platform == "xbla":
                god_header_path = game_dir / "000D0000"
            xbe_path = game_dir / "default.xbe"

            # Try XEX extraction first (Xbox 360 extracted ISO games)
            if self.platform == "xbox360" and xex_path.exists():
                icon_pixmap = self._extract_icon_from_xex(xex_path, title_id)
                if not icon_pixmap.isNull():
                    return icon_pixmap

            # Try GoD extraction (Xbox 360 Games on Demand)
            elif (
                self.platform in ["xbox360", "xbla"]
                and god_header_path.exists()
                and god_header_path.is_dir()
            ):
                icon_pixmap = self._extract_icon_from_god(god_header_path, title_id)
                if not icon_pixmap.isNull():
                    return icon_pixmap

            # Try XBE extraction (Original Xbox games)
            elif self.platform == "xbox" and xbe_path.exists():
                icon_pixmap = self._extract_icon_from_xbe(xbe_path, title_id)
                if not icon_pixmap.isNull():
                    return icon_pixmap

        # Download from Xbox Unity or MobCat
        try:
            if self.platform in ["xbox360", "xbla"]:
                # url = f"https://xboxunity.net/Resources/Lib/Icon.php?tid={title_id}&custom=1"
                url = f"https://raw.githubusercontent.com/UncreativeXenon/XboxUnity-Scraper/refs/heads/master/Icons/{title_id}.png"
            else:
                url = f"https://raw.githubusercontent.com/MobCat/MobCats-original-xbox-game-list/main/icon/{title_id[:4]}/{title_id}.png"

            if not url:
                return QPixmap()  # No URL available for this platform

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

    def _extract_icon_from_god(
        self, god_header_path: Path, expected_title_id: str
    ) -> QPixmap:
        """Extract icon from GoD file using XboxUnity"""
        try:
            # Find the first header file in the 00007000 directory
            header_files = list(god_header_path.glob("*"))
            if not header_files:
                return QPixmap()

            # Use the first header file found
            header_file_path = str(header_files[0])

            # Extract GoD information including icon
            god_info = self.xbox_unity.get_god_info(header_file_path)
            if not god_info:
                return QPixmap()

            # Verify this GoD file belongs to the title we're looking for
            extracted_title_id = god_info.get("title_id")
            if extracted_title_id and extracted_title_id != expected_title_id:
                # Title ID doesn't match, but still try to use the icon
                # (in case the folder was renamed)
                pass

            # Get the icon data
            icon_base64 = god_info.get("icon_base64")
            if not icon_base64:
                return QPixmap()

            # Decode base64 and create pixmap
            icon_data = base64.b64decode(icon_base64)
            pixmap = QPixmap()
            pixmap.loadFromData(icon_data)

            # Cache the icon for future use (use the expected title ID for consistent caching)
            if not pixmap.isNull():
                cache_file = self.cache_dir / f"{expected_title_id}.png"
                pixmap.save(str(cache_file), "PNG")

            return pixmap

        except Exception:
            return QPixmap()

    def _extract_icon_from_xbe(self, xbe_path: Path, expected_title_id: str) -> QPixmap:
        """Extract icon from XBE file using pyxbe CLI tool"""
        try:
            # Use pyxbe command line tool to extract images directly in the game directory
            game_dir = xbe_path.parent

            # Check if we're running from a PyInstaller bundle
            if getattr(sys, "frozen", False):
                # Running in a PyInstaller bundle - pyxbe won't be available
                print("Running from PyInstaller bundle - pyxbe CLI not available")
                return QPixmap()

            subprocess.run(
                [sys.executable, "-m", "xbe", "--extract-images", str(xbe_path)],
                cwd=str(game_dir),
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                text=True,
            )
            # Check for extracted BMP files regardless of return code
            # (pyxbe might fail but still create the files)
            title_image_path = game_dir / "default_title_image.bmp"
            if title_image_path.exists():
                # Load the title image
                pixmap = QPixmap()
                if pixmap.load(str(title_image_path)):
                    # Cache the icon for future use
                    if not pixmap.isNull():
                        cache_file = self.cache_dir / f"{expected_title_id}.png"
                        pixmap.save(str(cache_file), "PNG")

                    # Clean up the extracted BMP files
                    try:
                        if title_image_path.exists():
                            title_image_path.unlink()

                        save_image_path = game_dir / "default_save_image.bmp"
                        if save_image_path.exists():
                            save_image_path.unlink()
                    except Exception as cleanup_error:
                        print(f"Warning: Failed to clean up BMP files: {cleanup_error}")

                    return pixmap
                else:
                    print(f"Failed to load title image: {title_image_path}")
                    # Clean up even if loading failed
                    try:
                        if title_image_path.exists():
                            title_image_path.unlink()
                    except Exception:
                        pass
            else:
                # Fallback: look for any BMP files if default_title_image.bmp doesn't exist
                bmp_files = list(game_dir.glob("*.bmp"))
                if bmp_files:
                    print(
                        f"default_title_image.bmp not found, trying first available: {bmp_files}"
                    )
                    pixmap = QPixmap()
                    if pixmap.load(str(bmp_files[0])):
                        print(f"Successfully loaded BMP icon from: {bmp_files[0]}")

                        # Cache the icon for future use
                        if not pixmap.isNull():
                            cache_file = self.cache_dir / f"{expected_title_id}.png"
                            pixmap.save(str(cache_file), "PNG")
                            print(f"Cached XBE icon as PNG: {cache_file}")

                        # Clean up all BMP files
                        for bmp_file in bmp_files:
                            try:
                                bmp_file.unlink()
                                print(f"Cleaned up: {bmp_file}")
                            except Exception:
                                pass

                        return pixmap
                    else:
                        print(f"Failed to load BMP file: {bmp_files[0]}")
                        # Clean up even if loading failed
                        for bmp_file in bmp_files:
                            try:
                                bmp_file.unlink()
                            except Exception:
                                pass

            # # Show error info if extraction failed
            # if result.returncode != 0:
            #     print(f"pyxbe extraction failed with return code: {result.returncode}")
            #     if result.stderr:
            #         print(f"Error output: {result.stderr}")
            #     if result.stdout:
            #         print(f"Standard output: {result.stdout}")

            # No fallback - either extract via CLI or fail
            return QPixmap()

        except Exception as e:
            print(f"Exception in XBE icon extraction: {e}")
            return QPixmap()
