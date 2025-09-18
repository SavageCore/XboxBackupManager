from dataclasses import dataclass
from typing import Optional


@dataclass
class GameInfo:
    """Data class to hold game information"""

    title_id: str
    name: str
    size_bytes: int
    folder_path: str
    size_formatted: str
    transferred: bool = False
    last_modified: float = 0.0
    media_id: Optional[str] = None  # Media ID for extracted ISO games
    is_extracted_iso: bool = False  # Flag to indicate if this is an extracted ISO game
    dlc_count: int = 0  # Number of DLCs associated with the game

    @property
    def _size_formatted(self) -> str:
        """Return formatted file size"""
        size = float(self.size_bytes)
        for unit in ["B", "KB", "MB", "GB", "TB"]:
            if size < 1024.0:
                return f"{size:.1f} {unit}"
            size /= 1024.0
        return f"{size:.1f} PB"
