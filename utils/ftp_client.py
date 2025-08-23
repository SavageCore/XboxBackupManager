import ftplib
import socket
from typing import List, Tuple

from PyQt6.QtCore import QObject


class FTPClient(QObject):
    """FTP client for connecting and managing FTP operations"""

    def __init__(self):
        super().__init__()
        self._ftp = None
        self._host = ""
        self._username = ""
        self._password = ""
        self._port = 21
        self._connected = False

    def connect(
        self, host: str, username: str, password: str, port: int = 21
    ) -> Tuple[bool, str]:
        """Connect to FTP server"""
        try:
            self._ftp = ftplib.FTP()
            self._ftp.connect(host, port, timeout=10)
            self._ftp.login(username, password)

            self._host = host
            self._username = username
            self._password = password
            self._port = port
            self._connected = True

            return True, "Connected successfully"

        except ftplib.error_perm as e:
            return False, f"Authentication failed: {str(e)}"
        except socket.gaierror as e:
            return False, f"Could not resolve hostname: {str(e)}"
        except socket.timeout:
            return False, "Connection timed out"
        except Exception as e:
            return False, f"Connection failed: {str(e)}"

    def disconnect(self):
        """Disconnect from FTP server"""
        if self._ftp:
            try:
                self._ftp.quit()
            except Exception:
                try:
                    self._ftp.close()
                except Exception:
                    pass
            finally:
                self._ftp = None
                self._connected = False

    def is_connected(self) -> bool:
        """Check if connected to FTP server"""
        if not self._connected or not self._ftp:
            return False

        try:
            # Send NOOP to test connection
            self._ftp.voidcmd("NOOP")
            return True
        except Exception:
            self._connected = False
            return False

    def list_directory(self, path: str = "/") -> Tuple[bool, List[dict], str]:
        """List directory contents"""
        if not self.is_connected():
            return False, [], "Not connected to FTP server"

        try:
            items = []

            # Change to directory
            self._ftp.cwd(path)

            # Get directory listing with details
            lines = []
            self._ftp.retrlines("LIST", lines.append)

            for line in lines:
                # Parse LIST format (Unix-style)
                parts = line.split(None, 8)
                if len(parts) >= 9:
                    permissions = parts[0]
                    name = parts[8]

                    # Skip . and .. entries
                    if name in [".", ".."]:
                        continue

                    is_directory = permissions.startswith("d")

                    items.append(
                        {
                            "name": name,
                            "is_directory": is_directory,
                            "permissions": permissions,
                            "full_path": f"{path.rstrip('/')}/{name}",
                        }
                    )

            return True, items, ""

        except ftplib.error_perm as e:
            return False, [], f"Permission denied: {str(e)}"
        except Exception as e:
            return False, [], f"Failed to list directory: {str(e)}"

    def create_directory(self, path: str) -> Tuple[bool, str]:
        """Create directory on FTP server"""
        if not self.is_connected():
            return False, "Not connected to FTP server"

        try:
            self._ftp.mkd(path)
            return True, "Directory created successfully"
        except ftplib.error_perm as e:
            if "exists" in str(e).lower():
                return True, "Directory already exists"
            return False, f"Failed to create directory: {str(e)}"
        except Exception as e:
            return False, f"Failed to create directory: {str(e)}"

    def get_current_directory(self) -> str:
        """Get current working directory"""
        if not self.is_connected():
            return "/"

        try:
            return self._ftp.pwd()
        except Exception:
            return "/"
