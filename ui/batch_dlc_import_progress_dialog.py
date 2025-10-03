from PyQt6.QtWidgets import QDialog, QVBoxLayout, QLabel, QProgressBar, QPushButton
from PyQt6.QtCore import pyqtSignal
import time


class BatchDLCImportProgressDialog(QDialog):
    cancel_requested = pyqtSignal()

    def __init__(self, total_files, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Batch DLC Import Progress")
        self.setMinimumWidth(450)
        layout = QVBoxLayout()

        self.label = QLabel("Starting batch DLC import...")
        layout.addWidget(self.label)

        # Overall progress bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, total_files)
        layout.addWidget(self.progress_bar)

        # Per-file progress label
        self.file_label = QLabel("Current file: -")
        layout.addWidget(self.file_label)

        # Per-file progress bar
        self.file_progress_bar = QProgressBar()
        self.file_progress_bar.setRange(0, 100)
        self.file_progress_bar.setValue(0)
        layout.addWidget(self.file_progress_bar)

        # Speed and time remaining label
        self.speed_label = QLabel("Speed: - | Time remaining: -")
        layout.addWidget(self.speed_label)

        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.clicked.connect(self._on_cancel)
        layout.addWidget(self.cancel_button)

        self.setLayout(layout)
        self._cancelled = False

        # Speed tracking
        self.start_time = time.time()
        self.last_update_time = self.start_time
        self.last_bytes = 0
        self.speed_samples = []
        self.max_samples = 10
        self.current_file_size = 0

    def update_progress(self, current, message=None):
        self.progress_bar.setValue(current)
        if message:
            self.label.setText(message)

    def update_file_progress(self, filename, progress):
        """Update the per-file progress bar"""
        self.file_label.setText(f"Current file: {filename}")
        self.file_progress_bar.setValue(progress)

    def update_speed(self, speed_bps):
        """Update the transfer speed display"""
        if speed_bps >= 1024 * 1024:  # MB/s
            speed_text = f"{speed_bps / (1024 * 1024):.2f} MB/s"
        elif speed_bps >= 1024:  # KB/s
            speed_text = f"{speed_bps / 1024:.2f} KB/s"
        else:  # B/s
            speed_text = f"{speed_bps:.0f} B/s"
        self.speed_label.setText(f"Speed: {speed_text}")

    def update_progress_with_speed(self, current_bytes, total_bytes):
        """Update progress bar and calculate speed with time remaining"""
        if total_bytes > 0:
            percentage = int((current_bytes / total_bytes) * 100)
            self.file_progress_bar.setValue(percentage)

            # Calculate speed
            current_time = time.time()
            elapsed = current_time - self.last_update_time

            if elapsed >= 0.5:  # Update speed every 0.5 seconds
                bytes_diff = current_bytes - self.last_bytes
                speed = bytes_diff / elapsed if elapsed > 0 else 0

                # Keep rolling average of speed samples
                self.speed_samples.append(speed)
                if len(self.speed_samples) > self.max_samples:
                    self.speed_samples.pop(0)

                avg_speed = sum(self.speed_samples) / len(self.speed_samples)

                # Calculate time remaining
                bytes_remaining = total_bytes - current_bytes
                if avg_speed > 0:
                    seconds_remaining = bytes_remaining / avg_speed
                    time_str = self._format_time(seconds_remaining)
                else:
                    time_str = "calculating..."

                # Update status label
                speed_str = self._format_speed(avg_speed)
                self.speed_label.setText(
                    f"Speed: {speed_str} | Time remaining: {time_str}"
                )

                self.last_update_time = current_time
                self.last_bytes = current_bytes

    def reset_file_progress(self):
        """Reset the per-file progress bar"""
        self.file_progress_bar.setValue(0)
        self.file_label.setText("Current file: -")
        self.speed_label.setText("Speed: - | Time remaining: -")
        # Reset speed tracking for next file
        self.start_time = time.time()
        self.last_update_time = self.start_time
        self.last_bytes = 0
        self.speed_samples = []

    def _format_speed(self, bytes_per_sec):
        """Format speed to human readable format"""
        return self._format_size(bytes_per_sec) + "/s"

    def _format_size(self, bytes_size):
        """Format bytes to human readable size"""
        for unit in ["B", "KB", "MB", "GB"]:
            if bytes_size < 1024.0:
                return f"{bytes_size:.1f} {unit}"
            bytes_size /= 1024.0
        return f"{bytes_size:.1f} TB"

    def _format_time(self, seconds):
        """Format seconds to human readable time"""
        if seconds < 60:
            return f"{int(seconds)}s"
        elif seconds < 3600:
            minutes = int(seconds / 60)
            secs = int(seconds % 60)
            return f"{minutes}m {secs}s"
        else:
            hours = int(seconds / 3600)
            minutes = int((seconds % 3600) / 60)
            return f"{hours}h {minutes}m"

    def _on_cancel(self):
        self._cancelled = True
        self.cancel_requested.emit()
        self.label.setText("Cancelling...")
        self.cancel_button.setEnabled(False)

    def is_cancelled(self):
        return self._cancelled
