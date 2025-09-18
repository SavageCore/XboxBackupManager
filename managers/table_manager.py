#!/usr/bin/env python3
"""
Table Manager - Handles the games table UI operations
"""

from typing import List

from PyQt6.QtCore import QObject, Qt, pyqtSignal
from PyQt6.QtWidgets import QCheckBox, QTableWidget, QTableWidgetItem, QHeaderView

from models.game_info import GameInfo
from utils.ui_utils import UIUtils
from widgets.icon_delegate import IconDelegate


class TableManager(QObject):
    """Manages the games table display and interactions"""

    # Signals for table events
    selection_changed = pyqtSignal()
    game_context_menu_requested = pyqtSignal(int, int, str)  # row, column, title_id

    def __init__(self, table_widget: QTableWidget, parent=None):
        super().__init__(parent)
        self.table = table_widget
        self.current_platform = "xbox360"
        self._setup_table()

    def _setup_table(self):
        """Set up table properties and styling"""
        # Set selection behavior
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableWidget.SelectionMode.MultiSelection)

        # Set context menu policy
        self.table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._on_context_menu_requested)

        # Set up initial columns for Xbox 360
        self.set_platform("xbox360")

    def set_platform(self, platform: str):
        """Set up table columns for the specified platform"""
        self.current_platform = platform

        # Clear existing content
        self.table.clear()

        # Set up columns based on platform
        if platform == "xbox":
            headers = ["", "Game", "Title ID", "Size", "Folder", "Transferred"]
            self.table.setColumnCount(6)
        elif platform == "xbla":
            headers = [
                "",
                "Game",
                "Title ID",
                "Media ID",
                "Size",
                "Folder",
                "Transferred",
            ]
            self.table.setColumnCount(7)
        else:  # xbox360
            headers = [
                "",
                "Game",
                "Title ID",
                "Media ID",
                "Size",
                "Folder",
                "Transferred",
            ]
            self.table.setColumnCount(7)

        self.table.setHorizontalHeaderLabels(headers)

        # Set up icon delegate for the first column
        self.table.setItemDelegateForColumn(0, IconDelegate())

        # Configure column properties
        self._configure_columns()

    def _configure_columns(self):
        """Configure table column properties"""
        header = self.table.horizontalHeader()

        # Checkbox column - fixed width
        self.table.setColumnWidth(0, 50)
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)

        # Game name column - stretch
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)

        # Other columns - resize to content
        for i in range(2, self.table.columnCount()):
            header.setSectionResizeMode(i, QHeaderView.ResizeMode.ResizeToContents)

    def populate_games(self, games: List[GameInfo]):
        """Populate table with game data"""
        self.table.setRowCount(len(games))

        for row, game in enumerate(games):
            self._add_game_row(row, game)

    def _add_game_row(self, row: int, game: GameInfo):
        """Add a single game row to the table"""
        # Checkbox column
        checkbox = QCheckBox()
        checkbox.stateChanged.connect(self.selection_changed.emit)
        self.table.setCellWidget(row, 0, checkbox)

        # Game name
        name_item = QTableWidgetItem(game.name)
        name_item.setFlags(name_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
        self.table.setItem(row, 1, name_item)

        # Title ID
        title_id_item = QTableWidgetItem(game.title_id)
        title_id_item.setFlags(title_id_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
        self.table.setItem(row, 2, title_id_item)

        col_index = 3

        # Media ID (for Xbox 360 and XBLA)
        if self.current_platform in ["xbox360", "xbla"]:
            media_id = getattr(game, "media_id", "") or ""
            media_id_item = QTableWidgetItem(media_id)
            media_id_item.setFlags(media_id_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.table.setItem(row, col_index, media_id_item)
            col_index += 1

        # Size
        size_text = UIUtils.format_file_size(game.size_bytes)
        size_item = QTableWidgetItem(size_text)
        size_item.setFlags(size_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
        self.table.setItem(row, col_index, size_item)
        col_index += 1

        # Folder path
        folder_item = QTableWidgetItem(game.folder_path)
        folder_item.setFlags(folder_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
        self.table.setItem(row, col_index, folder_item)
        col_index += 1

        # Transferred status
        transferred_text = "Yes" if game.is_transferred else "No"
        transferred_item = QTableWidgetItem(transferred_text)
        transferred_item.setFlags(
            transferred_item.flags() & ~Qt.ItemFlag.ItemIsEditable
        )
        self.table.setItem(row, col_index, transferred_item)

    def get_selected_title_ids(self) -> List[str]:
        """Get list of selected game title IDs"""
        selected_ids = []

        for row in range(self.table.rowCount()):
            checkbox = self.table.cellWidget(row, 0)
            if checkbox and checkbox.isChecked():
                title_id_item = self.table.item(row, 2)
                if title_id_item:
                    selected_ids.append(title_id_item.text())

        return selected_ids

    def get_selected_count(self) -> int:
        """Get count of selected games"""
        return len(self.get_selected_title_ids())

    def select_all_games(self, checked: bool):
        """Select or deselect all games"""
        for row in range(self.table.rowCount()):
            checkbox = self.table.cellWidget(row, 0)
            if checkbox:
                checkbox.setChecked(checked)

    def update_game_transferred_status(self, title_id: str, is_transferred: bool):
        """Update the transferred status for a specific game"""
        for row in range(self.table.rowCount()):
            title_id_item = self.table.item(row, 2)
            if title_id_item and title_id_item.text() == title_id:
                # Find transferred column (last column)
                transferred_col = self.table.columnCount() - 1
                transferred_item = self.table.item(row, transferred_col)
                if transferred_item:
                    transferred_item.setText("Yes" if is_transferred else "No")
                break

    def clear_table(self):
        """Clear all table content"""
        self.table.clear()
        self.table.setRowCount(0)

    def _on_context_menu_requested(self, position):
        """Handle context menu request"""
        item = self.table.itemAt(position)
        if item:
            row = item.row()
            title_id_item = self.table.item(row, 2)
            if title_id_item:
                title_id = title_id_item.text()
                global_pos = self.table.mapToGlobal(position)
                self.game_context_menu_requested.emit(
                    global_pos.x(), global_pos.y(), title_id
                )
