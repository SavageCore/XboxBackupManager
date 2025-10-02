from PyQt6.QtWidgets import QDialog, QVBoxLayout, QLabel, QProgressBar, QPushButton
from PyQt6.QtCore import pyqtSignal


class BatchTUProgressDialog(QDialog):
    cancel_requested = pyqtSignal()

    def __init__(self, total_files, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Batch Title Updates Progress")
        self.setMinimumWidth(450)
        layout = QVBoxLayout()

        self.label = QLabel("Starting batch title update download...")
        layout.addWidget(self.label)

        # Overall progress bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, total_files)
        layout.addWidget(self.progress_bar)

        # Status label for current operation
        self.status_label = QLabel("Status: -")
        layout.addWidget(self.status_label)

        # Per-file progress label
        self.file_label = QLabel("Current file: -")
        layout.addWidget(self.file_label)

        # Per-file progress bar
        self.file_progress_bar = QProgressBar()
        self.file_progress_bar.setRange(0, 100)
        self.file_progress_bar.setValue(0)
        layout.addWidget(self.file_progress_bar)

        # Speed label
        self.speed_label = QLabel("Speed: -")
        layout.addWidget(self.speed_label)

        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.clicked.connect(self._on_cancel)
        layout.addWidget(self.cancel_button)

        self.setLayout(layout)
        self._cancelled = False

    def update_progress(self, current, message=None):
        self.progress_bar.setValue(current)
        if message:
            self.label.setText(message)

    def update_status(self, status_message):
        """Update the status label with current operation"""
        self.status_label.setText(f"Status: {status_message}")

    def set_file_progress_indeterminate(self):
        """Set the per-file progress bar to indeterminate mode"""
        self.file_progress_bar.setRange(0, 0)  # Indeterminate mode

    def set_file_progress_determinate(self):
        """Set the per-file progress bar back to determinate mode"""
        self.file_progress_bar.setRange(0, 100)
        self.file_progress_bar.setValue(0)

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

    def reset_file_progress(self):
        """Reset the per-file progress bar"""
        self.file_progress_bar.setValue(0)
        self.file_label.setText("Current file: -")
        self.speed_label.setText("Speed: -")

    def _on_cancel(self):
        self._cancelled = True
        self.cancel_requested.emit()
        self.label.setText("Cancelling...")
        self.cancel_button.setEnabled(False)

    def is_cancelled(self):
        return self._cancelled
