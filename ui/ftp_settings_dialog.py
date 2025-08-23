from PyQt6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
)

from utils.ftp_client import FTPClient


class FTPSettingsDialog(QDialog):
    """Dialog for configuring FTP connection settings"""

    def __init__(self, parent=None, current_settings=None):
        super().__init__(parent)
        self._ftp_client = FTPClient()
        self._current_settings = current_settings or {}
        self._init_ui()
        self._load_settings()

    def _init_ui(self):
        """Initialize the dialog UI"""
        self.setWindowTitle("FTP Connection Settings")
        self.setModal(True)
        self.setMinimumWidth(400)

        layout = QVBoxLayout(self)

        # Connection settings group
        connection_group = QGroupBox("Connection Settings")
        connection_layout = QFormLayout(connection_group)

        self.host_input = QLineEdit()
        self.host_input.setPlaceholderText("e.g., 192.168.1.100 or xbox.local")
        connection_layout.addRow("Host/IP:", self.host_input)

        self.port_input = QSpinBox()
        self.port_input.setRange(1, 65535)
        self.port_input.setValue(21)
        connection_layout.addRow("Port:", self.port_input)

        self.username_input = QLineEdit()
        self.username_input.setPlaceholderText("FTP username")
        connection_layout.addRow("Username:", self.username_input)

        self.password_input = QLineEdit()
        self.password_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.password_input.setPlaceholderText("FTP password")
        connection_layout.addRow("Password:", self.password_input)

        self.use_tls_checkbox = QCheckBox("Use SSL/TLS (FTPS)")
        self.use_tls_checkbox.setChecked(True)  # Default to secure connection
        self.use_tls_checkbox.setToolTip(
            "Enable for secure encrypted connections (recommended)"
        )
        connection_layout.addRow("Security:", self.use_tls_checkbox)

        layout.addWidget(connection_group)

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
        self.host_input.setText(self._current_settings.get("host", ""))
        self.port_input.setValue(self._current_settings.get("port", 21))
        self.username_input.setText(self._current_settings.get("username", ""))
        self.password_input.setText(self._current_settings.get("password", ""))
        self.use_tls_checkbox.setChecked(self._current_settings.get("use_tls", True))

    def _test_connection(self):
        """Test the FTP connection with current settings"""
        host = self.host_input.text().strip()
        port = self.port_input.value()
        username = self.username_input.text().strip()
        password = self.password_input.text()
        use_tls = self.use_tls_checkbox.isChecked()

        if not host or not username:
            QMessageBox.warning(
                self, "Invalid Input", "Please enter host and username."
            )
            return

        self.test_button.setEnabled(False)
        self.test_button.setText("Testing...")

        # Use the fallback connection method for better user experience
        success, message = self._ftp_client.connect(
            host, username, password, port, use_tls
        )

        if success:
            self._ftp_client.disconnect()
            QMessageBox.information(
                self, "Connection Test", f"Connection successful!\n\n{message}"
            )
        else:
            QMessageBox.critical(
                self, "Connection Test", f"Connection failed:\n{message}"
            )

        self.test_button.setEnabled(True)
        self.test_button.setText("Test Connection")

    def get_settings(self):
        """Get the FTP settings from the dialog"""
        return {
            "host": self.host_input.text().strip(),
            "port": self.port_input.value(),
            "username": self.username_input.text().strip(),
            "password": self.password_input.text(),
            "use_tls": self.use_tls_checkbox.isChecked(),
        }
