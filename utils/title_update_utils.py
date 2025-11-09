#!/usr/bin/env python3
"""
Title Update Utilities - Consolidated logic for title update operations
"""

import os
from typing import Dict, List, Optional, Tuple

from utils.ftp_connection_manager import get_ftp_manager


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
                        "filename": os.path.basename(file),
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
        """Search for title update in FTP directories."""

        # Uppercase filenames (TU_*) are in Cache, lowercase (tu*) are in Content
        if expected_filename.startswith("TU_"):
            # Check Cache directory
            try:
                items = ftp_client.list_directory("/Hdd1/Cache")
                for item in items:
                    if item["name"] == expected_filename:
                        item_size = item.get("size", 0)
                        if item_size == expected_size:
                            return {
                                "path": f"/Hdd1/Cache/{expected_filename}",
                                "filename": expected_filename,
                            }
            except Exception:
                pass
        else:
            # Check Content directory structure
            # Extract title_id from base_path (e.g., /Hdd1/Content/0000000000000000/4D530919/000B0000)
            path_parts = base_path.split("/")
            if len(path_parts) >= 5:
                title_id = path_parts[4]
                content_path = f"/Hdd1/Content/0000000000000000/{title_id}/000B0000"
                try:
                    items = ftp_client.list_directory(content_path)
                    for item in items:
                        if item["name"] == expected_filename:
                            item_size = item.get("size", 0)
                            if item_size == expected_size:
                                return {
                                    "path": f"{content_path}/{expected_filename}",
                                    "filename": expected_filename,
                                }
                except Exception:
                    pass

        return None

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

    @staticmethod
    def _is_title_update_installed(
        title_id: str, update, current_mode: str, settings_manager
    ) -> bool:
        """Check if a title update is installed by looking in Content and Cache folders"""
        if current_mode == "ftp":
            return TitleUpdateUtils._is_title_update_installed_ftp(title_id, update)
        else:
            return TitleUpdateUtils._is_title_update_installed_usb(
                title_id, update, settings_manager
            )

    @staticmethod
    def _is_title_update_installed_usb(title_id: str, update, settings_manager) -> bool:
        """Check if title update is installed on USB/local storage"""
        content_folder = settings_manager.load_usb_content_directory()
        cache_folder = settings_manager.load_usb_cache_directory()

        if content_folder:
            if not content_folder.endswith("0000000000000000"):
                content_folder = os.path.join(content_folder, "0000000000000000")
        else:
            return False

        possible_paths = [
            f"{content_folder}/{title_id}/000B0000",
            cache_folder,
        ]

        title_update_info = update.get("cached_info")
        if not title_update_info:
            return False

        for base_path in possible_paths:
            if base_path and os.path.exists(base_path):
                for root, dirs, files in os.walk(base_path):
                    for file in files:
                        if file.upper() == title_update_info.get(
                            "fileName", ""
                        ).upper() and os.path.getsize(
                            os.path.join(root, file)
                        ) == title_update_info.get("size", 0):
                            return True
        return False

    @staticmethod
    def _is_title_update_installed_ftp(title_id: str, update: dict) -> bool:
        """Check if title update is installed via FTP."""
        try:
            ftp_client = get_ftp_manager().get_connection()
            if not ftp_client:
                return False

            # Get the actual filename from cached_info (not the reference filename from search)
            title_update_info = update.get("cached_info")
            if not title_update_info:
                return False

            filename = title_update_info.get("fileName", "")
            expected_size = title_update_info.get("size", 0)

            if not filename:
                return False

            # Uppercase filenames (TU_*) go to Cache, lowercase (tu*) go to Content
            if filename.startswith("TU_") or filename.isupper():
                # Check Cache directory
                try:
                    success, items, _ = ftp_client.list_directory("/Hdd1/Cache")
                    if success:
                        for item in items:
                            if (
                                item["name"].upper() == filename.upper()
                                and item.get("size", 0) == expected_size
                            ):
                                return True
                except Exception:
                    pass
            else:
                # Check Content directory structure
                content_base = f"/Hdd1/Content/0000000000000000/{title_id}/000B0000"
                try:
                    success, items, _ = ftp_client.list_directory(content_base)
                    if success:
                        for item in items:
                            if (
                                item["name"].upper() == filename.upper()
                                and item.get("size", 0) == expected_size
                            ):
                                return True
                except Exception:
                    pass

            return False

        except Exception as e:
            print(f"[ERROR] FTP installation check failed: {e}")
            return False
