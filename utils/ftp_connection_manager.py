"""
FTP Connection Manager - Provides persistent FTP connections with keep-alive
This eliminates the need for repeated connect/disconnect cycles
"""

import threading
import time
from typing import Optional, Tuple

from PyQt6.QtCore import QObject, QTimer, pyqtSignal

from utils.ftp_client import FTPClient
from utils.settings_manager import SettingsManager


class FTPConnectionManager(QObject):
    """
    Manages a persistent FTP connection with automatic keep-alive

    Benefits:
    - Single connection reused across operations
    - Automatic NOOP keep-alive every 30 seconds
    - Thread-safe access
    - Auto-reconnection on connection loss
    """

    connection_lost = pyqtSignal(str)  # error_message
    connection_restored = pyqtSignal()

    def __init__(self):
        super().__init__()
        self.settings_manager = SettingsManager()
        self._client: Optional[FTPClient] = None
        self._lock = threading.Lock()
        self._keep_alive_timer: Optional[QTimer] = None
        self._last_activity = 0
        self._keep_alive_interval = 30000  # 30 seconds

    def get_connection(self) -> Optional[FTPClient]:
        """
        Get the current FTP connection, creating one if needed

        Returns:
            FTPClient instance if connected, None otherwise
        """
        with self._lock:
            # Check if we have a valid connection
            if self._client and self._client.is_connected():
                self._last_activity = time.time()
                return self._client

            # Need to connect/reconnect
            return self._connect()

    def _connect(self) -> Optional[FTPClient]:
        """Internal method to establish FTP connection"""
        try:
            ftp_settings = self.settings_manager.load_ftp_settings()
            ftp_host = ftp_settings.get("host")
            ftp_port = ftp_settings.get("port")
            ftp_user = ftp_settings.get("username")
            ftp_pass = ftp_settings.get("password")
            ftp_use_tls = ftp_settings.get("use_tls", False)

            if not all([ftp_host, ftp_port, ftp_user, ftp_pass]):
                print("[ERROR] FTP credentials not configured")
                return None

            self._client = FTPClient()
            success, message = self._client.connect(
                ftp_host, ftp_user, ftp_pass, int(ftp_port), ftp_use_tls
            )

            if success:
                self._start_keep_alive()
                self._last_activity = time.time()
                return self._client
            else:
                print(f"[ERROR] FTP connection failed: {message}")
                self._client = None
                return None

        except Exception as e:
            print(f"[ERROR] Failed to connect to FTP: {e}")
            self._client = None
            return None

    def _start_keep_alive(self):
        """Start the keep-alive timer"""
        if self._keep_alive_timer:
            self._keep_alive_timer.stop()

        self._keep_alive_timer = QTimer()
        self._keep_alive_timer.timeout.connect(self._send_keep_alive)
        self._keep_alive_timer.start(self._keep_alive_interval)

    def _send_keep_alive(self):
        """Send NOOP command to keep connection alive"""
        with self._lock:
            if not self._client:
                return

            # Only send NOOP if we've been idle for a while
            idle_time = time.time() - self._last_activity
            if idle_time < 25:  # Don't send if we've been active recently
                return

            try:
                if self._client.is_connected():
                    print("[DEBUG] Sending FTP keep-alive (NOOP)")
                    self._last_activity = time.time()
                else:
                    print("[WARN] FTP connection lost, attempting reconnect...")
                    self.connection_lost.emit("Connection lost")
                    if self._connect():
                        self.connection_restored.emit()
            except Exception as e:
                print(f"[ERROR] Keep-alive failed: {e}")
                self.connection_lost.emit(str(e))

    def disconnect(self):
        """Explicitly disconnect from FTP server"""
        with self._lock:
            if self._keep_alive_timer:
                self._keep_alive_timer.stop()
                self._keep_alive_timer = None

            if self._client:
                self._client.disconnect()
                self._client = None
                print("[INFO] FTP connection closed")

    def is_connected(self) -> bool:
        """Check if currently connected"""
        with self._lock:
            return self._client is not None and self._client.is_connected()

    def reconnect(self) -> Tuple[bool, str]:
        """Force reconnection"""
        with self._lock:
            if self._client:
                self._client.disconnect()
                self._client = None

            client = self._connect()
            if client:
                return True, "Reconnected successfully"
            else:
                return False, "Reconnection failed"


# Global singleton instance
_connection_manager: Optional[FTPConnectionManager] = None


def get_ftp_manager() -> FTPConnectionManager:
    """
    Get the global FTP connection manager instance

    Usage:
        from utils.ftp_connection_manager import get_ftp_manager

        manager = get_ftp_manager()
        ftp_client = manager.get_connection()
        if ftp_client:
            # Use the connection
            success, items, error = ftp_client.list_directory("/")
    """
    global _connection_manager
    if _connection_manager is None:
        _connection_manager = FTPConnectionManager()
    return _connection_manager


def cleanup_ftp_manager():
    """Cleanup the FTP connection manager (call on app exit)"""
    global _connection_manager
    if _connection_manager:
        _connection_manager.disconnect()
        _connection_manager = None
