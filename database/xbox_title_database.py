#!/usr/bin/env python3
"""
Xbox Title Database Loader
Handles loading and querying Xbox title information from MobCatsOGXboxTitleIDs.db
"""

import hashlib
import sqlite3
from pathlib import Path
from typing import Dict, Optional, Tuple

from PyQt6.QtCore import QObject, pyqtSignal

from utils.resource_path import ResourcePath


class XboxTitleDatabaseLoader(QObject):
    """Loads and manages Xbox title database from SQLite"""

    database_loaded = pyqtSignal(dict)  # Emitted when database is loaded
    database_error = pyqtSignal(str)  # Emitted when database loading fails

    def __init__(self):
        super().__init__()
        self.database_path = ResourcePath.get_resource_path(
            "database/MobCatsOGXboxTitleIDs.db"
        )
        self.title_database: Dict[str, Dict[str, str]] = {}
        self.md5_cache: Dict[str, str] = {}  # Cache MD5s to avoid recalculating

    def load_database(self):
        """Load the Xbox title database from SQLite file"""
        try:
            if not Path(self.database_path).exists():
                raise FileNotFoundError(
                    f"Database file not found: {self.database_path}"
                )

            conn = sqlite3.connect(self.database_path)
            cursor = conn.cursor()

            # Query all title information
            cursor.execute(
                """
                SELECT XBE_MD5, Title_ID, Full_Name, Title_Name, Publisher, Region,
                       Version, Media_Type, Features
                FROM TitleIDs
                WHERE XBE_MD5 IS NOT NULL AND XBE_MD5 != ''
            """
            )

            rows = cursor.fetchall()

            # Build database dictionary keyed by XBE_MD5
            for row in rows:
                (
                    xbe_md5,
                    title_id,
                    full_name,
                    title_name,
                    publisher,
                    region,
                    version,
                    media_type,
                    features,
                ) = row

                # Use the more descriptive name if available
                display_name = (
                    full_name if full_name and full_name.strip() else title_name
                )
                if not display_name or not display_name.strip():
                    display_name = f"Unknown Game ({title_id})"

                self.title_database[xbe_md5.upper()] = {
                    "title_id": title_id or "Unknown",
                    "name": display_name.strip(),
                    "publisher": publisher or "Unknown",
                    "region": region or "Unknown",
                    "version": version or "Unknown",
                    "media_type": media_type or "Unknown",
                    "features": features or "",
                    "full_name": full_name or "",
                    "title_name": title_name or "",
                }

            conn.close()

            self.database_loaded.emit(self.title_database)

        except Exception as e:
            error_msg = f"Failed to load Xbox title database: {str(e)}"
            self.database_error.emit(error_msg)

    def get_title_info_by_xbe_path(self, xbe_path: str) -> Optional[Tuple[str, str]]:
        """
        Get title ID and name by calculating MD5 of XBE file

        Args:
            xbe_path: Path to the default.xbe file

        Returns:
            Tuple of (title_id, name) or None if not found
        """
        try:
            xbe_file = Path(xbe_path)
            if not xbe_file.exists():
                return None

            # Check cache first
            if xbe_path in self.md5_cache:
                md5_hash = self.md5_cache[xbe_path]
            else:
                # Calculate MD5 of the XBE file
                md5_hash = self._calculate_md5(xbe_file)
                if md5_hash:
                    self.md5_cache[xbe_path] = md5_hash
                else:
                    return None

            # Look up in database
            title_info = self.title_database.get(md5_hash.upper())
            if title_info:
                return title_info["title_id"], title_info["name"]

            return None

        except Exception:
            return None

    def get_full_title_info_by_xbe_path(
        self, xbe_path: str
    ) -> Optional[Dict[str, str]]:
        """
        Get full title information by calculating MD5 of XBE file

        Args:
            xbe_path: Path to the default.xbe file

        Returns:
            Dictionary with all title information or None if not found
        """
        try:
            xbe_file = Path(xbe_path)
            if not xbe_file.exists():
                return None

            # Check cache first
            if xbe_path in self.md5_cache:
                md5_hash = self.md5_cache[xbe_path]
            else:
                # Calculate MD5 of the XBE file
                md5_hash = self._calculate_md5(xbe_file)
                if md5_hash:
                    self.md5_cache[xbe_path] = md5_hash
                else:
                    return None

            # Look up in database
            return self.title_database.get(md5_hash.upper())

        except Exception:
            return None

    def _calculate_md5(self, file_path: Path) -> Optional[str]:
        """
        Calculate MD5 hash of a file

        Args:
            file_path: Path to the file

        Returns:
            MD5 hash as uppercase string or None if error
        """
        try:
            md5_hash = hashlib.md5()

            with open(file_path, "rb") as f:
                # Read in chunks to handle large files efficiently
                for chunk in iter(lambda: f.read(8192), b""):
                    md5_hash.update(chunk)

            return md5_hash.hexdigest().upper()

        except Exception:
            return None

    def clear_cache(self):
        """Clear the MD5 cache"""
        self.md5_cache.clear()

    def get_cache_stats(self) -> Tuple[int, int]:
        """Get cache statistics"""
        return len(self.md5_cache), len(self.title_database)
