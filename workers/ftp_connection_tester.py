import ftplib
import socket

from PyQt6.QtCore import QThread, pyqtSignal


class FTPConnectionTester(QThread):
    """Thread to test FTP connection without blocking UI"""

    connection_result = pyqtSignal(bool, str)  # success, message

    def __init__(self, host, port=21, timeout=5):
        super().__init__()
        self.host = host
        self.port = port
        self.timeout = timeout

    def run(self):
        """Test FTP connection in background thread"""
        try:
            # Quick TCP connection test first
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(self.timeout)

            result = sock.connect_ex((self.host, self.port))
            sock.close()

            if result == 0:
                # TCP connection succeeded, try FTP greeting
                try:
                    ftp = ftplib.FTP()
                    ftp.connect(self.host, self.port, timeout=self.timeout)
                    ftp.getwelcome()
                    ftp.quit()
                    self.connection_result.emit(True, "FTP server reachable")
                except Exception as e:
                    self.connection_result.emit(
                        False, f"FTP server not responding: {str(e)}"
                    )
            else:
                self.connection_result.emit(
                    False, f"Cannot connect to {self.host}:{self.port}"
                )

        except socket.timeout:
            self.connection_result.emit(
                False, f"Connection to {self.host}:{self.port} timed out"
            )
        except socket.gaierror:
            self.connection_result.emit(False, f"Cannot resolve hostname: {self.host}")
        except Exception as e:
            self.connection_result.emit(False, f"Connection error: {str(e)}")
