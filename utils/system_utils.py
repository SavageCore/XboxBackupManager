import logging
import os
import platform
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

from PyQt6.QtWidgets import QApplication, QMessageBox
from xbe import Xbe

# Set up logging
logger = logging.getLogger(__name__)


class SystemUtils:
    """Cross-platform system utilities with enhanced security"""

    @staticmethod
    def open_folder_in_explorer(folder_path: str, parent_widget=None):
        """Open the folder in the system file explorer using safer methods"""
        if not os.path.exists(folder_path):
            if parent_widget:
                QMessageBox.warning(
                    parent_widget,
                    "Folder Not Found",
                    f"The folder does not exist:\n{folder_path}",
                )
            return False

        try:
            folder_path = os.path.normpath(folder_path)  # Normalize path for security
            system_name = platform.system()

            logger.info(f"Opening folder in {system_name}: {folder_path}")

            if system_name == "Windows":
                # Use os.startfile - less suspicious than subprocess
                try:
                    os.startfile(folder_path)
                    return True
                except OSError as e:
                    logger.warning(f"os.startfile failed: {e}, trying subprocess")
                    # Fallback to subprocess with explicit command
                    subprocess.run(
                        ["explorer", folder_path],
                        check=True,
                        timeout=10,
                        creationflags=subprocess.CREATE_NO_WINDOW,
                    )
                    return True

            elif system_name == "Darwin":  # macOS
                # Use subprocess with explicit, safe command
                subprocess.run(
                    ["open", folder_path],
                    check=True,
                    timeout=10,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
                return True

            elif system_name == "Linux":
                # Check for available file managers in order of preference
                file_managers = ["xdg-open", "nautilus", "dolphin", "thunar"]

                for fm in file_managers:
                    if shutil.which(fm):  # Check if command exists
                        try:
                            subprocess.run(
                                [fm, folder_path],
                                check=True,
                                timeout=10,
                                stdout=subprocess.DEVNULL,
                                stderr=subprocess.DEVNULL,
                            )
                            return True
                        except (
                            subprocess.CalledProcessError,
                            subprocess.TimeoutExpired,
                        ):
                            continue

                # No suitable file manager found
                if parent_widget:
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

        except subprocess.TimeoutExpired:
            if parent_widget:
                QMessageBox.warning(
                    parent_widget,
                    "Timeout Error",
                    "File manager took too long to respond",
                )
            return False
        except subprocess.CalledProcessError as e:
            if parent_widget:
                QMessageBox.warning(
                    parent_widget,
                    "File Manager Error",
                    f"Could not open folder: {e}",
                )
            return False
        except Exception as e:
            logger.error(f"Unexpected error opening folder: {e}")
            if parent_widget:
                QMessageBox.warning(
                    parent_widget,
                    "Unexpected Error",
                    f"An unexpected error occurred:\n{e}",
                )
            return False

    @staticmethod
    def copy_to_clipboard(text: str):
        """Copy text to system clipboard"""
        try:
            clipboard = QApplication.clipboard()
            if clipboard is not None:
                clipboard.setText(text)
                logger.debug("Text copied to clipboard")
        except Exception as e:
            logger.error(f"Failed to copy to clipboard: {e}")

    @staticmethod
    def extract_xex_info(xex_path: str) -> dict:
        """
        Extract Title ID, Media ID, and icon from a default.xex file using xextool.exe XML output
        with enhanced validation and security

        Args:
            xex_path: Path to the default.xex file

        Returns:
            dict: {'title_id': str, 'media_id': str, 'icon_base64': str} or None if extraction fails
        """
        if not os.path.exists(xex_path):
            logger.warning(f"XEX file not found: {xex_path}")
            return None

        # Validate file path for security
        xex_path = os.path.normpath(os.path.abspath(xex_path))

        # Check if the file is actually a XEX file (basic validation)
        try:
            with open(xex_path, "rb") as f:
                header = f.read(4)
                if header != b"XEX2":
                    logger.warning(f"Invalid XEX file header: {xex_path}")
                    return None
        except Exception as e:
            logger.error(f"Error reading XEX file: {e}")
            return None

        # Look for xextool in current directory with proper validation
        xextool_path = Path.cwd() / "xextool.exe"

        if not xextool_path.exists():
            logger.warning(f"XexTool not found at: {xextool_path}")
            return None

        # Validate xextool is actually executable
        if not os.access(xextool_path, os.X_OK):
            logger.warning(f"XexTool is not executable: {xextool_path}")
            return None

        try:
            logger.info(f"Extracting XEX info from: {xex_path}")

            # Use absolute paths for security and clarity
            xextool_abs = str(xextool_path.resolve())
            xex_abs = str(Path(xex_path).resolve())

            # Run xextool with XML output format including icon extraction
            # Use explicit arguments list for security
            cmd_args = [xextool_abs, "-x", "dtin", xex_abs]

            result = subprocess.run(
                cmd_args,
                capture_output=True,
                text=True,
                timeout=30,  # Increased timeout for large files
                cwd=str(Path.cwd()),  # Explicit working directory
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
            )

            if result.returncode != 0:
                logger.warning(f"XexTool returned error code {result.returncode}")
                if result.stderr:
                    logger.warning(f"XexTool stderr: {result.stderr}")
                return None

            output = result.stdout
            if not output.strip():
                logger.warning("XexTool returned empty output")
                return None

            # Parse the XML output with enhanced error handling
            game_name = None
            title_id = None
            media_id = None
            icon_base64 = None

            try:
                # Parse XML output with validation
                root = ET.fromstring(output)

                if root.tag != "XexInfo":  # Basic XML structure validation
                    logger.warning("Unexpected XML structure from XexTool")

                # Extract GameName
                name_element = root.find("GameName")
                if name_element is not None and name_element.text:
                    game_name = name_element.text.strip()

                # Extract TitleId
                title_element = root.find("TitleId")
                if title_element is not None and title_element.text:
                    title_id = title_element.text.strip().upper()

                # Extract MediaId
                media_element = root.find("MediaId")
                if media_element is not None and media_element.text:
                    # MediaId is 16 bytes (32 hex chars), but we need the last 8 chars for compatibility
                    media_full = media_element.text.strip().upper()
                    if len(media_full) >= 8:
                        # Take the last 8 characters for the media ID
                        media_id = media_full[-8:]

                # Extract GameIcon (base64 encoded)
                icon_element = root.find("GameIcon")
                if icon_element is not None and icon_element.text:
                    icon_base64 = icon_element.text.strip()

                # Build result dictionary
                if title_id:
                    result_dict = {"title_id": title_id}
                    if media_id:
                        result_dict["media_id"] = media_id
                    if icon_base64:
                        result_dict["icon_base64"] = icon_base64
                    if game_name:
                        result_dict["game_name"] = game_name

                    logger.info(f"Successfully extracted XEX info: Title ID {title_id}")
                    return result_dict
                else:
                    logger.warning("No Title ID found in XEX file")
                    return None

            except ET.ParseError as e:
                logger.error(f"XML parsing error: {e}")
                return None

        except subprocess.TimeoutExpired:
            logger.error("XexTool operation timed out")
            return None
        except subprocess.CalledProcessError as e:
            logger.error(f"XexTool process error: {e}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error in XEX extraction: {e}")
            return None

    @staticmethod
    def extract_xbe_info(xbe_path: str) -> dict:
        """
        Extract Title ID, Title Name, and icon from a default.xbe file using pyxbe
        with enhanced validation

        Args:
            xbe_path: Path to the default.xbe file

        Returns:
            dict: {'title_id': str, 'title_name': str, 'icon_base64': str} or None if extraction fails
        """
        if not Xbe:
            logger.warning("pyxbe library not available")
            return None

        if not os.path.exists(xbe_path):
            logger.warning(f"XBE file not found: {xbe_path}")
            return None

        # Validate and normalize path
        xbe_path = os.path.normpath(os.path.abspath(xbe_path))

        try:
            logger.info(f"Extracting XBE info from: {xbe_path}")

            # Load the XBE file using the proper from_file method
            xbe = Xbe.from_file(xbe_path)

            # Extract basic information with validation
            title_id = None
            title_name = None

            # Get Title ID from certificate
            if hasattr(xbe, "cert") and hasattr(xbe.cert, "title_id"):
                title_id = f"{xbe.cert.title_id:08X}"  # Format as hex string
                logger.debug(f"Extracted Title ID: {title_id}")

            # Get Title Name - available directly on xbe object
            if hasattr(xbe, "title_name") and xbe.title_name:
                title_name = xbe.title_name.strip()
                logger.debug(f"Extracted Title Name: {title_name}")

            result = {
                "title_id": title_id,
                "title_name": title_name,
            }

            # Only return if we have at least a title ID
            if title_id:
                logger.info(f"Successfully extracted XBE info: Title ID {title_id}")
                return result
            else:
                logger.warning("No Title ID found in XBE file")
                return None

        except Exception as e:
            logger.error(f"Error extracting XBE info from {xbe_path}: {e}")
            return None

    @staticmethod
    def restart_app():
        """Restart the application with enhanced error handling and security"""
        try:
            logger.info("Attempting to restart application")

            if getattr(sys, "frozen", False):
                # Running as PyInstaller executable
                executable_path = sys.executable
                args = sys.argv[1:]  # Preserve command line arguments
                logger.info(f"Restarting frozen app: {executable_path}")
            else:
                # Running as Python script
                executable_path = sys.executable
                args = [sys.argv[0]] + sys.argv[1:]
                logger.info(f"Restarting Python script: {executable_path} {args}")

            # Validate executable exists and is actually executable
            if not os.path.exists(executable_path):
                error_msg = f"Cannot find executable to restart: {executable_path}"
                logger.error(error_msg)
                QMessageBox.critical(None, "Restart Error", error_msg)
                return False

            if not os.access(executable_path, os.X_OK):
                logger.warning(
                    f"Executable may not have execute permissions: {executable_path}"
                )

            # Prepare environment for new process
            env = os.environ.copy()
            env["XBOX_BACKUP_RESTARTED"] = "1"  # Mark as restarted process
            env["XBOX_BACKUP_PARENT_PID"] = str(os.getpid())

            # Build command arguments safely
            if getattr(sys, "frozen", False):
                # For frozen executable
                cmd_args = [executable_path] + args
            else:
                # For Python script
                cmd_args = [executable_path] + args

            logger.info(f"Starting new process with args: {cmd_args}")

            # Start new instance with appropriate process creation flags
            creation_flags = 0
            if sys.platform == "win32":
                creation_flags = subprocess.CREATE_NEW_PROCESS_GROUP

            process = subprocess.Popen(
                cmd_args,
                env=env,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                stdin=subprocess.DEVNULL,
                creationflags=creation_flags,
                cwd=os.getcwd(),  # Explicit working directory
            )

            # Brief verification that new process started
            import time

            time.sleep(1)

            if process.poll() is not None:
                error_msg = "New application instance failed to start"
                logger.error(error_msg)
                QMessageBox.critical(None, "Restart Error", error_msg)
                return False

            logger.info(
                f"New application instance started successfully (PID: {process.pid})"
            )

            # Exit current instance gracefully
            app = QApplication.instance()
            if app:
                app.quit()
            else:
                sys.exit(0)

            return True

        except subprocess.SubprocessError as e:
            error_msg = f"Subprocess error during restart: {str(e)}"
            logger.error(error_msg)
            QMessageBox.critical(None, "Restart Error", error_msg)
            return False
        except Exception as e:
            error_msg = f"Failed to restart application: {str(e)}"
            logger.error(error_msg)
            QMessageBox.critical(None, "Restart Error", error_msg)
            return False
