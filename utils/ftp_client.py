import ftplib
import socket
import ssl
from typing import List, Tuple
from utils.settings_manager import SettingsManager

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
        self._use_tls = False

    def connect(
        self,
        host: str,
        username: str,
        password: str,
        port: int = 21,
        use_tls: bool = False,
    ) -> Tuple[bool, str]:
        """Connect to FTP server"""
        try:
            if use_tls:
                # Try FTP with TLS first
                self._ftp = ftplib.FTP_TLS()
                self._ftp.ssl_version = ssl.PROTOCOL_TLS_CLIENT
                # Ignore certificate verification for simplicity
                self._ftp.check_hostname = False
                context = ssl.create_default_context()
                context.check_hostname = False
                context.verify_mode = ssl.CERT_NONE
                self._ftp.ssl_context = context
            else:
                # Fall back to regular FTP
                self._ftp = ftplib.FTP()

            self._ftp.connect(host, port, timeout=10)
            self._ftp.login(username, password)

            if use_tls and isinstance(self._ftp, ftplib.FTP_TLS):
                # Secure the data connection
                self._ftp.prot_p()

            self._host = host
            self._username = username
            self._password = password
            self._port = port
            self._connected = True
            self._use_tls = use_tls

            connection_type = "FTPS" if use_tls else "FTP"
            return True, f"Connected successfully via {connection_type}"

        except ftplib.error_perm as e:
            error_msg = str(e)
            if "503 Use AUTH first" in error_msg and not use_tls:
                return (
                    False,
                    "Server requires SSL/TLS. Please enable secure connection.",
                )
            return False, f"Authentication failed: {error_msg}"
        except socket.gaierror as e:
            return False, f"Could not resolve hostname: {str(e)}"
        except socket.timeout:
            return False, "Connection timed out"
        except ssl.SSLError as e:
            return False, f"SSL/TLS error: {str(e)}"
        except Exception as e:
            error_msg = str(e)
            if "503 Use AUTH first" in error_msg and not use_tls:
                # If we get this error with regular FTP, suggest trying TLS
                return (
                    False,
                    "Server requires SSL/TLS. Please enable secure connection and try again.",
                )
            return False, f"Connection failed: {error_msg}"

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

    def remove_directory(self, path: str) -> Tuple[bool, str]:
        """Remove directory and all its contents recursively on FTP server"""
        if not self.is_connected():
            return False, "Not connected to FTP server"

        try:
            self._remove_directory_recursive(path)
            return True, "Directory removed successfully"
        except ftplib.error_perm as e:
            return False, f"Failed to remove directory: {str(e)}"
        except Exception as e:
            return False, f"Failed to remove directory: {str(e)}"

    def _remove_directory_recursive(self, path: str):
        """Recursively remove directory and all its contents"""
        try:
            self._ftp.cwd(path)
            lines = []
            self._ftp.retrlines("LIST", lines.append)

            for line in lines:
                parts = line.split(None, 8)
                if len(parts) >= 9:
                    permissions = parts[0]
                    name = parts[8]

                    # Skip . and .. entries
                    if name in [".", ".."]:
                        continue

                    is_directory = permissions.startswith("d")
                    full_path = f"{path.rstrip('/')}/{name}"

                    if is_directory:
                        # Recursively remove subdirectory
                        self._remove_directory_recursive(full_path)
                    else:
                        # Remove file
                        self._ftp.delete(full_path)

            # Now remove the empty directory
            self._ftp.rmd(path)

        except Exception as e:
            raise Exception(f"Failed to remove {path}: {str(e)}")

    def remove_file(self, path: str) -> Tuple[bool, str]:
        """Remove a single file on FTP server"""
        if not self.is_connected():
            return False, "Not connected to FTP server"

        try:
            self._ftp.delete(path)
            return True, "File removed successfully"
        except ftplib.error_perm as e:
            return False, f"Failed to remove file: {str(e)}"
        except Exception as e:
            return False, f"Failed to remove file: {str(e)}"

    def directory_exists(self, path: str) -> bool:
        """Check if a directory exists on FTP server with timeout protection"""
        if not self.is_connected():
            return False

        try:
            # Set a shorter timeout for this operation
            old_timeout = None
            if hasattr(self._ftp, "sock") and self._ftp.sock:
                old_timeout = self._ftp.sock.gettimeout()
                self._ftp.sock.settimeout(3)  # 3 second timeout

            current_dir = self._ftp.pwd()  # Save current directory
            self._ftp.cwd(path)  # Try to change to target directory
            self._ftp.cwd(current_dir)  # Go back to original directory

            # Restore original timeout
            if (
                old_timeout is not None
                and hasattr(self._ftp, "sock")
                and self._ftp.sock
            ):
                self._ftp.sock.settimeout(old_timeout)

            return True

        except (ftplib.error_perm, socket.timeout, OSError):
            return False
        except Exception:
            return False
