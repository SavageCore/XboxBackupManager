from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
)

from utils.ftp_client import FTPClient


class FTPBrowserDialog(QDialog):
    """Dialog for browsing FTP server directories"""

    def __init__(self, parent=None, ftp_settings=None):
        super().__init__(parent)
        self._ftp_client = FTPClient()
        self._ftp_settings = ftp_settings or {}
        self._selected_path = "/"
        self._init_ui()
        self._connect_to_ftp()

    def _init_ui(self):
        """Initialize the dialog UI"""
        self.setWindowTitle("Browse FTP Directory")
        self.setModal(True)
        self.setMinimumSize(500, 400)

        layout = QVBoxLayout(self)

        # Current path display
        path_layout = QHBoxLayout()
        path_layout.addWidget(QLabel("Current Path:"))
        self.path_label = QLineEdit()
        self.path_label.setReadOnly(True)
        self.path_label.setText("/")
        path_layout.addWidget(self.path_label)
        layout.addLayout(path_layout)

        # Directory tree
        self.tree_widget = QTreeWidget()
        self.tree_widget.setHeaderLabels(["Name", "Type"])
        self.tree_widget.itemDoubleClicked.connect(self._on_item_double_clicked)
        layout.addWidget(self.tree_widget)

        # Buttons
        button_layout = QHBoxLayout()

        self.refresh_button = QPushButton("Refresh")
        self.refresh_button.clicked.connect(self._refresh_directory)
        button_layout.addWidget(self.refresh_button)

        self.create_folder_button = QPushButton("Create Folder")
        self.create_folder_button.clicked.connect(self._create_folder)
        button_layout.addWidget(self.create_folder_button)

        button_layout.addStretch()
        layout.addLayout(button_layout)

        # Dialog buttons
        button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

    def _connect_to_ftp(self):
        """Connect to FTP server using provided settings"""
        if not self._ftp_settings:
            QMessageBox.critical(self, "Error", "No FTP settings provided.")
            self.reject()
            return

        success, message = self._ftp_client.connect(
            self._ftp_settings["host"],
            self._ftp_settings["username"],
            self._ftp_settings["password"],
            self._ftp_settings.get("port", 21),
        )

        if not success:
            QMessageBox.critical(
                self, "FTP Connection Error", f"Failed to connect:\n{message}"
            )
            self.reject()
            return

        self._load_directory("/")

    def _load_directory(self, path):
        """Load directory contents"""
        self.tree_widget.clear()

        success, items, error = self._ftp_client.list_directory(path)

        if not success:
            QMessageBox.warning(self, "Error", f"Failed to load directory:\n{error}")
            return

        self._selected_path = path
        self.path_label.setText(path)

        # Add parent directory item if not at root
        if path != "/":
            parent_item = QTreeWidgetItem([".. (Parent Directory)", "Directory"])
            parent_item.setData(
                0,
                Qt.ItemDataRole.UserRole,
                {"path": self._get_parent_path(path), "is_directory": True},
            )
            self.tree_widget.addTopLevelItem(parent_item)

        # Add directory items
        for item in items:
            if item["is_directory"]:
                tree_item = QTreeWidgetItem([item["name"], "Directory"])
                tree_item.setData(0, Qt.ItemDataRole.UserRole, item)
                self.tree_widget.addTopLevelItem(tree_item)

        # Add file items
        for item in items:
            if not item["is_directory"]:
                tree_item = QTreeWidgetItem([item["name"], "File"])
                tree_item.setData(0, Qt.ItemDataRole.UserRole, item)
                self.tree_widget.addTopLevelItem(tree_item)

    def _get_parent_path(self, path):
        """Get parent directory path"""
        if path == "/":
            return "/"
        return "/".join(path.rstrip("/").split("/")[:-1]) or "/"

    def _on_item_double_clicked(self, item, column):
        """Handle double-click on tree item"""
        data = item.data(0, Qt.ItemDataRole.UserRole)
        if data and data.get("is_directory"):
            if item.text(0) == ".. (Parent Directory)":
                new_path = data["path"]
            else:
                current_path = self._selected_path.rstrip("/")
                new_path = (
                    f"{current_path}/{data['name']}"
                    if current_path != "/"
                    else f"/{data['name']}"
                )

            self._load_directory(new_path)

    def _refresh_directory(self):
        """Refresh current directory"""
        self._load_directory(self._selected_path)

    def _create_folder(self):
        """Create new folder dialog"""
        from PyQt6.QtWidgets import QInputDialog

        folder_name, ok = QInputDialog.getText(
            self, "Create Folder", "Enter folder name:"
        )

        if ok and folder_name:
            current_path = self._selected_path.rstrip("/")
            new_folder_path = (
                f"{current_path}/{folder_name}"
                if current_path != "/"
                else f"/{folder_name}"
            )

            success, message = self._ftp_client.create_directory(new_folder_path)

            if success:
                self._refresh_directory()
            else:
                QMessageBox.warning(
                    self, "Error", f"Failed to create folder:\n{message}"
                )

    def get_selected_path(self):
        """Get the selected directory path"""
        return self._selected_path

    def closeEvent(self, event):
        """Handle dialog close"""
        self._ftp_client.disconnect()
        super().closeEvent(event)
