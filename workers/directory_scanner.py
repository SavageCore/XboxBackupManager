import base64
import os
from pathlib import Path
from typing import Optional

from PyQt6.QtCore import QThread, pyqtSignal

from models.game_info import GameInfo
from utils.system_utils import SystemUtils
from utils.xboxunity import XboxUnity
from utils.dlc_utils import DLCUtils


class DirectoryScanner(QThread):
    """Thread to scan directory for Xbox games"""

    progress = pyqtSignal(int, int)  # current, total
    game_found = pyqtSignal(GameInfo)
    finished = pyqtSignal()
    error = pyqtSignal(str)

    def __init__(
        self,
        directory: str,
        platform: str = "xbox360",
    ):
        super().__init__()
        self.directory = directory
        self.platform = platform
        self.should_stop = False
        self.xbox_unity = XboxUnity()
        self.dlc_utils = DLCUtils()

    def run(self):
        """Main scanning logic"""
        try:
            if not os.path.exists(self.directory):
                self.error.emit(f"Directory does not exist: {self.directory}")
                return

            if self.platform == "xbox":
                self._scan_xbox_directory()
            else:
                self._scan_xbox360_directory()

        except Exception as e:
            if not self.should_stop:  # Only emit error if not intentionally stopped
                self.error.emit(f"Scanning error: {str(e)}")

    def _scan_xbox_directory(self):
        """Scan directory for original Xbox games"""
        folders = []

        # Get all subdirectories
        for item in os.listdir(self.directory):
            if self.should_stop:
                return
            item_path = os.path.join(self.directory, item)
            if os.path.isdir(item_path):
                folders.append(item_path)

        total_folders = len(folders)
        self.progress.emit(0, total_folders)

        for i, folder_path in enumerate(folders):
            if self.should_stop:
                return

            # Look for default.xbe file
            xbe_path = os.path.join(folder_path, "default.xbe")
            if os.path.exists(xbe_path):
                game_info = self._process_xbox_game(folder_path, xbe_path)
                if game_info and not self.should_stop:
                    self.game_found.emit(game_info)

            if not self.should_stop:
                self.progress.emit(i + 1, total_folders)

        if not self.should_stop:
            self.finished.emit()

    def _process_xbox_game(self, folder_path: str, xbe_path: str) -> Optional[GameInfo]:
        """Process an Xbox game folder"""
        try:
            # Use pyxbe to extract title information from XBE file
            xbe_info = SystemUtils.extract_xbe_info(xbe_path)

            if xbe_info and xbe_info.get("title_id"):
                title_id = xbe_info["title_id"]
                title_name = xbe_info.get("title_name")
                icon_base64 = xbe_info.get("icon_base64")

                # Use extracted title name, or fall back to folder name
                if title_name:
                    name = title_name
                else:
                    folder_name = os.path.basename(folder_path)
                    name = f"Unknown Game ({folder_name})"
            else:
                # Fallback: use folder name as title ID and name if XBE extraction fails
                folder_name = os.path.basename(folder_path)
                title_id = folder_name
                name = f"Xbox Game ({folder_name})"
                icon_base64 = None

            # Calculate folder size
            size_bytes = self._calculate_directory_size(folder_path)

            # Create GameInfo object
            game_info = GameInfo(
                title_id=title_id,
                name=name,
                folder_path=folder_path,
                size_bytes=size_bytes,
                size_formatted=self._format_size(size_bytes),
                is_extracted_iso=True,  # Xbox games are considered extracted ISOs
            )

            # Cache the icon if we extracted one
            if icon_base64:
                self._cache_xbe_icon(title_id, icon_base64)

            return game_info

        except Exception as e:
            print(f"Error processing Xbox game {folder_path}: {e}")
            return None

    def _process_extracted_iso_game(
        self, folder_path: str, xex_path: str
    ) -> Optional[GameInfo]:
        """Process an extracted ISO Xbox 360 game folder"""
        try:
            # Use xextool to extract title ID and media ID from default.xex
            xex_info = SystemUtils.extract_xex_info(xex_path)

            if xex_info:
                title_id = xex_info["title_id"]
                media_id = xex_info.get("media_id")  # Use .get() to handle None values
                icon_base64 = xex_info.get("icon_base64")  # Extract icon if available
                game_name = xex_info.get("game_name")
            else:
                # Fallback: use folder name as title ID if xextool fails
                folder_name = os.path.basename(folder_path)
                title_id = folder_name
                media_id = None
                icon_base64 = None
                game_name = None

            # Get title name - prioritize XEX game name, then fallback to title ID
            if game_name:
                name = game_name
            else:
                name = f"Unknown Game ({title_id})"

            # Calculate folder size
            size_bytes = self._calculate_directory_size(folder_path)

            # Get DLC count
            dlc_count = self.dlc_utils.get_dlc_count(title_id)

            # Create GameInfo object with media_id
            game_info = GameInfo(
                title_id=title_id,
                name=name,
                folder_path=folder_path,
                size_bytes=size_bytes,
                size_formatted=self._format_size(size_bytes),
                media_id=media_id,
                is_extracted_iso=True,  # Mark this as an extracted ISO game
                dlc_count=dlc_count,  # Set DLC count
            )

            # Cache the icon if we extracted one
            if icon_base64:
                self._cache_xex_icon(title_id, icon_base64)

            return game_info

        except Exception as e:
            print(f"Error processing extracted ISO game {folder_path}: {e}")
            return None

    def _process_god_game(self, folder_path: str, title_id: str) -> Optional[GameInfo]:
        """Process an Xbox 360 GoD game folder"""
        try:
            # Try to extract detailed info from GoD header
            god_header_path = Path(folder_path) / "00007000"
            header_files = list(god_header_path.glob("*"))

            god_info = None
            media_id = None
            game_name = None

            if header_files:
                # Use the first header file found
                header_file_path = str(header_files[0])

                # Extract comprehensive GoD information
                god_info = self.xbox_unity.get_god_info(header_file_path)

                if god_info:
                    # Use extracted title_id if available and valid
                    if god_info.get("title_id") and god_info["title_id"] != "00000000":
                        title_id = god_info["title_id"]

                    # Get media_id for title updates
                    media_id = god_info.get("media_id")

                    # Use display_name from GoD header if available
                    if god_info.get("display_name"):
                        game_name = god_info["display_name"]

                    # Cache the icon if available
                    if god_info.get("icon_base64"):
                        self._cache_god_icon(title_id, god_info["icon_base64"])

            # Get title name - prioritize GoD extracted name, then fallback to title ID
            if game_name:
                name = game_name
            else:
                # Fallback to title ID if GoD extraction failed
                name = f"Unknown Game ({title_id})"

            # Calculate folder size
            size_bytes = self._calculate_directory_size(folder_path)

            # Get DLC count
            dlc_count = self.dlc_utils.get_dlc_count(title_id)

            # Create GameInfo object
            game_info = GameInfo(
                title_id=title_id,
                name=name,
                folder_path=folder_path,
                size_bytes=size_bytes,
                size_formatted=self._format_size(size_bytes),
                media_id=media_id,  # Add media_id from GoD extraction
                is_extracted_iso=False,  # Xbox 360 GoD games are not extracted ISOs
                dlc_count=dlc_count,  # Set DLC count
            )

            return game_info

        except Exception as e:
            print(f"Error processing Xbox 360 game {folder_path}: {e}")
            return None

    def _process_xbla_game(
        self, folder_path: str, title_id: str, xbla_exe: str
    ) -> Optional[GameInfo]:
        """Process an XBLA game folder"""
        try:
            header_file_path = xbla_exe

            # Extract comprehensive GoD information
            god_info = self.xbox_unity.get_god_info(header_file_path)

            if god_info:
                # Use extracted title_id if available and valid
                if god_info.get("title_id") and god_info["title_id"] != "00000000":
                    title_id = god_info["title_id"]

                # Get media_id for title updates
                media_id = god_info.get("media_id")

                # Use display_name from GoD header if available
                if god_info.get("display_name"):
                    game_name = god_info["display_name"]

                # Cache the icon if available
                if god_info.get("icon_base64"):
                    self._cache_god_icon(title_id, god_info["icon_base64"])

                # Get DLC count
                dlc_count = self.dlc_utils.get_dlc_count(title_id)

            # Get title name - prioritize extracted name, then fallback to title ID
            if game_name:
                name = game_name
            else:
                name = f"XBLA Game ({title_id})"

            # Calculate folder size
            size_bytes = self._calculate_directory_size(folder_path)

            # Create GameInfo object
            game_info = GameInfo(
                title_id=title_id,
                name=name,
                folder_path=folder_path,
                size_bytes=size_bytes,
                size_formatted=self._format_size(size_bytes),
                media_id=media_id,
                is_extracted_iso=False,  # XBLA games are not extracted ISOs
                dlc_count=dlc_count,  # Set DLC count
            )

            return game_info

        except Exception as e:
            print(f"Error processing XBLA game {folder_path}: {e}")
            return None

    def _scan_xbox360_directory(self):
        """Scan directory for Xbox 360/XBLA games (GoD format), XBLA games, and extracted ISO games"""
        folders = []

        # Get all subdirectories
        for item in os.listdir(self.directory):
            if self.should_stop:
                return
            item_path = os.path.join(self.directory, item)
            if os.path.isdir(item_path):
                # Check if it's an extracted ISO game (has default.xex)
                xex_path = os.path.join(item_path, "default.xex")
                if os.path.exists(xex_path):
                    folders.append((item_path, None, "iso", xex_path))
                else:
                    # Check if it's an XBLA game (has 000D0000 subfolder)
                    xbla_folder = os.path.join(item_path, "000D0000")
                    if os.path.isdir(xbla_folder):
                        # There's only one file in the 000D0000 folder, get its path
                        xbla_files = [
                            f
                            for f in os.listdir(xbla_folder)
                            if os.path.isfile(os.path.join(xbla_folder, f))
                        ]
                        if xbla_files:
                            xbla_exe = os.path.join(xbla_folder, xbla_files[0])
                            folders.append((item_path, item.upper(), "xbla", xbla_exe))
                    else:
                        # GoD format if it has 00007000 subfolder
                        god_folder = os.path.join(item_path, "00007000")
                        if os.path.isdir(god_folder):
                            folders.append((item_path, item.upper(), "god"))
                        else:
                            # Unknown format, skip
                            continue

        total_folders = len(folders)
        self.progress.emit(0, total_folders)

        for i, folder_info in enumerate(folders):
            if self.should_stop:
                return

            if len(folder_info) == 3:  # GoD format
                folder_path, title_id, game_type = folder_info
                game_info = self._process_god_game(folder_path, title_id)
            elif folder_info[2] == "xbla":  # XBLA format
                folder_path, title_id, game_type, xbla_exe = folder_info
                game_info = self._process_xbla_game(folder_path, title_id, xbla_exe)
            else:  # Extracted ISO format
                folder_path, _, game_type, xex_path = folder_info
                game_info = self._process_extracted_iso_game(folder_path, xex_path)

            if game_info and not self.should_stop:
                self.game_found.emit(game_info)

            if not self.should_stop:
                self.progress.emit(i + 1, total_folders)

        if not self.should_stop:
            self.finished.emit()

    def _calculate_directory_size(self, directory: Path) -> int:
        """Calculate total size of directory in bytes"""
        total_size = 0
        for dirpath, _, filenames in os.walk(directory):
            for filename in filenames:
                file_path = Path(dirpath) / filename
                if file_path.is_file():
                    total_size += file_path.stat().st_size
        return total_size

    def _format_size(self, size_bytes: int) -> str:
        """Format size in bytes to a human-readable string"""
        for unit in ["B", "KB", "MB", "GB"]:
            if size_bytes < 1024:
                return f"{size_bytes:.2f} {unit}"
            size_bytes /= 1024
        return f"{size_bytes:.2f} TB"

    def _cache_xex_icon(self, title_id: str, icon_base64: str):
        """Cache the extracted XEX icon to the cache/icons directory"""
        try:
            # Create cache/icons directory if it doesn't exist
            cache_icons_dir = Path("cache") / "icons"
            cache_icons_dir.mkdir(parents=True, exist_ok=True)

            # Decode base64 and save as PNG file
            icon_data = base64.b64decode(icon_base64)
            icon_path = cache_icons_dir / f"{title_id}.png"

            with open(icon_path, "wb") as f:
                f.write(icon_data)

        except Exception as e:
            print(f"Failed to cache icon for {title_id}: {e}")

    def _cache_god_icon(self, title_id: str, icon_base64: str):
        """Cache the extracted GoD icon to the cache/icons directory"""
        try:
            # Create cache/icons directory if it doesn't exist
            cache_icons_dir = Path("cache") / "icons"
            cache_icons_dir.mkdir(parents=True, exist_ok=True)

            # Decode base64 and save as PNG file
            icon_data = base64.b64decode(icon_base64)
            icon_path = cache_icons_dir / f"{title_id}.png"

            with open(icon_path, "wb") as f:
                f.write(icon_data)

        except Exception as e:
            print(f"Failed to cache GoD icon for {title_id}: {e}")

    def _cache_xbe_icon(self, title_id: str, icon_base64: str):
        """Cache the extracted XBE icon to the cache/icons directory"""
        try:
            # Create cache/icons directory if it doesn't exist
            cache_icons_dir = Path("cache") / "icons"
            cache_icons_dir.mkdir(parents=True, exist_ok=True)

            # Decode base64 and save as image file
            icon_data = base64.b64decode(icon_base64)
            icon_path = cache_icons_dir / f"{title_id}.png"

            with open(icon_path, "wb") as f:
                f.write(icon_data)

        except Exception as e:
            print(f"Failed to cache XBE icon for {title_id}: {e}")
