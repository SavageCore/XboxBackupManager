from PyQt6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
)

from utils.ftp_client import FTPClient
from utils.xboxunity import XboxUnity


class XboxUnitySettingsDialog(QDialog):
    """Dialog for configuring Xbox Unity settings"""

    def __init__(self, parent=None, current_settings=None):
        super().__init__(parent)
        self._ftp_client = FTPClient()
        self._xbox_unity = XboxUnity()
        self._current_settings = current_settings or {}
        self._init_ui()
        self._load_settings()

    def _init_ui(self):
        """Initialize the dialog UI"""
        self.setWindowTitle("Xbox Unity Settings")
        self.setModal(True)
        self.setMinimumWidth(400)

        layout = QVBoxLayout(self)

        # Login settings group
        login_group = QGroupBox("Login Settings")
        login_layout = QFormLayout(login_group)

        self.username_input = QLineEdit()
        self.username_input.setPlaceholderText("Xbox Unity username")
        login_layout.addRow("Username:", self.username_input)

        self.password_input = QLineEdit()
        self.password_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.password_input.setPlaceholderText("Xbox Unity password")
        login_layout.addRow("Password:", self.password_input)

        self.api_key_input = QLineEdit()
        self.api_key_input.setPlaceholderText("Xbox Unity API Key")
        login_layout.addRow("API Key:", self.api_key_input)

        layout.addWidget(login_group)

        # Test connection button
        test_layout = QHBoxLayout()
        self.test_button = QPushButton("Test Connection")
        self.test_button.clicked.connect(self._test_connection)
        test_layout.addStretch()
        test_layout.addWidget(self.test_button)
        layout.addLayout(test_layout)

        # Dialog buttons
        button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

    def _load_settings(self):
        """Load current settings into the form"""
        self.username_input.setText(self._current_settings.get("username", ""))
        self.password_input.setText(self._current_settings.get("password", ""))
        self.api_key_input.setText(self._current_settings.get("api_key", ""))

    def _test_connection(self):
        """Test the Xbox Unity connection with current settings"""
        username = self.username_input.text().strip()
        password = self.password_input.text()
        api_key = self.api_key_input.text().strip()
        if not ((username and password) or api_key):
            QMessageBox.warning(
                self, "Invalid Input", "Please enter username and password, or API key."
            )
            return

        self.test_button.setEnabled(False)
        self.test_button.setText("Testing...")

        # Test connection in the main thread (it's quick)
        success, message = self._xbox_unity.test_connectivity()

        if success:
            QMessageBox.information(self, "Connection Test", "Connection successful!")
        else:
            QMessageBox.critical(
                self, "Connection Test", f"Connection failed:\n{message}"
            )

        self.test_button.setEnabled(True)
        self.test_button.setText("Test Connection")

    def get_settings(self):
        """Get the Xbox Unity settings from the dialog"""
        return {
            "username": self.username_input.text().strip(),
            "password": self.password_input.text(),
            "api_key": self.api_key_input.text().strip(),
        }
