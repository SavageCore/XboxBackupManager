import json
import os
from pathlib import Path
from typing import Dict, Optional


class DLCUtils:
    def __init__(self):
        pass

    def parse_file(self, dlc_path: str) -> Optional[Dict[str, Optional[str]]]:
        """
        Parse an Xbox 360/XBLA DLC file to extract the display name and title ID.
        Returns a dictionary with 'display_name' and 'title_id' keys, or None if parsing fails.
        """
        if not os.path.isfile(dlc_path):
            print(f"Invalid DLC path: {dlc_path}")
            return None

        try:
            with open(dlc_path, "rb") as f:
                data = f.read()

                # Title ID is at offset 0x360 (864) as 4 bytes, big endian
                title_id_offset = 0x360
                if len(data) < title_id_offset + 4:
                    print("File too small to contain title ID")
                    return None
                title_id_bytes = data[title_id_offset : title_id_offset + 4]
                title_id = "".join(f"{b:02X}" for b in title_id_bytes)

                # Display name is at offset 0x410 (1040), UTF-16 LE encoded
                display_name_offset = 0x410
                max_name_length = 128

                if len(data) < display_name_offset + max_name_length:
                    print("File too small to contain display name")
                    return None

                display_name_bytes = data[
                    display_name_offset : display_name_offset + max_name_length
                ]

                # Find the start of the actual string (skip leading null bytes)
                start_pos = 0
                while start_pos < len(display_name_bytes) - 1:
                    if display_name_bytes[start_pos : start_pos + 2] != b"\x00\x00":
                        break
                    start_pos += 2

                # Decode UTF-16 LE string, stop at null terminator (0x0000)
                display_name = ""
                for i in range(start_pos, len(display_name_bytes), 2):
                    if i + 1 < len(display_name_bytes):
                        char_bytes = display_name_bytes[i : i + 2]
                        if char_bytes == b"\x00\x00":  # Null terminator
                            break
                        try:
                            char = char_bytes.decode("utf-16-le")
                            char_code = ord(char)
                            # Filter out specific problematic control characters but keep printable chars
                            if (
                                char.isprintable()
                                and char_code != 0x206E  # Right-to-left override
                                and char_code != 0x0019  # End of medium control
                                and char_code
                                not in range(
                                    0x0000, 0x001F
                                )  # C0 controls (except printable)
                                and char_code not in range(0x007F, 0x009F)
                            ):  # C1 controls
                                display_name += char
                        except UnicodeDecodeError:
                            # Skip invalid characters
                            continue

                # Clean up display name (remove extra whitespace)
                display_name = " ".join(display_name.split())
                if not display_name:
                    display_name = None

                # Description is at offset 0xD10 (3344)
                description_offset = 0xD10
                max_description_length = 256

                if len(data) < description_offset + max_description_length:
                    description = None
                else:
                    description_bytes = data[
                        description_offset : description_offset + max_description_length
                    ]

                    # Find the start of the actual string (skip leading null bytes)
                    start_pos = 0
                    while start_pos < len(description_bytes) - 1:
                        if description_bytes[start_pos : start_pos + 2] != b"\x00\x00":
                            break
                        start_pos += 2

                    # Decode UTF-16 LE string, stop at null terminator (0x0000)
                    description = ""
                    for i in range(start_pos, len(description_bytes), 2):
                        if i + 1 < len(description_bytes):
                            char_bytes = description_bytes[i : i + 2]
                            if char_bytes == b"\x00\x00":  # Null terminator
                                break
                            try:
                                char = char_bytes.decode("utf-16-le")
                                char_code = ord(char)
                                # Filter out specific problematic control characters but keep printable chars
                                if (
                                    char.isprintable()
                                    and char_code != 0x206E  # Right-to-left override
                                    and char_code != 0x0019  # End of medium control
                                    and char_code
                                    not in range(
                                        0x0000, 0x001F
                                    )  # C0 controls (except printable)
                                    and char_code not in range(0x007F, 0x009F)
                                ):  # C1 controls
                                    description += char
                            except UnicodeDecodeError:
                                # Skip invalid characters
                                continue

                    # Clean up description (remove extra whitespace)
                    description = " ".join(description.split())
                    if not description:
                        description = None

                return {
                    "display_name": display_name,
                    "description": description,
                    "title_id": title_id,
                }

        except Exception as e:
            print(f"Error parsing DLC file: {e}")
            return None

    def add_dlc_to_index(
        self,
        title_id: str,
        display_name: Optional[str],
        description: Optional[str],
        game_name: Optional[str],
        size: Optional[str],
        file: Optional[str] = None,
    ):
        """
        Add a DLC entry to the local cache index (cache/dlc_index.json).
        """

        cache_dir = Path("cache")
        cache_dir.mkdir(exist_ok=True)
        index_file = cache_dir / "dlc_index.json"

        # Load existing index
        if index_file.exists():
            try:
                with open(index_file, "r", encoding="utf-8") as f:
                    dlc_index = json.load(f)
            except Exception as e:
                print(f"Error loading existing DLC index: {e}")
                dlc_index = []
        else:
            dlc_index = []

        # Check if this DLC already exists in the index
        for entry in dlc_index:
            if entry.get("file") == file:
                print(f"DLC with file {file} already exists in index.")
                return  # Already exists, do not add again

        # Add new DLC entry
        new_entry = {
            "title_id": title_id,
            "display_name": display_name,
            "description": description,
            "game_name": game_name,
            "size": size,
            "file": file,
        }
        dlc_index.append(new_entry)

        # Save updated index
        try:
            with open(index_file, "w", encoding="utf-8") as f:
                json.dump(dlc_index, f, indent=4)
        except Exception as e:
            print(f"Error saving DLC index: {e}")

    def load_dlc_index(self, title_id: str = None) -> list:
        """
        Load the DLC index from cache/dlc_index.json.
        Returns a list of DLC entries.
        """
        index_file = Path("cache") / "dlc_index.json"
        if index_file.exists():
            try:
                with open(index_file, "r", encoding="utf-8") as f:
                    dlc_index = json.load(f)

                # Check we still have the DLC file, remove entries with missing files
                valid_entries = []
                for entry in dlc_index:
                    file_path = (
                        Path("cache")
                        / "dlc"
                        / entry.get("title_id")
                        / entry.get("file")
                    )
                    if file_path and os.path.isfile(file_path):
                        valid_entries.append(entry)

                # Save any changes to the index
                if len(valid_entries) != len(dlc_index):
                    try:
                        with open(index_file, "w", encoding="utf-8") as f:
                            json.dump(valid_entries, f, indent=4)
                    except Exception as e:
                        print(f"Error saving updated DLC index: {e}")

                # If title_id is specified, filter to only that game's DLCs
                if title_id:
                    valid_entries = [
                        entry
                        for entry in valid_entries
                        if entry["title_id"] == title_id
                    ]

                # Sort by display_name
                valid_entries.sort(key=lambda x: (x.get("display_name") or "").lower())

                return valid_entries
            except Exception as e:
                print(f"Error loading DLC index: {e}")
                return []
        return []

    def get_dlc_count(self, title_id: str) -> int:
        """Get the number of DLCs associated with a game by title ID"""
        dlcs = self.load_dlc_index()
        dlcs_count = sum(1 for dlc in dlcs if dlc["title_id"] == title_id)
        return dlcs_count

    def reprocess_dlc(self, get_game_name_callback):
        """
        Reprocess the DLC files in cache/dlc to rebuild the index.
        We've changed the way we parse DLC files, so reprocess existing ones.
        A file is /cache/dlc/title_id/dlcfilename
        """
        cache_dir = Path("cache")
        dlc_dir = cache_dir / "dlc"
        if dlc_dir.exists() and dlc_dir.is_dir():
            for title_dir in dlc_dir.iterdir():
                if title_dir.is_dir():
                    for dlc_file in title_dir.glob("*"):
                        if dlc_file.is_file():
                            result = self.parse_file(str(dlc_file))
                            if result:
                                display_name = result.get("display_name")
                                description = result.get("description")
                                title_id = result.get("title_id")
                                file_size = dlc_file.stat().st_size
                                game_name = get_game_name_callback(title_id)

                                # Add to index
                                self.add_dlc_to_index(
                                    title_id=title_id,
                                    description=description,
                                    display_name=display_name,
                                    game_name=game_name,
                                    size=file_size,
                                    file=dlc_file.name,
                                )
