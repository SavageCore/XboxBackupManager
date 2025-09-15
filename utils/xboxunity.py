import os
import re
import shutil
import struct
import sys
from typing import Any, Callable, Dict, List, Optional, Tuple

import requests

from utils.settings_manager import SettingsManager

# API Configuration
BASE_URL = "https://xboxunity.net/Api"
WEB_BASE_URL = "https://xboxunity.net"
RESOURCES_URL = "https://xboxunity.net/Resources/Lib"

# Reuse a single session to keep connections alive and improve performance
_session = requests.Session()

# Set default timeout for all requests
_session.timeout = 30


class XboxUnityError(Exception):
    """Custom exception for XboxUnity API errors"""

    pass


class XboxUnity:
    """
    Class to interact with XboxUnity API for title updates.
    This class provides methods to search for title updates, login, and download updates.
    """

    def __init__(self):
        self.session = _session
        self.settings_manager = SettingsManager()

    @staticmethod
    def test_connectivity() -> bool:
        """
        Test basic connectivity with XboxUnity.

        Returns:
            bool: True if connection successful, False otherwise
        """
        try:
            print("[INFO] Testing connectivity with XboxUnity...")
            response = _session.get("https://xboxunity.net", timeout=10)

            if response.status_code == 200:
                print("[INFO] Connectivity with XboxUnity: OK")
                return True, None
            else:
                print(f"[ERROR] XboxUnity responded with code: {response.status_code}")
                return False, f"Unexpected status code: {response.status_code}"

        except requests.exceptions.RequestException as e:
            print(f"[ERROR] Cannot connect to XboxUnity: {e}")
            return False, str(e)

    # TODO: Currently the wrong endpoint is used for login. Not sure what the correct one is.
    def login_xboxunity(self, username: str, password: str) -> Optional[str]:
        """
        Login using username/password and return authentication token.

        Args:
            username (str): XboxUnity username
            password (str): XboxUnity password

        Returns:
            Optional[str]: Authentication token if successful, None otherwise
        """
        url = f"{BASE_URL}/Auth/Login"
        headers = {
            "User-Agent": "UnityApp/1.0",
            "Content-Type": "application/x-www-form-urlencoded",
        }
        data = {"username": username, "password": password}

        try:
            print(f"[INFO] Attempting to connect to XboxUnity: {url}")
            response = _session.post(url, data=data, headers=headers, timeout=30)
            print(f"[INFO] Server response: {response.status_code}")

            if response.status_code == 200:
                try:
                    json_data = response.json()
                    print(f"[INFO] JSON response received: {json_data}")

                    if "token" in json_data:
                        print("[INFO] Token obtained successfully")
                        return json_data["token"]
                    else:
                        print("[ERROR] Token not found in response")
                        return None

                except ValueError as e:
                    print(f"[ERROR] Failed to parse login response JSON: {e}")
                    print(f"[ERROR] Response content: {response.text[:500]}")
                    return None
            else:
                print(f"[ERROR] HTTP status code: {response.status_code}")
                print(f"[ERROR] Server response: {response.text[:500]}")
                return None

        except requests.exceptions.Timeout:
            print("[ERROR] Timeout connecting to XboxUnity")
            return None
        except requests.exceptions.ConnectionError:
            print("[ERROR] Connection error with XboxUnity")
            return None
        except Exception as e:
            print(f"[ERROR] Unexpected error in login: {e}")
            return None

    def _parse_title_updates_type1(
        self, data: Dict[str, Any], title_id: str, media_id: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Parse Type 1 response (with MediaIDS structure).

        Args:
            data: JSON response data
            title_id: Title ID
            media_id: Optional Media ID filter

        Returns:
            List of title update information dictionaries
        """
        title_updates = []
        print("[INFO] Response type 1 - with MediaIDS")

        if media_id:
            print(f"[INFO] Filtering TUs only for specific MediaID: {media_id}")

        for media_item in data.get("MediaIDS", []):
            item_media_id = media_item.get("MediaID", "")
            updates = media_item.get("Updates", [])

            # Filter by Media ID if specified
            if media_id and item_media_id != media_id:
                print(
                    f"[INFO] Skipping MediaID {item_media_id} (doesn't match {media_id})"
                )
                continue

            print(
                f"[INFO] Processing MediaID: {item_media_id} ({len(updates)} updates)"
            )

            for update in updates:
                title_updates.append(
                    self._create_title_update_info(update, title_id, item_media_id)
                )

        return title_updates

    def _parse_title_updates_type2(
        self, data: Dict[str, Any], title_id: str, media_id: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Parse Type 2 response (with direct Updates structure).

        Args:
            data: JSON response data
            title_id: Title ID
            media_id: Optional Media ID filter

        Returns:
            List of title update information dictionaries
        """
        title_updates = []
        print("[INFO] Response type 2 - with direct Updates")

        for update in data.get("Updates", []):
            update_media_id = update.get("MediaID", "")

            # Filter by Media ID if specified
            if media_id and update_media_id != media_id:
                print(
                    f"[INFO] Skipping TU with MediaID {update_media_id} (doesn't match {media_id})"
                )
                continue

            title_updates.append(
                self._create_title_update_info(update, title_id, update_media_id)
            )

        return title_updates

    def _create_title_update_info(
        self, update: Dict[str, Any], title_id: str, media_id: str
    ) -> Dict[str, Any]:
        """
        Create a standardized title update information dictionary.

        Args:
            update: Update data from API response
            title_id: Title ID
            media_id: Media ID

        Returns:
            Dictionary with title update information
        """
        # Use temporary filename - will be updated with real name during download
        file_name = f"{title_id}_{update.get('Version', '1')}.tu"

        title_update_info = {
            "fileName": file_name,
            "downloadUrl": f"{RESOURCES_URL}/TitleUpdate.php?tuid={update.get('TitleUpdateID', '')}",
            "titleUpdateId": update.get("TitleUpdateID", ""),
            "version": update.get("Version", ""),
            "mediaId": media_id,
            "titleId": title_id,
            "titleName": update.get("Name", ""),
            "size": update.get("Size", 0),
            "uploadDate": update.get("UploadDate", ""),
            "hash": update.get("hash", ""),
            "baseVersion": update.get("BaseVersion", ""),
        }

        print(
            f"[INFO] TU found: {title_update_info['fileName']} "
            f"(MediaID: {title_update_info['mediaId']}, Version: {title_update_info['version']})"
        )

        return title_update_info

    def search_title_updates_with_real_endpoint(
        self,
        title_id: str,
        media_id: Optional[str] = None,
        token: Optional[str] = None,
        api_key: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        Use the real XboxUnity endpoint found in page analysis.
        Resources/Lib/TitleUpdateInfo.php - FILTERS BY SPECIFIC MEDIAID

        Args:
            title_id (str): Xbox 360 Title ID
            media_id (Optional[str]): Media ID to filter results
            token (Optional[str]): Authentication token (unused in current implementation)
            api_key (Optional[str]): API key (unused in current implementation)

        Returns:
            List[Dict[str, Any]]: List of title update information dictionaries
        """
        print(f"[INFO] Using real TitleUpdateInfo endpoint for TitleID: {title_id}")
        if media_id:
            print(f"[INFO] Filtering TUs only for MediaID: {media_id}")

        try:
            url = f"{RESOURCES_URL}/TitleUpdateInfo.php"

            # Headers to simulate web AJAX request
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
                "Accept": "application/json, text/javascript, */*; q=0.01",
                "Accept-Language": "en-US,en;q=0.5",
                "X-Requested-With": "XMLHttpRequest",
                "Referer": "https://xboxunity.net/",
            }

            params = {"titleid": title_id}

            print(f"[INFO] Querying: {url} with TitleID: {title_id}")
            response = _session.get(url, params=params, headers=headers, timeout=30)

            if response.status_code != 200:
                print(f"[ERROR] Error in TitleUpdateInfo: {response.status_code}")
                print(f"[ERROR] Response: {response.text[:200]}")
                return []

            try:
                data = response.json()
                print(f"[INFO] TitleUpdateInfo response received: {type(data)}")

                if not isinstance(data, dict):
                    if isinstance(data, list) and len(data) == 0:
                        print(f"[INFO] No TUs available for TitleID {title_id}")
                        return []
                    else:
                        print(f"[INFO] Unexpected response from real endpoint: {data}")
                        return []

                response_type = data.get("Type")
                title_updates = []

                if response_type == 1 and "MediaIDS" in data:
                    title_updates = self._parse_title_updates_type1(
                        data, title_id, media_id
                    )
                elif response_type == 2 and "Updates" in data:
                    title_updates = self._parse_title_updates_type2(
                        data, title_id, media_id
                    )
                else:
                    print(f"[INFO] Unrecognized response type: {response_type}")
                    print(f"[INFO] Complete structure: {data}")

                if title_updates:
                    print(
                        f"[INFO] Total TUs found with real endpoint: {len(title_updates)}"
                    )
                    return title_updates
                else:
                    print(
                        f"[INFO] No TUs available for TitleID {title_id} with MediaID {media_id}"
                    )
                    return []

            except ValueError as e:
                print(f"[ERROR] Error parsing TitleUpdateInfo response: {e}")
                print(f"[ERROR] Content: {response.text[:500]}")
                return []

        except requests.exceptions.RequestException as e:
            print(f"[ERROR] Error querying TitleUpdateInfo: {e}")
            return []

    def search_title_updates(
        self,
        media_id: Optional[str] = None,
        title_id: Optional[str] = None,
        token: Optional[str] = None,
        api_key: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        Main function to search for title updates.
        Only uses the endpoint that actually works.

        Args:
            media_id (Optional[str]): Media ID to filter results
            title_id (Optional[str]): Xbox 360 Title ID (required)
            token (Optional[str]): Authentication token (unused)
            api_key (Optional[str]): API key (unused)

        Returns:
            List[Dict[str, Any]]: List of title update information dictionaries

        Raises:
            XboxUnityError: If title_id is not provided
        """
        print("[INFO] Starting TU search...")

        if media_id:
            print(f"[INFO] MediaID: {media_id}")
        if title_id:
            print(f"[INFO] TitleID: {title_id}")

        if not title_id:
            error_msg = "TitleID is required to search for title updates"
            print(f"[ERROR] {error_msg}")
            raise XboxUnityError(error_msg)

        # Use the real TitleUpdateInfo.php endpoint (based on web analysis)
        print("[INFO] Testing real TitleUpdateInfo endpoint...")
        title_updates = self.search_title_updates_with_real_endpoint(
            title_id, media_id=media_id, token=token, api_key=api_key
        )

        if title_updates:
            return title_updates
        else:
            print(f"[WARNING] No TUs found for TitleID: {title_id}")
            if media_id:
                print(f"[WARNING] With specific MediaID: {media_id}")
            return []

    def _extract_filename_from_headers(self, content_disposition: str) -> Optional[str]:
        """
        Extract filename from Content-Disposition header.

        Args:
            content_disposition (str): Content-Disposition header value

        Returns:
            Optional[str]: Extracted filename or None
        """
        filename_match = re.search(
            r'filename[^;=\n]*=(([\'"]).*?\2|[^;\n]*)', content_disposition
        )
        if filename_match:
            filename = filename_match.group(1).strip("'\"")
            print(f"[INFO] Original filename from headers: {filename}")
            return filename
        return None

    def download_title_update(
        self,
        url: str,
        destination: str,
        progress_callback: Optional[Callable[[int, int], None]] = None,
    ) -> Tuple[bool, Optional[str]]:
        """
        Download a title update from the specified URL.

        Args:
            url (str): Download URL
            destination (str): Local file destination path
            progress_callback (Optional[Callable[[int, int], None]]): Progress callback function

        Returns:
            Tuple[bool, Optional[str]]: (Success status, Original filename)
        """
        try:
            print(f"[INFO] Downloading from: {url}")

            # First, get the original filename from server headers without downloading
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
                "Referer": "https://xboxunity.net/",
            }

            # Do a HEAD request first to get the actual filename
            head_response = _session.head(url, headers=headers, timeout=30)
            if head_response.status_code == 200:
                content_disposition = head_response.headers.get(
                    "content-disposition", ""
                )
                original_filename = None

                if content_disposition:
                    original_filename = self._extract_filename_from_headers(
                        content_disposition
                    )

                if not original_filename:
                    original_filename = os.path.basename(destination)

                # Check if file with the actual filename already exists
                destination_dir = os.path.dirname(destination)
                final_destination = os.path.join(destination_dir, original_filename)

                if os.path.isfile(final_destination):
                    print(
                        f"[INFO] File already exists, skipping download: {final_destination}"
                    )
                    return True, original_filename

            # Create directory if it doesn't exist
            directory = os.path.dirname(destination)
            if directory:
                os.makedirs(directory, exist_ok=True)

            response = _session.get(url, headers=headers, stream=True, timeout=60)

            if response.status_code != 200:
                print(f"[ERROR] Download error: {response.status_code}")
                print(f"[ERROR] Response: {response.text[:200]}")
                return False, None

            # Get original filename from Content-Disposition header (if we didn't get it from HEAD request)
            if "original_filename" not in locals() or not original_filename:
                content_disposition = response.headers.get("content-disposition", "")
                original_filename = None

                if content_disposition:
                    original_filename = self._extract_filename_from_headers(
                        content_disposition
                    )

                # If no filename in headers, use the provided destination filename
                if not original_filename:
                    original_filename = os.path.basename(destination)

            # Set final destination with original filename
            destination_dir = os.path.dirname(destination)
            final_destination = os.path.join(destination_dir, original_filename)
            print(f"[INFO] Downloading to: {final_destination}")

            total_size = int(response.headers.get("content-length", 0))
            print(f"[INFO] File size: {total_size} bytes")

            downloaded = 0
            with open(final_destination, "wb") as file:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        file.write(chunk)
                        downloaded += len(chunk)

                        if progress_callback and total_size > 0:
                            progress_callback(downloaded, total_size)

            print(f"[INFO] Download completed: {final_destination}")
            return True, original_filename

        except requests.exceptions.RequestException as e:
            print(f"[ERROR] Network error downloading TU: {e}")
            return False, None
        except IOError as e:
            print(f"[ERROR] File I/O error: {e}")
            return False, None
        except Exception as e:
            print(f"[ERROR] Unexpected error downloading TU: {e}")
            return False, None

    def get_title_update_information(self, url: str) -> Optional[dict]:
        """
        Return a dict of the original filename of a title update and the size from its download URL.

        Args:
            url (str): Download URL
        Returns:
            Optional[dict]: Original filename and size if found, None otherwise
        """

        try:
            print(f"[INFO] Fetching information from URL: {url}")

            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
                "Referer": "https://xboxunity.net/",
            }

            response = _session.head(url, headers=headers, timeout=30)

            if response.status_code != 200:
                print(f"[ERROR] Error fetching headers: {response.status_code}")
                return None

            size = int(response.headers.get("content-length", 0))
            original_filename = None

            content_disposition = response.headers.get("content-disposition", "")
            if content_disposition:
                original_filename = self._extract_filename_from_headers(
                    content_disposition
                )

            return {"fileName": original_filename, "size": size}

        except requests.exceptions.RequestException as e:
            print(f"[ERROR] Network error fetching filename: {e}")
            return None
        except Exception as e:
            print(f"[ERROR] Unexpected error fetching filename: {e}")
            return None

    def install_title_update(self, tu_path: str, title_id: str = None) -> bool:
        """
        Install a title update

        Args:
            tu_path (str): Path to the title update file
        Returns:
            bool: True if installation successful, False otherwise
        """
        print(f"[INFO] Installing title update from: {tu_path}")
        if not os.path.isfile(tu_path):
            print(f"[ERROR] TU file does not exist: {tu_path}")
            return False

        # Title updates that are in lowercase (for example tu00000002_00000000) go inside the Hdd1/Content/0000000000000000/{TITLE_ID}/000B0000 folder
        # Title updates that are in uppercase (for example TU_16L61V6_0000008000000.00000000000O2) go inside Hdd1/Cache folder
        filename = os.path.basename(tu_path)
        if filename.islower():
            print(
                "[INFO] Detected lowercase TU filename - installing to Content folder"
            )
            # Move to Content folder
            # Example path: Hdd1/Content/0000000000000000/{TITLE_ID}/000B0000
            content_folder = self.settings_manager.load_usb_content_directory()
            if content_folder:
                # Ensure we're set to Content/0000000000000000/, user probably just choose Content folder so we need to append the 16 zeros part
                if not content_folder.endswith("0000000000000000"):
                    content_folder = os.path.join(content_folder, "0000000000000000")
                destination = os.path.join(content_folder, title_id, "000B0000")

                # The folder may not exist yet, so create it
                os.makedirs(destination, exist_ok=True)

                print(f"[INFO] Moving TU to Content folder: {destination}")
                shutil.move(tu_path, destination)
                return True
            else:
                print("[ERROR] Content folder not found in settings.")
                return False
        elif filename.isupper():
            print("[INFO] Detected uppercase TU filename - installing to Cache folder")
            # Move to Cache folder
            cache_folder = self.settings_manager.load_usb_cache_directory()
            if cache_folder:
                destination = os.path.join(cache_folder, filename)
                print(f"[INFO] Moving TU to Cache folder: {destination}")
                shutil.move(tu_path, destination)
                return True
            else:
                print("[ERROR] Cache folder not found in settings.")
                return False

    def get_media_id(self, god_header_path):
        try:
            with open(god_header_path, "rb") as f:
                # Optional: Verify it's an STFS package by checking magic (e.g., 'CON ', 'LIVE', or 'PIRS')
                magic = f.read(4).decode("ascii", errors="ignore").strip()
                if magic not in ["CON", "LIVE", "PIRS"]:
                    print(
                        f"Warning: File magic '{magic}' does not match expected STFS types (CON, LIVE, PIRS)."
                    )

                # Seek to Media ID offset and read 4 bytes as big-endian uint32
                f.seek(0x354)
                media_id_bytes = f.read(4)
                if len(media_id_bytes) != 4:
                    raise ValueError("File too short to read Media ID.")

                media_id = struct.unpack(">I", media_id_bytes)[0]
                media_id = hex(media_id)
                # Strip '0x' prefix and convert to uppercase
                media_id = media_id[2:].upper()
                return media_id
        except FileNotFoundError:
            print(f"Error: File '{god_header_path}' not found.")
            sys.exit(1)
        except Exception as e:
            print(f"Error reading file: {e}")
            sys.exit(1)
