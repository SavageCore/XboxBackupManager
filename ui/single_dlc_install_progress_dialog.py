from PyQt6.QtWidgets import QDialog, QVBoxLayout, QLabel, QProgressBar
import time


class SingleDLCInstallProgressDialog(QDialog):
    def __init__(self, dlc_name, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Installing DLC")
        self.setModal(True)
        self.setMinimumWidth(500)

        layout = QVBoxLayout()

        # DLC name label
        self.dlc_label = QLabel(f"Installing: {dlc_name}")
        layout.addWidget(self.dlc_label)

        # Progress bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        layout.addWidget(self.progress_bar)

        # Status label (speed, time remaining, etc.)
        self.status_label = QLabel("Preparing...")
        layout.addWidget(self.status_label)

        self.setLayout(layout)

        # Speed tracking
        self.start_time = time.time()
        self.last_update_time = self.start_time
        self.last_bytes = 0
        self.speed_samples = []
        self.max_samples = 10

    def update_progress(self, current, total):
        """Update progress bar based on bytes transferred"""
        if total > 0:
            percentage = int((current / total) * 100)
            self.progress_bar.setValue(percentage)

            # Calculate speed
            current_time = time.time()
            elapsed = current_time - self.last_update_time

            if elapsed >= 0.5:  # Update speed every 0.5 seconds
                bytes_diff = current - self.last_bytes
                speed = bytes_diff / elapsed if elapsed > 0 else 0

                # Keep rolling average of speed samples
                self.speed_samples.append(speed)
                if len(self.speed_samples) > self.max_samples:
                    self.speed_samples.pop(0)

                avg_speed = sum(self.speed_samples) / len(self.speed_samples)

                # Calculate time remaining
                bytes_remaining = total - current
                if avg_speed > 0:
                    seconds_remaining = bytes_remaining / avg_speed
                    time_str = self._format_time(seconds_remaining)
                else:
                    time_str = "calculating..."

                # Update status label
                speed_str = self._format_speed(avg_speed)
                progress_str = (
                    f"{self._format_size(current)} / {self._format_size(total)}"
                )
                self.status_label.setText(
                    f"{progress_str} - {speed_str} - {time_str} remaining"
                )

                self.last_update_time = current_time
                self.last_bytes = current

    def set_status(self, message):
        """Set a custom status message"""
        self.status_label.setText(message)

    def _format_size(self, bytes_size):
        """Format bytes to human readable size"""
        for unit in ["B", "KB", "MB", "GB"]:
            if bytes_size < 1024.0:
                return f"{bytes_size:.1f} {unit}"
            bytes_size /= 1024.0
        return f"{bytes_size:.1f} TB"

    def _format_speed(self, bytes_per_sec):
        """Format speed to human readable format"""
        return f"{self._format_size(bytes_per_sec)}/s"

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
