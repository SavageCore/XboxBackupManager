#!/usr/bin/env python3
"""
Title Update Utilities - Consolidated logic for title update operations
"""

import os
from typing import Dict, List, Optional, Tuple


class TitleUpdateUtils:
    """Consolidated utilities for title update operations"""

    @staticmethod
    def find_install_info(
        title_id: str,
        update: Dict,
        content_folder: Optional[str],
        cache_folder: Optional[str],
        is_ftp: bool = False,
        ftp_client=None,
    ) -> Optional[Dict]:
        """
        Consolidated logic to find install information for title updates.
        Works for both USB/local and FTP modes.

        Args:
            title_id: Game title ID
            update: Update information dictionary
            content_folder: Content directory path
            cache_folder: Cache directory path
            is_ftp: Whether this is FTP mode
            ftp_client: FTP client instance (required if is_ftp=True)

        Returns:
            Dict with install info or None if not found
        """
        # Ensure content folder ends with profile ID
        if content_folder and not content_folder.endswith("0000000000000000"):
            if is_ftp:
                content_folder = f"{content_folder}/0000000000000000"
            else:
                content_folder = os.path.join(content_folder, "0000000000000000")

        # Define possible paths to search
        possible_paths = [
            (
                f"{content_folder}/{title_id}/000B0000" if content_folder else None,
                "Content",
            ),
            (cache_folder, "Cache"),
        ]

        # Get expected file info from update
        title_update_info = update.get("cached_info")
        if not title_update_info:
            return None

        expected_filename = title_update_info.get("fileName", "")
        expected_size = title_update_info.get("size", 0)

        # Search in each possible location
        for base_path, location_type in possible_paths:
            if not base_path:
                continue

            result = TitleUpdateUtils._search_in_location(
                base_path,
                expected_filename,
                expected_size,
                location_type,
                is_ftp,
                ftp_client,
            )
            if result:
                return result

        return None

    @staticmethod
    def _search_in_location(
        base_path: str,
        expected_filename: str,
        expected_size: int,
        location_type: str,
        is_ftp: bool,
        ftp_client=None,
    ) -> Optional[Dict]:
        """
        Search for a title update file in a specific location.

        Returns:
            Dict with file info if found, None otherwise
        """
        try:
            if is_ftp:
                return TitleUpdateUtils._search_ftp_location(
                    base_path,
                    expected_filename,
                    expected_size,
                    location_type,
                    ftp_client,
                )
            else:
                return TitleUpdateUtils._search_local_location(
                    base_path, expected_filename, expected_size, location_type
                )
        except Exception as e:
            print(f"Error searching in {location_type} location {base_path}: {e}")
            return None

    @staticmethod
    def _search_local_location(
        base_path: str, expected_filename: str, expected_size: int, location_type: str
    ) -> Optional[Dict]:
        """Search for title update in local filesystem"""
        if not os.path.exists(base_path):
            return None

        for root, dirs, files in os.walk(base_path):
            for file in files:
                if (
                    file.upper() == expected_filename.upper()
                    and os.path.getsize(os.path.join(root, file)) == expected_size
                ):
                    return {
                        "installed": True,
                        "location": location_type,
                        "path": os.path.join(root, file),
                        "size": expected_size,
                    }
        return None

    @staticmethod
    def _search_ftp_location(
        base_path: str,
        expected_filename: str,
        expected_size: int,
        location_type: str,
        ftp_client,
    ) -> Optional[Dict]:
        """Search for title update on FTP server"""
        if not ftp_client or not ftp_client.directory_exists(base_path):
            return None

        def search_recursive(path: str) -> Optional[Dict]:
            """Recursively search FTP directory"""
            try:
                success, items, _ = ftp_client.list_directory(path)
                if not success:
                    return None

                for item in items:
                    if item["is_directory"]:
                        # Recursively search subdirectories
                        result = search_recursive(item["full_path"])
                        if result:
                            return result
                    else:
                        # Check if this file matches
                        if (
                            item["name"].upper() == expected_filename.upper()
                            and item["size"] == expected_size
                        ):
                            return {
                                "installed": True,
                                "location": location_type,
                                "path": item["full_path"],
                                "size": expected_size,
                            }
                return None
            except Exception:
                return None

        return search_recursive(base_path)

    @staticmethod
    def get_title_update_paths(
        content_folder: Optional[str], cache_folder: Optional[str], title_id: str
    ) -> List[Tuple[Optional[str], str]]:
        """
        Get standardized list of paths to search for title updates.

        Args:
            content_folder: Content directory path
            cache_folder: Cache directory path
            title_id: Game title ID

        Returns:
            List of (path, location_type) tuples
        """
        # Ensure content folder ends with profile ID
        if content_folder and not content_folder.endswith("0000000000000000"):
            content_folder = os.path.join(content_folder, "0000000000000000")

        return [
            (
                f"{content_folder}/{title_id}/000B0000" if content_folder else None,
                "Content",
            ),
            (cache_folder, "Cache"),
        ]
