from typing import List, Optional
from PyQt6.QtCore import QTimer
from PyQt6.QtWidgets import QStatusBar


class StatusManager:
    """Manages status bar messages with queuing and automatic reversion"""

    def __init__(self, status_bar: QStatusBar, parent):
        self._status_bar = status_bar
        self._parent = parent
        self._message_queue: List[tuple] = []  # (message, timeout) tuples
        self._current_timer: Optional[QTimer] = None
        self._is_showing_temp_message = False
        self._default_timeout = 5000  # 5 seconds

    def show_message(self, message: str, timeout: int = None):
        """Show a temporary message that reverts to games count after timeout"""
        if timeout is None:
            timeout = self._default_timeout

        # Add to queue
        self._message_queue.append((message, timeout))

        # Process queue if not currently showing a message
        if not self._is_showing_temp_message:
            self._process_next_message()

    def show_permanent_message(self, message: str):
        """Show a permanent message (won't auto-revert)"""
        self._clear_current_timer()
        self._status_bar.showMessage(message)
        self._is_showing_temp_message = False

    def show_games_status(self):
        """Show the default games count status"""
        # Don't show games status if currently scanning
        if hasattr(self._parent, "_is_scanning") and self._parent._is_scanning:
            return

        if hasattr(self._parent, "games") and self._parent.games:
            game_count = len(self._parent.games)
            total_size = sum(game.size_bytes for game in self._parent.games)

            # Format total size
            size_formatted = total_size
            for unit in ["B", "KB", "MB", "GB", "TB"]:
                if size_formatted < 1024.0:
                    break
                size_formatted /= 1024.0

            plural = "s" if game_count > 1 else ""
            message = f"{game_count:,} game{plural} ({size_formatted:.1f} {unit})"
            self._status_bar.showMessage(message)
        else:
            self._status_bar.showMessage("Ready")

    def _process_next_message(self):
        """Process the next message in the queue"""
        if not self._message_queue:
            return

        message, timeout = self._message_queue.pop(0)

        # Show the message
        self._status_bar.showMessage(message)
        self._is_showing_temp_message = True

        # Set up timer to revert after timeout
        self._current_timer = QTimer()
        self._current_timer.setSingleShot(True)
        self._current_timer.timeout.connect(self._on_timeout)
        self._current_timer.start(timeout)

    def _on_timeout(self):
        """Handle timeout - show next message or revert to games status"""
        self._is_showing_temp_message = False

        if self._message_queue:
            # Process next message in queue
            self._process_next_message()
        else:
            # No more messages - revert to games status
            self.show_games_status()

    def _clear_current_timer(self):
        """Clear the current timer if it exists"""
        if self._current_timer:
            self._current_timer.stop()
            self._current_timer.deleteLater()
            self._current_timer = None

    def clear_queue(self):
        """Clear all queued messages"""
        self._message_queue.clear()
        self._clear_current_timer()
        self._is_showing_temp_message = False

    def set_default_timeout(self, timeout: int):
        """Set the default timeout for messages"""
        self._default_timeout = timeout
