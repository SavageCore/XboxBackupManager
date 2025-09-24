from PyQt6.QtWidgets import QDialog, QVBoxLayout, QLabel, QProgressBar, QPushButton
from PyQt6.QtCore import pyqtSignal


class BatchDLCImportProgressDialog(QDialog):
    cancel_requested = pyqtSignal()

    def __init__(self, total_files, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Batch DLC Import Progress")
        self.setMinimumWidth(450)
        layout = QVBoxLayout()

        self.label = QLabel("Starting batch DLC import...")
        layout.addWidget(self.label)

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, total_files)
        layout.addWidget(self.progress_bar)

        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.clicked.connect(self._on_cancel)
        layout.addWidget(self.cancel_button)

        self.setLayout(layout)
        self._cancelled = False

    def update_progress(self, current, message=None):
        self.progress_bar.setValue(current)
        if message:
            self.label.setText(message)

    def _on_cancel(self):
        self._cancelled = True
        self.cancel_requested.emit()
        self.label.setText("Cancelling...")
        self.cancel_button.setEnabled(False)

    def is_cancelled(self):
        return self._cancelled
