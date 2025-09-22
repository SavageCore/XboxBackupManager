from PyQt6.QtWidgets import (
    QDialog,
    QFormLayout,
    QHBoxLayout,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
)


class DLCInfoDialog(QDialog):
    def __init__(
        self,
        title_id,
        display_name,
        description,
        game_name,
        parent=None,
    ):
        super().__init__(parent)
        self.setWindowTitle(f"DLC Info - {display_name or title_id}")
        self.setModal(True)
        self.setMinimumWidth(400)

        layout = QVBoxLayout(self)
        form = QFormLayout()

        self.display_name = QLineEdit(display_name or "")
        self.display_name.setReadOnly(True)
        form.addRow("Display Name:", self.display_name)

        self.description = QLineEdit(description or "")
        self.description.setReadOnly(True)
        form.addRow("Description:", self.description)

        self.game_name = QLineEdit(game_name or "")
        self.game_name.setReadOnly(True)
        form.addRow("Game Name:", self.game_name)

        self.title_id = QLineEdit(title_id or "")
        self.title_id.setReadOnly(True)
        form.addRow("Title ID:", self.title_id)

        layout.addLayout(form)

        button_layout = QHBoxLayout()
        self.close_button = QPushButton("Close")
        self.close_button.clicked.connect(self.accept)
        button_layout.addStretch()
        button_layout.addWidget(self.close_button)
        layout.addLayout(button_layout)

    def get_values(self):
        return {
            "display_name": self.display_name.text(),
            "title_name": self.title_name.text(),
            "title_id": self.title_id.text(),
            "profile_id": self.profile_id.text(),
            "device_id": self.device_id.text(),
            "console_id": self.console_id.text(),
        }
