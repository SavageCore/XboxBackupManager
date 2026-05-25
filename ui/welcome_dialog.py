import os

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QDialog,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from constants import APP_NAME, VERSION
from utils.system_utils import SystemUtils


class WelcomeDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"Welcome to {APP_NAME}")
        self.setModal(True)
        self.setMinimumWidth(620)
        self.setMinimumHeight(520)
        self.setWindowFlag(Qt.WindowType.WindowContextHelpButtonHint, False)
        self._dir_fields: dict[str, QLineEdit] = {}
        self._init_ui()

    def _init_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(20, 20, 20, 20)
        outer.setSpacing(12)

        title = QLabel(f"Welcome to {APP_NAME} v{VERSION}")
        font = title.font()
        font.setPointSize(font.pointSize() + 4)
        font.setBold(True)
        title.setFont(font)
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        outer.addWidget(title)

        intro = QLabel(
            "Xbox Backup Manager helps you organise and transfer game backups, "
            "Title Updates, and DLC for Xbox 360.\n\n"
            "Set up your directories below. You can change them "
            "at any time from the File menu."
        )
        intro.setWordWrap(True)
        outer.addWidget(intro)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)

        scroll_content = QWidget()
        scroll_layout = QVBoxLayout(scroll_content)
        scroll_layout.setSpacing(12)
        scroll_layout.setContentsMargins(0, 0, 4, 0)

        source_entries = [
            (
                "xbox",
                "Original Xbox Game Directory",
                "Source folder for original Xbox game files.",
            ),
            (
                "xbox360",
                "Xbox 360 Game Directory",
                "Source folder for Xbox 360 Game on Demand (GoD) files.",
            ),
            (
                "xbla",
                "XBLA Game Directory",
                "Source folder for Xbox Live Arcade (XBLA) game files.",
            ),
            (
                "dlc",
                "DLC Directory",
                "Source folder for downloadable content (DLC) files.",
            ),
        ]

        usb_entries = [
            (
                "usb_cache",
                "USB Cache Directory",
                "Temporary cache folder on your USB drive used to stage files during "
                "transfer (e.g. E:\\Cache).",
            ),
            (
                "usb_content",
                "USB Content Directory",
                "Content folder on your USB drive where DLC and Title Updates are "
                "installed in Xbox 360 format "
                "(e.g. E:\\Content\\0000000000000000).",
            ),
            (
                "usb_xbox",
                "USB Target — Original Xbox",
                "Target folder for original Xbox games (e.g. E:\\OG Xbox).",
            ),
            (
                "usb_xbox360",
                "USB Target — Xbox 360",
                "Target folder for Xbox 360 GoD files (e.g. /Hdd1/Games).",
            ),
            (
                "usb_xbla",
                "USB Target — XBLA",
                "Target folder for XBLA games (e.g. /Hdd1/Content/0000000000000000).",
            ),
        ]

        scroll_layout.addWidget(self._make_group("Source Directories", source_entries))
        scroll_layout.addWidget(
            self._make_group("USB / Transfer Directories", usb_entries)
        )
        scroll_layout.addStretch()

        scroll.setWidget(scroll_content)
        outer.addWidget(scroll, stretch=1)

        btn = QPushButton("Get Started")
        btn.setDefault(True)
        btn.clicked.connect(self.accept)
        outer.addWidget(btn, alignment=Qt.AlignmentFlag.AlignCenter)

    def _make_group(self, title: str, entries: list) -> QGroupBox:
        group = QGroupBox(title)
        layout = QVBoxLayout(group)
        layout.setSpacing(10)
        for key, label, description in entries:
            layout.addWidget(self._make_entry(key, label, description))
        return group

    def _make_entry(self, key: str, label: str, description: str) -> QWidget:
        widget = QWidget()
        vbox = QVBoxLayout(widget)
        vbox.setContentsMargins(0, 0, 0, 0)
        vbox.setSpacing(2)

        lbl = QLabel(label)
        lbl_font = lbl.font()
        lbl_font.setBold(True)
        lbl.setFont(lbl_font)
        vbox.addWidget(lbl)

        desc = QLabel(description)
        desc.setWordWrap(True)
        desc_font = desc.font()
        desc_font.setPointSize(max(desc_font.pointSize() - 1, 7))
        desc.setFont(desc_font)
        vbox.addWidget(desc)

        row = QHBoxLayout()
        field = QLineEdit()
        field.setPlaceholderText("Not set — click Browse to choose a folder")
        field.setReadOnly(True)
        browse_btn = QPushButton("Browse…")
        # browse_btn.setFixedWidth(90)
        browse_btn.clicked.connect(lambda checked, f=field: self._browse(f))
        row.addWidget(field)
        row.addWidget(browse_btn)
        vbox.addLayout(row)

        self._dir_fields[key] = field
        return widget

    def _browse(self, field: QLineEdit):
        directory = SystemUtils.browse_for_directory(
            self,
            "Select Directory",
            field.text() or os.path.expanduser("~"),
        )
        if directory:
            field.setText(directory)

    def get_directories(self) -> dict:
        return {key: field.text() for key, field in self._dir_fields.items()}
