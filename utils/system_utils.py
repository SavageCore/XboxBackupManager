import os
import platform
import subprocess
import sys
import xml.etree.ElementTree as ET

from PyQt6.QtWidgets import QApplication, QMessageBox
from xbe import Xbe


class SystemUtils:
    """Cross-platform system utilities"""

    @staticmethod
    def open_folder_in_explorer(folder_path: str, parent_widget=None):
        """Open the folder in the system file explorer"""
        if not os.path.exists(folder_path):
            if parent_widget:
                QMessageBox.warning(
                    parent_widget,
                    "Folder Not Found",
                    f"The folder does not exist:\n{folder_path}",
                )
            return False

        try:
            system_name = platform.system()
            if system_name == "Windows":
                subprocess.run(["explorer", folder_path])
            elif system_name == "Darwin":  # macOS
                subprocess.run(["open", folder_path])
            elif system_name == "Linux":
                file_managers = ["xdg-open", "nautilus", "dolphin", "thunar", "pcmanfm"]
                opened = False
                for manager in file_managers:
                    try:
                        subprocess.run(
                            [manager, folder_path], capture_output=True, timeout=5
                        )
                        opened = True
                        break
                    except (subprocess.TimeoutExpired, FileNotFoundError):
                        continue
                    except subprocess.CalledProcessError:
                        opened = True
                        break

                if not opened and parent_widget:
                    QMessageBox.warning(
                        parent_widget,
                        "File Manager Not Found",
                        "Could not find a suitable file manager to open the folder.",
                    )
                    return False
            else:
                if parent_widget:
                    QMessageBox.warning(
                        parent_widget,
                        "Unsupported Platform",
                        f"Opening folders is not supported on {system_name}",
                    )
                return False

            return True

        except Exception as e:
            if "exit status" not in str(e).lower() and parent_widget:
                QMessageBox.warning(
                    parent_widget,
                    "Unexpected Error",
                    f"An unexpected error occurred:\n{e}",
                )
            return False

    @staticmethod
    def copy_to_clipboard(text: str):
        """Copy text to system clipboard"""
        clipboard = QApplication.clipboard()
        if clipboard is not None:
            clipboard.setText(text)

    @staticmethod
    def extract_xex_info(xex_path: str) -> dict:
        """
        Extract Title ID, Media ID, and icon from a default.xex file using xextool.exe XML output

        Args:
            xex_path: Path to the default.xex file
            xextool_path: Path to XexTool.exe (defaults to ./XexTool.exe)

        Returns:
            dict: {'title_id': str, 'media_id': str, 'icon_base64': str} or None if extraction fails
        """
        if not os.path.exists(xex_path):
            return None

        # Check if the file is actually a XEX file (basic validation)
        try:
            with open(xex_path, "rb") as f:
                header = f.read(4)
                if header != b"XEX2":
                    return None
        except Exception:
            return None

        xextool_path = os.path.join(os.getcwd(), "xextool.exe")

        if not os.path.exists(xextool_path):
            return None

        try:
            # Run xextool with XML output format including icon extraction
            result = subprocess.run(
                [xextool_path, "-x", "dtin", xex_path],
                capture_output=True,
                text=True,
                timeout=10,
            )

            if result.returncode != 0:
                return None

            output = result.stdout

            # Parse the XML output
            game_name = None
            title_id = None
            media_id = None
            icon_base64 = None

            try:
                # Parse XML output
                root = ET.fromstring(output)

                # Extract GameName
                name_element = root.find("GameName")
                if name_element is not None:
                    game_name = name_element.text if name_element.text else None

                # Extract TitleId
                title_element = root.find("TitleId")
                if title_element is not None:
                    title_id = (
                        title_element.text.upper() if title_element.text else None
                    )

                # Extract MediaId
                media_element = root.find("MediaId")
                if media_element is not None:
                    # MediaId is 16 bytes (32 hex chars), but we need the last 8 chars for compatibility
                    media_full = (
                        media_element.text.upper() if media_element.text else None
                    )
                    if media_full and len(media_full) >= 8:
                        # Take the last 8 characters for the media ID
                        media_id = media_full[-8:]

                # Extract GameIcon (base64 encoded)
                icon_element = root.find("GameIcon")
                if icon_element is not None:
                    icon_base64 = icon_element.text if icon_element.text else None

                if title_id:
                    result_dict = {"title_id": title_id}
                    if media_id:
                        result_dict["media_id"] = media_id
                    if icon_base64:
                        result_dict["icon_base64"] = icon_base64
                    if game_name:
                        result_dict["game_name"] = game_name
                    return result_dict
                else:
                    return None

            except ET.ParseError:
                return None

        except (
            subprocess.TimeoutExpired,
            subprocess.CalledProcessError,
            Exception,
        ):
            return None

    @staticmethod
    def extract_xbe_info(xbe_path: str) -> dict:
        """
        Extract Title ID, Title Name, and icon from a default.xbe file using pyxbe

        Args:
            xbe_path: Path to the default.xbe file

        Returns:
            dict: {'title_id': str, 'title_name': str, 'icon_base64': str} or None if extraction fails
        """
        if not Xbe:
            print("pyxbe library not available")
            return None

        if not os.path.exists(xbe_path):
            return None

        try:
            # Load the XBE file using the proper from_file method
            xbe = Xbe.from_file(xbe_path)

            # Extract basic information
            title_id = None
            title_name = None

            # Get Title ID from certificate
            if hasattr(xbe, "cert") and hasattr(xbe.cert, "title_id"):
                title_id = f"{xbe.cert.title_id:08X}"  # Format as hex string

            # Get Title Name - available directly on xbe object
            if hasattr(xbe, "title_name"):
                title_name = xbe.title_name

            return {
                "title_id": title_id,
                "title_name": title_name,
            }

        except Exception as e:
            print(f"Error extracting XBE info from {xbe_path}: {e}")
            return None

    @staticmethod
    def restart_app(self):
        """Restart the application with error handling"""
        try:
            if getattr(sys, "frozen", False):
                # Running as PyInstaller executable
                executable_path = sys.executable
                args = sys.argv[1:]  # Preserve command line arguments
            else:
                # Running as Python script
                executable_path = sys.executable
                args = [sys.argv[0]] + sys.argv[1:]

            # Ensure the executable exists
            if not os.path.exists(executable_path):
                QMessageBox.critical(None, "Error", "Cannot find executable to restart")
                return

            # Start new instance with detached process
            if getattr(sys, "frozen", False):
                subprocess.Popen(
                    [executable_path] + args,
                    creationflags=(
                        subprocess.DETACHED_PROCESS if sys.platform == "win32" else 0
                    ),
                )
            else:
                subprocess.Popen([executable_path] + args)

            # Exit current instance
            QApplication.instance().quit()

        except Exception as e:
            QMessageBox.critical(
                None, "Restart Error", f"Failed to restart application: {str(e)}"
            )
