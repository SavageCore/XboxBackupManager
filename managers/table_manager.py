#!/usr/bin/env python3
"""
Table Manager - Handles the games table UI operations
"""

from typing import List

from PyQt6.QtCore import QObject, Qt, pyqtSignal
from PyQt6.QtGui import QIcon, QPixmap
from PyQt6.QtWidgets import QHeaderView, QTableWidget, QTableWidgetItem

from managers.game_manager import GameManager
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

        # Don't clear existing data, just set up column structure
        # Store existing data if we have any
        existing_data = []
        if self.table.rowCount() > 0:
            # Extract existing data to preserve it
            for row in range(self.table.rowCount()):
                row_data = []
                for col in range(self.table.columnCount()):
                    item = self.table.item(row, col)
                    row_data.append(item.text() if item else "")
                existing_data.append(row_data)

        # Set up columns based on platform
        if platform == "xbox":
            headers = [
                "",
                "Icon",
                "Title ID",
                "Game Name",
                "Size",
                "Transferred",
                "Source Path",
            ]
            self.table.setColumnCount(7)
        elif platform == "xbla":
            headers = [
                "",
                "Icon",
                "Title ID",
                "Game Name",
                "Media ID",
                "Size",
                "DLCs",
                "Transferred",
                "Source Path",
            ]
            self.table.setColumnCount(9)
        else:  # xbox360
            headers = [
                "",
                "Icon",
                "Title ID",
                "Game Name",
                "Media ID",
                "Size",
                "Transferred",
                "Source Path",
            ]
            self.table.setColumnCount(8)

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

        # Icon column - fixed width for proper icon display
        self.table.setColumnWidth(1, 70)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Fixed)

        # Set row height to accommodate larger icons
        self.table.verticalHeader().setDefaultSectionSize(70)

        # Title ID column - fixed width
        self.table.setColumnWidth(2, 120)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Fixed)

        # Game name column - stretch (column 3)
        self.table.setColumnWidth(3, 300)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.Fixed)

        # Platform-specific column widths
        if self.current_platform in ["xbox360", "xbla"]:
            # Media ID column
            self.table.setColumnWidth(4, 100)
            header.setSectionResizeMode(4, QHeaderView.ResizeMode.Fixed)

            # Size column
            self.table.setColumnWidth(5, 80)
            header.setSectionResizeMode(5, QHeaderView.ResizeMode.Fixed)

            if self.current_platform == "xbla":
                # DLCs column
                self.table.setColumnWidth(6, 70)
                header.setSectionResizeMode(6, QHeaderView.ResizeMode.Fixed)

                # Transferred column
                self.table.setColumnWidth(7, 120)
                header.setSectionResizeMode(7, QHeaderView.ResizeMode.Fixed)

                # Source path - stretch
                header.setSectionResizeMode(8, QHeaderView.ResizeMode.Stretch)
            else:  # xbox360
                # Transferred column
                self.table.setColumnWidth(6, 120)
                header.setSectionResizeMode(6, QHeaderView.ResizeMode.Fixed)

                # Source path - stretch
                header.setSectionResizeMode(7, QHeaderView.ResizeMode.Stretch)
        else:  # xbox
            # Size column
            self.table.setColumnWidth(4, 80)
            header.setSectionResizeMode(4, QHeaderView.ResizeMode.Fixed)

            # Transferred column
            self.table.setColumnWidth(5, 120)
            header.setSectionResizeMode(5, QHeaderView.ResizeMode.Fixed)

            # Source path - stretch
            header.setSectionResizeMode(6, QHeaderView.ResizeMode.Stretch)

    def populate_games(self, games: List[GameInfo]):
        """Populate table with game data, preserving existing entries"""
        # Get existing title IDs to avoid duplicates
        existing_title_ids = set()
        for row in range(self.table.rowCount()):
            title_id_item = self.table.item(row, 2)  # Title ID is always column 2
            if title_id_item:  # Ensure item exists
                existing_title_ids.add(title_id_item.text())

        # Add only new games
        for game in games:
            if game.title_id not in existing_title_ids:
                row = self.table.rowCount()
                self.table.insertRow(row)
                self._add_game_row(row, game)

    def refresh_games(self, games: List[GameInfo]):
        """Completely refresh table with new games"""
        self.table.setRowCount(0)
        self.populate_games(games)

    def clear_games(self):
        """Clear all games from table"""
        self.table.setRowCount(0)

    def _add_game_row(self, row: int, game: GameInfo):
        """Add a single game row to the table"""
        col_index = 0

        # Select checkbox column - properly centered
        checkbox_item = QTableWidgetItem("")  # Empty text is important
        checkbox_item.setFlags(checkbox_item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
        checkbox_item.setCheckState(Qt.CheckState.Unchecked)
        checkbox_item.setFlags(checkbox_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
        # Center the checkbox both horizontally and vertically
        checkbox_item.setTextAlignment(
            Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter
        )
        # Ensure no text content interferes with checkbox positioning
        checkbox_item.setText("")
        checkbox_item.setData(Qt.ItemDataRole.DisplayRole, "")
        self.table.setItem(row, col_index, checkbox_item)
        col_index += 1

        # Icon column - with proper icon handling
        icon_item = QTableWidgetItem("")
        icon_item.setFlags(icon_item.flags() & ~Qt.ItemFlag.ItemIsEditable)

        # Try to load and scale icon if available
        # They're in cache/icons/<title_id>.png
        icon_path = GameManager.get_icon_path(self, game.title_id)
        if icon_path:
            try:
                pixmap = QPixmap(icon_path)
                if not pixmap.isNull():
                    # Scale to 64x64 for better visibility
                    scaled_pixmap = pixmap.scaled(
                        64,
                        64,
                        Qt.AspectRatioMode.KeepAspectRatio,
                        Qt.TransformationMode.SmoothTransformation,
                    )
                    icon_item.setIcon(QIcon(scaled_pixmap))
            except Exception as e:
                print(f"Failed to load icon for {game.title_id}: {e}")
                # If icon loading fails, just leave it empty
                pass

        self.table.setItem(row, col_index, icon_item)
        col_index += 1

        # Title ID column
        title_id_item = QTableWidgetItem(game.title_id)
        title_id_item.setData(Qt.ItemDataRole.UserRole, game.title_id)
        title_id_item.setFlags(title_id_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
        self.table.setItem(row, col_index, title_id_item)
        col_index += 1

        # Game Name column
        name_item = QTableWidgetItem(game.name)
        name_item.setData(Qt.ItemDataRole.UserRole, game.name)
        name_item.setFlags(name_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
        self.table.setItem(row, col_index, name_item)
        col_index += 1

        # Media ID column (for Xbox 360 and XBLA)
        if self.current_platform in ["xbox360", "xbla"]:
            media_id_text = getattr(game, "media_id", "") or ""
            media_id_item = QTableWidgetItem(media_id_text)
            media_id_item.setData(Qt.ItemDataRole.UserRole, media_id_text)
            media_id_item.setFlags(media_id_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.table.setItem(row, col_index, media_id_item)
            col_index += 1

        # Size column
        size_text = UIUtils.format_file_size(game.size_bytes)
        size_item = QTableWidgetItem(size_text)
        size_item.setData(
            Qt.ItemDataRole.UserRole, game.size_bytes
        )  # Store raw bytes for sorting
        size_item.setFlags(size_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
        self.table.setItem(row, col_index, size_item)
        col_index += 1

        # DLCs column (XBLA only)
        if self.current_platform == "xbla":
            # This would need to be implemented based on folder structure
            dlc_item = QTableWidgetItem(str(game.dlc_count) or "0")  # Placeholder
            dlc_item.setData(Qt.ItemDataRole.UserRole, game.dlc_count or 0)
            dlc_item.setFlags(dlc_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            dlc_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.table.setItem(row, col_index, dlc_item)
            col_index += 1

        # Transferred status column - centered with emoji
        status_text = "✔️" if game.transferred else "❌"
        transferred_item = QTableWidgetItem(status_text)
        transferred_item.setData(Qt.ItemDataRole.UserRole, game.transferred)
        transferred_item.setFlags(
            transferred_item.flags() & ~Qt.ItemFlag.ItemIsEditable
        )
        transferred_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        self.table.setItem(row, col_index, transferred_item)
        col_index += 1

        # Source Path column (always last)
        path_item = QTableWidgetItem(game.folder_path)
        path_item.setData(Qt.ItemDataRole.UserRole, game.folder_path)
        path_item.setFlags(path_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
        self.table.setItem(row, col_index, path_item)

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
