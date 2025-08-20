import os
import platform
import subprocess

from PyQt6.QtWidgets import QApplication, QMessageBox


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
