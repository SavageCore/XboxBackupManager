import os

from PyQt6.QtWidgets import (
    QDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
)

from utils.xboxunity import XboxUnity
from utils.settings_manager import SettingsManager


class XboxUnityTitleUpdatesDialog(QDialog):
    """Dialog for viewing Xbox Unity title updates"""

    def __init__(self, parent=None, title_id=None, updates=None):
        super().__init__(parent)
        self.title_id = title_id
        self.updates = updates or []
        self.xbox_unity = XboxUnity()
        self.settings_manager = SettingsManager()
        # Sort updates by version number (descending) - highest version first
        self.updates = sorted(
            self.updates, key=lambda x: int(x.get("version", 0)), reverse=True
        )
        self.current_mode = parent.current_mode if parent else "usb"
        self._init_ui()

    def _is_title_update_installed(self, title_id: str, update) -> bool:
        """Check if a title update is installed by looking in Content and Cache folders"""
        print("")
        print("")
        print(
            f"[INFO] Checking if title update {update.get('fileName')} is installed..."
        )
        if self.current_mode == "ftp":
            content_folder = self.settings_manager.load_ftp_content_directory()
            cache_folder = self.settings_manager.load_ftp_cache_directory()
        else:
            content_folder = self.settings_manager.load_usb_content_directory()
            cache_folder = self.settings_manager.load_usb_cache_directory()

        if content_folder:
            # Ensure we're set to Content/0000000000000000/, user probably just choose Content folder so we need to append the 16 zeros part
            if not content_folder.endswith("0000000000000000"):
                content_folder = os.path.join(content_folder, "0000000000000000")
        else:
            return False  # Can't check if no content folder set

        # Check both common Xbox 360 locations
        possible_paths = [
            f"{content_folder}/{title_id}/000B0000",
            cache_folder,
        ]

        # Use cached info instead of making API call
        title_update_info = update.get("cached_info")
        if not title_update_info:
            print("[Info] No cached title update info available.")
            return False

        for base_path in possible_paths:
            if os.path.exists(base_path):
                # Look for title update files matching the media ID or version
                for root, dirs, files in os.walk(base_path):
                    for file in files:
                        # Check if the file matches the expected title update filename and size
                        if file.upper() == title_update_info.get(
                            "fileName", ""
                        ).upper() and os.path.getsize(
                            os.path.join(root, file)
                        ) == title_update_info.get(
                            "size", 0
                        ):
                            print(
                                f"[INFO] Found installed title update file: {file} in {root} with size {os.path.getsize(os.path.join(root, file))}"
                            )
                            return True
        return False

    def _uninstall_title_update(
        self,
        title_id: str,
        version: str,
        media_id: str,
        button: QPushButton,
        update: dict,
    ) -> None:
        """Uninstall a title update by removing it from Content and Cache folders"""
        removed_files = []

        if self.current_mode == "ftp":
            content_folder = self.settings_manager.load_ftp_content_directory()
            cache_folder = self.settings_manager.load_ftp_cache_directory()
        else:
            content_folder = self.settings_manager.load_usb_content_directory()
            cache_folder = self.settings_manager.load_usb_cache_directory()

        if content_folder:
            # Ensure we're set to Content/0000000000000000/, user probably just choose Content folder so we need to append the 16 zeros part
            if not content_folder.endswith("0000000000000000"):
                content_folder = os.path.join(content_folder, "0000000000000000")
        else:
            return False  # Can't check if no content folder set

        # Check both common Xbox 360 locations
        possible_paths = [
            f"{content_folder}/{title_id}/000B0000",
            cache_folder,
        ]

        # Use cached info instead of making API call
        title_update_info = update.get("cached_info")
        if not title_update_info:
            print("[Info] No cached title update info available.")
            return False

        for base_path in possible_paths:
            if os.path.exists(base_path):
                print(f"Searching for title update files in {base_path}")
                for root, dirs, files in os.walk(base_path):
                    for file in files:
                        print(f"Checking file {file} in {root}")
                        print(
                            f"Looking for {title_update_info.get('fileName', '')} of size {title_update_info.get('size', 0)}"
                        )
                        print(f"File size: {os.path.getsize(os.path.join(root, file))}")
                        if file.upper() == title_update_info.get(
                            "fileName", ""
                        ).upper() and os.path.getsize(
                            os.path.join(root, file)
                        ) == title_update_info.get(
                            "size", 0
                        ):
                            try:
                                os.remove(os.path.join(root, file))
                                removed_files.append(os.path.join(root, file))
                            except Exception as e:
                                print(f"Error removing file {file}: {e}")

        if removed_files:
            print(f"Removed title update files: {removed_files}")
            button.setText("Download")
        else:
            print("No title update files found to remove")

    def _init_ui(self):
        """Initialize the dialog UI"""
        self.setWindowTitle("Xbox Unity Title Updates")
        self.setModal(True)
        self.setMinimumWidth(400)

        layout = QVBoxLayout(self)

        # [{'fileName': '394F07D1_3.tu', 'downloadUrl': 'https://xboxunity.net/Resources/Lib/TitleUpdate.php?tuid=23374', 'titleUpdateId': '23374', 'version': '3', 'mediaId': '0E696BB9', 'titleId': '394F07D1', 'titleName': 'Diablo III', 'size': '2272', 'uploadDate': '2013-12-11 00:00:00', 'hash': 'BDFC8D7D71C3F83E8DDBEC55B37E59E14C82499E', 'baseVersion': '00000004'}, {'fileName': '394F07D1_2.tu', 'downloadUrl': 'https://xboxunity.net/Resources/Lib/TitleUpdate.php?tuid=23229', 'titleUpdateId': '23229', 'version': '2', 'mediaId': '0E696BB9', 'titleId': '394F07D1', 'titleName': 'Diablo III', 'size': '2108', 'uploadDate': '2013-10-03 00:00:00', 'hash': 'ACECB6DB91DAF682BD4614E4F2385880C0D21E04', 'baseVersion': '00000004'}, {'fileName': '394F07D1_4.tu', 'downloadUrl': 'https://xboxunity.net/Resources/Lib/TitleUpdate.php?tuid=23838', 'titleUpdateId': '23838', 'version': '4', 'mediaId': '1C7C4B06', 'titleId': '394F07D1', 'titleName': 'Diablo III', 'size': '5108', 'uploadDate': '2014-08-27 00:00:00', 'hash': 'A85EF5748B9E4850BAE39B63E019D266A7DC9467', 'baseVersion': '0000000B'}, {'fileName': '394F07D1_3.tu', 'downloadUrl': 'https://xboxunity.net/Resources/Lib/TitleUpdate.php?tuid=23252', 'titleUpdateId': '23252', 'version': '3', 'mediaId': '1C7C4B06', 'titleId': '394F07D1', 'titleName': 'Diablo III', 'size': '2272', 'uploadDate': '2013-10-15 00:00:00', 'hash': 'E0227D628064524C3FB1119343697A42396D15FD', 'baseVersion': '0000000B'}, {'fileName': '394F07D1_2.tu', 'downloadUrl': 'https://xboxunity.net/Resources/Lib/TitleUpdate.php?tuid=23197', 'titleUpdateId': '23197', 'version': '2', 'mediaId': '1C7C4B06', 'titleId': '394F07D1', 'titleName': 'Diablo III', 'size': '2108', 'uploadDate': '2013-09-10 00:00:00', 'hash': '407697744821E6EA4CAB57A9C2D3E4AD19BA1035', 'baseVersion': '0000000B'}, {'fileName': '394F07D1_4.tu', 'downloadUrl': 'https://xboxunity.net/Resources/Lib/TitleUpdate.php?tuid=23810', 'titleUpdateId': '23810', 'version': '4', 'mediaId': '26C4AC9A', 'titleId': '394F07D1', 'titleName': 'Diablo III', 'size': '6056', 'uploadDate': '2014-08-19 00:00:00', 'hash': 'FFEF5DB14325365456A842B5CE228F652B185819', 'baseVersion': '00000007'}, {'fileName': '394F07D1_3.tu', 'downloadUrl': 'https://xboxunity.net/Resources/Lib/TitleUpdate.php?tuid=23279', 'titleUpdateId': '23279', 'version': '3', 'mediaId': '26C4AC9A', 'titleId': '394F07D1', 'titleName': 'Diablo III', 'size': '2264', 'uploadDate': '2013-10-27 00:00:00', 'hash': 'A471F1C5BBBD0F75470F5F5E5F58BB0240B1742E', 'baseVersion': '00000007'}, {'fileName': '394F07D1_2.tu', 'downloadUrl': 'https://xboxunity.net/Resources/Lib/TitleUpdate.php?tuid=23189', 'titleUpdateId': '23189', 'version': '2', 'mediaId': '26C4AC9A', 'titleId': '394F07D1', 'titleName': 'Diablo III', 'size': '2096', 'uploadDate': '2013-09-05 00:00:00', 'hash': 'B004658261B176C2AFF873B18D6EBC4A80AC9BAB', 'baseVersion': '00000007'}, {'fileName': '394F07D1_3.tu', 'downloadUrl': 'https://xboxunity.net/Resources/Lib/TitleUpdate.php?tuid=23440', 'titleUpdateId': '23440', 'version': '3', 'mediaId': '2C584E7F', 'titleId': '394F07D1', 'titleName': 'Diablo III', 'size': '2272', 'uploadDate': '2014-01-10 00:00:00', 'hash': '1228E3293C9DA46822AFC90DFCD94DFF73B950CD', 'baseVersion': '00000008'}, {'fileName': '394F07D1_4.tu', 'downloadUrl': 'https://xboxunity.net/Resources/Lib/TitleUpdate.php?tuid=23811', 'titleUpdateId': '23811', 'version': '4', 'mediaId': '68E5958A', 'titleId': '394F07D1', 'titleName': 'Diablo III', 'size': '6092', 'uploadDate': '2014-08-19 00:00:00', 'hash': 'B533A20BDE4743F87430ED7D4C2C161BCCE50C5F', 'baseVersion': '0000000F'}, {'fileName': '394F07D1_3.tu', 'downloadUrl': 'https://xboxunity.net/Resources/Lib/TitleUpdate.php?tuid=23254', 'titleUpdateId': '23254', 'version': '3', 'mediaId': '68E5958A', 'titleId': '394F07D1', 'titleName': 'Diablo III', 'size': '2272', 'uploadDate': '2013-10-15 00:00:00', 'hash': '01B3C044404A35D5ED19BE7E422D2CBD2B7BE638', 'baseVersion': '0000000F'}, {'fileName': '394F07D1_2.tu', 'downloadUrl': 'https://xboxunity.net/Resources/Lib/TitleUpdate.php?tuid=23180', 'titleUpdateId': '23180', 'version': '2', 'mediaId': '68E5958A', 'titleId': '394F07D1', 'titleName': 'Diablo III', 'size': '2108', 'uploadDate': '2013-08-30 00:00:00', 'hash': '11B7C32B9C88EBC7BD4EFCD2642C18262CF36AE2', 'baseVersion': '0000000F'}, {'fileName': '394F07D1_3.tu', 'downloadUrl': 'https://xboxunity.net/Resources/Lib/TitleUpdate.php?tuid=23255', 'titleUpdateId': '23255', 'version': '3', 'mediaId': '6BD3D4A9', 'titleId': '394F07D1', 'titleName': 'Diablo III', 'size': '2272', 'uploadDate': '2013-10-16 00:00:00', 'hash': 'AB340C2AC7F5C340446F824D8AC5C34D6EBE3D98', 'baseVersion': '00000003'}, {'fileName': '394F07D1_2.tu', 'downloadUrl': 'https://xboxunity.net/Resources/Lib/TitleUpdate.php?tuid=23185', 'titleUpdateId': '23185', 'version': '2', 'mediaId': '6BD3D4A9', 'titleId': '394F07D1', 'titleName': 'Diablo III', 'size': '2108', 'uploadDate': '2013-09-02 00:00:00', 'hash': 'FE2D4C5C589CDF79A13FB4317C6127A86DFFC6FB', 'baseVersion': '00000003'}, {'fileName': '394F07D1_4.tu', 'downloadUrl': 'https://xboxunity.net/Resources/Lib/TitleUpdate.php?tuid=23863', 'titleUpdateId': '23863', 'version': '4', 'mediaId': '7A13A2D8', 'titleId': '394F07D1', 'titleName': 'Diablo III', 'size': '5112', 'uploadDate': '2014-09-17 00:00:00', 'hash': '80CFCBC5F50737D288C79B55365F1BF5C795E7E4', 'baseVersion': '0000000D'}, {'fileName': '394F07D1_3.tu', 'downloadUrl': 'https://xboxunity.net/Resources/Lib/TitleUpdate.php?tuid=23253', 'titleUpdateId': '23253', 'version': '3', 'mediaId': '7A13A2D8', 'titleId': '394F07D1', 'titleName': 'Diablo III', 'size': '2272', 'uploadDate': '2013-10-15 00:00:00', 'hash': '1248C8BCA697A4A671AB1C87590F051295D04389', 'baseVersion': '0000000D'}, {'fileName': '394F07D1_2.tu', 'downloadUrl': 'https://xboxunity.net/Resources/Lib/TitleUpdate.php?tuid=23186', 'titleUpdateId': '23186', 'version': '2', 'mediaId': '7A13A2D8', 'titleId': '394F07D1', 'titleName': 'Diablo III', 'size': '2108', 'uploadDate': '2013-09-03 00:00:00', 'hash': '6238DEE31C2F4FE74766847A1DF8593FA1E8000F', 'baseVersion': '0000000D'}]
        # Show a table of title updates here, sorted by version number descending
        # Columns: Version, Size (in MB), Upload Date, Download Button
        updates_group = QGroupBox(f"Title Updates for {self.title_id}")
        updates_layout = QFormLayout(updates_group)

        for update in self.updates:
            version = update.get("version", "N/A")
            media_id = update.get("mediaId", "")
            download_url = update.get("downloadUrl", "")
            title_update_info = self.xbox_unity.get_title_update_information(
                download_url
            )
            update["cached_info"] = title_update_info  # Store it in the update dict

            version_input = QLineEdit()
            version_input.setText(version)
            version_input.setReadOnly(True)

            size_input = QLineEdit()
            size_input.setText(f"{int(update.get('size', 0)) / 1024:.2f} MB")
            size_input.setReadOnly(True)

            date_input = QLineEdit()
            date_input.setText(update.get("uploadDate", "N/A"))
            date_input.setReadOnly(True)

            # Check if title update is already installed
            is_installed = self._is_title_update_installed(self.title_id, update)

            download_input = QPushButton("Uninstall" if is_installed else "Download")
            download_url = update.get("downloadUrl", "")

            update_layout = QHBoxLayout()
            update_layout.addWidget(version_input)
            update_layout.addWidget(size_input)
            update_layout.addWidget(date_input)

            destination = f"cache/tu/{self.title_id}/"

            if is_installed:
                # Connect uninstall action
                download_input.clicked.connect(
                    lambda checked, ver=version, mid=media_id, btn=download_input, upd=update: self._uninstall_title_update(
                        self.title_id, ver, mid, btn, upd
                    )
                )
            else:
                # Connect download and install action
                download_input.clicked.connect(
                    lambda checked, url=download_url, btn=download_input, ver=version, mid=media_id, upd=update: self._download_and_install(
                        url, destination, self.title_id, btn, ver, mid, upd
                    )
                )

            update_layout.addWidget(download_input)

            updates_layout.addRow(f"Version {version}:", update_layout)

        layout.addWidget(updates_group)

    def _download_and_install(
        self,
        url: str,
        destination: str,
        title_id: str,
        button: QPushButton,
        version: str,
        media_id: str,
        update: dict,
    ) -> None:
        """Download and install a title update, then update button state"""
        button.setText("Downloading...")
        button.setEnabled(False)

        success, tu_path = self.xbox_unity.download_title_update(url, destination)
        if success:
            install_success = self.xbox_unity.install_title_update(
                destination + tu_path, title_id
            )
            if install_success:
                button.setText("Uninstall")
                button.setEnabled(True)
                button.clicked.disconnect()
                button.clicked.connect(
                    lambda checked: self._uninstall_title_update(
                        title_id, version, media_id, button, update
                    )
                )
            else:
                button.setText("Download")
                button.setEnabled(True)
                print("Failed to install title update")
        else:
            button.setText("Download")
            button.setEnabled(True)
            print("Failed to download title update")
