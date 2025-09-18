#!/usr/bin/env python3
"""
Refactored Main Window - Example showing how to use the new manager classes
This demonstrates the architectural improvements possible with the manager pattern
"""

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QMainWindow, QVBoxLayout, QWidget, QTableWidget

from managers.directory_manager import DirectoryManager
from managers.game_manager import GameManager
from managers.table_manager import TableManager
from managers.transfer_manager import TransferManager
from utils.settings_manager import SettingsManager
from utils.status_manager import StatusManager
from utils.ui_utils import UIUtils


class RefactoredMainWindow(QMainWindow):
    """
    Refactored main window using manager pattern
    This is MUCH cleaner and follows Single Responsibility Principle
    """

    def __init__(self):
        super().__init__()

        # Initialize managers
        self.settings_manager = SettingsManager()
        self.status_manager = StatusManager(self)
        self.directory_manager = DirectoryManager(self)
        self.game_manager = GameManager(self)
        self.transfer_manager = TransferManager(self)

        # Current state
        self.current_platform = "xbox360"
        self.current_mode = "usb"

        self.setup_ui()
        self.connect_signals()
        self.load_settings()

    def setup_ui(self):
        """Set up the user interface"""
        self.setWindowTitle("Xbox Backup Manager - Refactored")
        self.setGeometry(100, 100, 1200, 800)

        # Create main widget and layout
        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        layout = QVBoxLayout(main_widget)

        # Create games table
        self.games_table = QTableWidget()
        layout.addWidget(self.games_table)

        # Initialize table manager
        self.table_manager = TableManager(self.games_table, self)

        # Add other UI components here...
        # (toolbar, menus, progress bars, etc.)

    def connect_signals(self):
        """Connect manager signals to UI handlers"""

        # Directory manager signals
        self.directory_manager.directory_changed.connect(self.on_directory_changed)
        self.directory_manager.directory_files_changed.connect(
            self.on_directory_files_changed
        )

        # Game manager signals
        self.game_manager.scan_started.connect(self.on_scan_started)
        self.game_manager.scan_progress.connect(self.on_scan_progress)
        self.game_manager.scan_complete.connect(self.on_scan_complete)
        self.game_manager.scan_error.connect(self.on_scan_error)

        # Transfer manager signals
        self.transfer_manager.transfer_started.connect(self.on_transfer_started)
        self.transfer_manager.transfer_progress.connect(self.on_transfer_progress)
        self.transfer_manager.game_transferred.connect(self.on_game_transferred)
        self.transfer_manager.transfer_complete.connect(self.on_transfer_complete)
        self.transfer_manager.transfer_error.connect(self.on_transfer_error)

        # Table manager signals
        self.table_manager.selection_changed.connect(self.on_selection_changed)
        self.table_manager.game_context_menu_requested.connect(
            self.on_context_menu_requested
        )

    def load_settings(self):
        """Load application settings"""
        self.directory_manager.load_directories_from_settings(self.settings_manager)
        # Load other settings...

    # Event handlers - much cleaner and focused!

    def on_directory_changed(self, directory: str):
        """Handle directory change"""
        self.status_manager.show_message(f"Directory changed: {directory}")
        self.start_scan()

    def on_directory_files_changed(self):
        """Handle directory files change"""
        self.start_scan()

    def on_scan_started(self):
        """Handle scan start"""
        self.status_manager.show_message("Scanning directory...")

    def on_scan_progress(self, current: int, total: int, current_game: str):
        """Handle scan progress"""
        self.status_manager.show_message(
            f"Scanning: {current_game} ({current}/{total})"
        )

    def on_scan_complete(self, games):
        """Handle scan completion"""
        self.table_manager.populate_games(games)
        self.status_manager.show_message(f"Found {len(games)} games")

        # Update transferred states
        current_target = self.directory_manager.get_target_directory(
            self.current_mode, self.current_platform
        )
        self.game_manager.update_transferred_states(current_target)

    def on_scan_error(self, error_message: str):
        """Handle scan error"""
        UIUtils.show_critical(self, "Scan Error", error_message)

    def on_transfer_started(self):
        """Handle transfer start"""
        self.status_manager.show_message("Transfer started...")

    def on_transfer_progress(self, current: int, total: int, current_game: str):
        """Handle transfer progress"""
        self.status_manager.show_message(
            f"Transferring: {current_game} ({current}/{total})"
        )

    def on_game_transferred(self, title_id: str):
        """Handle individual game transfer completion"""
        self.game_manager.mark_game_transferred(title_id)
        self.table_manager.update_game_transferred_status(title_id, True)

    def on_transfer_complete(self):
        """Handle transfer completion"""
        self.status_manager.show_message("Transfer completed successfully!")
        UIUtils.show_information(
            self, "Transfer Complete", "All games transferred successfully!"
        )

    def on_transfer_error(self, error_message: str):
        """Handle transfer error"""
        UIUtils.show_critical(self, "Transfer Error", error_message)

    def on_selection_changed(self):
        """Handle table selection change"""
        selected_count = self.table_manager.get_selected_count()
        self.status_manager.show_message(f"{selected_count} games selected")

    def on_context_menu_requested(self, x: int, y: int, title_id: str):
        """Handle context menu request"""
        # Show context menu for game
        pass

    # Public methods - much simpler!

    def browse_directory(self):
        """Browse for source directory"""
        directory = self.directory_manager.browse_directory(
            self, "Xbox 360", self.directory_manager.current_directory
        )

        if directory:
            self.directory_manager.set_current_directory(
                directory, self.current_platform
            )

    def start_scan(self):
        """Start scanning current directory"""
        current_dir = self.directory_manager.current_directory
        if not current_dir:
            UIUtils.show_warning(
                self, "No Directory", "Please select a directory first"
            )
            return

        self.game_manager.start_scan(
            current_dir, self.current_platform, self.current_mode
        )

    def transfer_selected_games(self):
        """Transfer selected games"""
        selected_ids = self.table_manager.get_selected_title_ids()

        if not selected_ids:
            UIUtils.show_information(
                self, "No Selection", "Please select games to transfer"
            )
            return

        selected_games = self.game_manager.get_selected_games(selected_ids)
        target_dir = self.directory_manager.get_target_directory(
            self.current_mode, self.current_platform
        )

        # Validate transfer requirements
        is_valid, error_msg = self.transfer_manager.validate_transfer_requirements(
            selected_games, target_dir
        )
        if not is_valid:
            UIUtils.show_warning(self, "Transfer Error", error_msg)
            return

        # Start transfer
        self.transfer_manager.start_transfer(
            selected_games, target_dir, self.current_mode, self.current_platform
        )


# Compare the sizes:
# Original main_window.py: 5,356 lines (God Object)
# This refactored version: ~200 lines (Single Responsibility)
#
# The functionality is separated into focused managers:
# - DirectoryManager: 160 lines
# - GameManager: 130 lines
# - TableManager: 190 lines
# - TransferManager: 120 lines
# Total: ~800 lines across 5 focused classes vs 5,356 lines in one class!
