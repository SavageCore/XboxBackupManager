#!/usr/bin/env python3
"""
Xbox Backup Manager - Main Window
Refactored main window class using modular components
"""

import os
from pathlib import Path
from typing import Dict, List

from PyQt6.QtCore import (
    QFileSystemWatcher,
    Qt,
    QTimer,
)
from PyQt6.QtGui import QAction, QActionGroup, QIcon, QPixmap
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QFileDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMainWindow,
    QMenu,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from database.title_database import TitleDatabaseLoader

# Import our modular components
from models.game_info import GameInfo
from ui.theme_manager import ThemeManager
from utils.settings_manager import SettingsManager
from utils.system_utils import SystemUtils
from widgets.icon_delegate import IconDelegate
from workers.directory_scanner import DirectoryScanner
from workers.icon_downloader import IconDownloader


class XboxBackupManager(QMainWindow):
    """Main application window"""

    def __init__(self):
        super().__init__()

        # Initialize managers
        self.settings_manager = SettingsManager()
        self.theme_manager = ThemeManager()
        self.database_loader = TitleDatabaseLoader()

        # Application state
        self.games: List[GameInfo] = []
        self.current_directory = ""
        self.current_platform = "xbox360"  # Default platform
        self.platform_directories = {"xbox360": "", "xbla": ""}
        self.icon_cache: Dict[str, QPixmap] = {}

        # File system monitoring
        self.file_watcher = QFileSystemWatcher()
        self.file_watcher.directoryChanged.connect(self.on_directory_changed)

        # Timer to debounce file system events
        self.scan_timer = QTimer()
        self.scan_timer.setSingleShot(True)
        self.scan_timer.timeout.connect(self.delayed_scan)
        self.scan_delay = 2000  # 2 seconds delay

        # Connect database signals
        self.database_loader.database_loaded.connect(self.on_database_loaded)
        self.database_loader.database_error.connect(self.on_database_error)

        # Initialize UI and load settings
        self.init_ui()
        self.load_settings()
        self.load_title_database()

    def init_ui(self):
        """Initialize the user interface"""
        self.setWindowTitle("Xbox Backup Manager")
        self.setGeometry(100, 100, 1000, 600)

        # Create menu bar
        self.create_menu_bar()

        # Central widget and main layout
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # Create top section
        self.create_top_section(main_layout)

        # Create games table
        self.create_games_table(main_layout)

        # Create progress bar
        self.create_progress_bar(main_layout)

        # Status bar
        self.status_bar = self.statusBar()
        self.status_bar.showMessage("Ready - Load title database first")

    def create_top_section(self, main_layout):
        """Create the top section with directory controls"""
        top_layout = QHBoxLayout()
        top_layout.setContentsMargins(10, 10, 10, 10)
        top_layout.setSpacing(10)

        self.directory_label = QLabel("No directory selected")
        self.directory_label.setStyleSheet("QLabel { font-weight: bold; }")

        self.browse_button = QPushButton("Browse Directory")
        self.browse_button.setObjectName("browse_button")
        self.browse_button.clicked.connect(self.browse_directory)

        self.scan_button = QPushButton("Scan Directory")
        self.scan_button.setObjectName("scan_button")
        self.scan_button.clicked.connect(self.scan_directory)
        self.scan_button.setEnabled(False)

        # Platform indicator label
        self.platform_label = QLabel("Xbox 360")
        self.platform_label.setStyleSheet("QLabel { font-weight: bold; }")

        top_layout.addWidget(QLabel("Directory:"))
        top_layout.addWidget(self.directory_label, 1)
        top_layout.addWidget(self.platform_label)
        top_layout.addWidget(self.browse_button)
        top_layout.addWidget(self.scan_button)

        top_widget = QWidget()
        top_widget.setLayout(top_layout)
        main_layout.addWidget(top_widget)

    def create_games_table(self, main_layout):
        """Create and setup the games table"""
        self.games_table = QTableWidget()
        self.games_table.setContentsMargins(0, 0, 0, 0)

        # Enable context menu
        self.games_table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.games_table.customContextMenuRequested.connect(self.show_context_menu)

        main_layout.addWidget(self.games_table)

    def create_progress_bar(self, main_layout):
        """Create the progress bar"""
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        self.progress_bar.setMaximumHeight(20)
        self.progress_bar.setContentsMargins(10, 0, 10, 10)
        main_layout.addWidget(self.progress_bar)

    def create_menu_bar(self):
        """Create the application menu bar"""
        menubar = self.menuBar()

        # File menu
        self.create_file_menu(menubar)

        # Platform menu
        self.create_platform_menu(menubar)

        # View menu
        self.create_view_menu(menubar)

        # Help menu
        self.create_help_menu(menubar)

    def create_file_menu(self, menubar):
        """Create the File menu"""
        file_menu = menubar.addMenu("&File")

        browse_action = QAction("&Browse Directory...", self)
        browse_action.setShortcut("Ctrl+O")
        browse_action.triggered.connect(self.browse_directory)
        file_menu.addAction(browse_action)

        file_menu.addSeparator()

        exit_action = QAction("E&xit", self)
        exit_action.setShortcut("Ctrl+Q")
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)

    def create_platform_menu(self, menubar):
        """Create the Platform menu"""
        platform_menu = menubar.addMenu("&Platform")
        self.platform_action_group = QActionGroup(self)

        self.xbox360_action = QAction("&Xbox 360", self)
        self.xbox360_action.setCheckable(True)
        self.xbox360_action.setChecked(True)
        self.xbox360_action.triggered.connect(lambda: self.switch_platform("xbox360"))
        self.platform_action_group.addAction(self.xbox360_action)
        platform_menu.addAction(self.xbox360_action)

        self.xbla_action = QAction("Xbox &Live Arcade", self)
        self.xbla_action.setCheckable(True)
        self.xbla_action.triggered.connect(lambda: self.switch_platform("xbla"))
        self.platform_action_group.addAction(self.xbla_action)
        platform_menu.addAction(self.xbla_action)

    def create_view_menu(self, menubar):
        """Create the View menu"""
        view_menu = menubar.addMenu("&View")
        theme_menu = view_menu.addMenu("&Theme")
        self.theme_action_group = QActionGroup(self)

        self.auto_theme_action = QAction("&Auto", self)
        self.auto_theme_action.setCheckable(True)
        self.auto_theme_action.setChecked(True)
        self.auto_theme_action.triggered.connect(lambda: self.set_theme_override(None))
        self.theme_action_group.addAction(self.auto_theme_action)
        theme_menu.addAction(self.auto_theme_action)

        self.light_theme_action = QAction("&Light", self)
        self.light_theme_action.setCheckable(True)
        self.light_theme_action.triggered.connect(
            lambda: self.set_theme_override(False)
        )
        self.theme_action_group.addAction(self.light_theme_action)
        theme_menu.addAction(self.light_theme_action)

        self.dark_theme_action = QAction("&Dark", self)
        self.dark_theme_action.setCheckable(True)
        self.dark_theme_action.triggered.connect(lambda: self.set_theme_override(True))
        self.theme_action_group.addAction(self.dark_theme_action)
        theme_menu.addAction(self.dark_theme_action)

    def create_help_menu(self, menubar):
        """Create the Help menu"""
        help_menu = menubar.addMenu("&Help")

        about_action = QAction("&About", self)
        about_action.triggered.connect(self.show_about)
        help_menu.addAction(about_action)

    def switch_platform(self, platform: str):
        """Switch to a different platform"""
        if platform == self.current_platform:
            return

        # Save current directory for current platform
        if self.current_directory:
            self.platform_directories[self.current_platform] = self.current_directory

        # Stop watching current directory
        self.stop_watching_directory()

        # Switch to new platform
        self.current_platform = platform

        # Update platform label
        platform_names = {"xbox360": "Xbox 360", "xbla": "Xbox Live Arcade"}
        self.platform_label.setText(platform_names[platform])

        # Recreate table with appropriate columns for new platform
        self.setup_table()

        # Load directory for new platform
        if self.platform_directories[platform]:
            self.current_directory = self.platform_directories[platform]
            self.directory_label.setText(self.current_directory)
            self.scan_button.setEnabled(True)
            self.start_watching_directory()
            self.scan_directory()
        else:
            self.current_directory = ""
            self.directory_label.setText("No directory selected")
            self.scan_button.setEnabled(False)
            self.games.clear()
            self.games_table.setRowCount(0)

        # Save platform selection
        self.settings_manager.save_current_platform(platform)
        self.status_bar.showMessage(f"Switched to {platform_names[platform]}")

    def set_theme_override(self, override_value):
        """Set theme override and apply theme"""
        self.theme_manager.set_override(override_value)
        self.apply_theme()
        self.settings_manager.save_theme_preference(override_value)

    def show_about(self):
        """Show about dialog"""
        QMessageBox.about(
            self,
            "About Xbox 360 Backup Manager",
            "Xbox 360 Backup Manager v1.0.0\n\n"
            "A cross-platform GUI for managing Xbox 360 game backups.\n"
            "Similar to Wii Backup Manager but for Xbox 360/XBLA.\n\n"
            "Supports automatic scanning, file system watching, and game organization.",
        )

    def apply_theme(self):
        """Apply the current theme"""
        stylesheet = self.theme_manager.get_stylesheet()
        self.setStyleSheet(stylesheet)
        self.update_theme_menu_state()

    def update_theme_menu_state(self):
        """Update theme menu state based on current override"""
        if self.theme_manager.dark_mode_override is None:
            self.auto_theme_action.setChecked(True)
        elif self.theme_manager.dark_mode_override:
            self.dark_theme_action.setChecked(True)
        else:
            self.light_theme_action.setChecked(True)

    def load_settings(self):
        """Load settings from persistent storage"""
        # Restore window state
        self.settings_manager.restore_window_state(self)

        # Restore theme preference
        theme_override = self.settings_manager.load_theme_preference()
        self.theme_manager.set_override(theme_override)

        # Restore current platform
        self.current_platform = self.settings_manager.load_current_platform()

        # Update platform menu state
        platform_actions = {
            "xbox360": self.xbox360_action,
            "xbla": self.xbla_action,
        }
        if self.current_platform in platform_actions:
            platform_actions[self.current_platform].setChecked(True)

        # Restore platform directories
        self.platform_directories = self.settings_manager.load_platform_directories()

        # Set current directory based on current platform
        if self.platform_directories[self.current_platform]:
            self.current_directory = self.platform_directories[self.current_platform]
            self.directory_label.setText(self.current_directory)

        # Update platform label
        platform_names = {"xbox360": "Xbox 360", "xbla": "Xbox Live Arcade"}
        self.platform_label.setText(platform_names[self.current_platform])

        # Setup the table with the correct platform
        self.setup_table()

        # Load cached icons
        self.load_cached_icons()

        # Apply theme after loading preferences
        self.apply_theme()

    def load_cached_icons(self):
        """Load any cached icons from disk"""
        cache_dir = Path("cache/icons")
        if not cache_dir.exists():
            return

        # Load all cached icons
        for cache_file in cache_dir.glob("*.png"):
            title_id = cache_file.stem.upper()
            pixmap = QPixmap(str(cache_file))
            if not pixmap.isNull():
                self.icon_cache[title_id] = pixmap

    def save_settings(self):
        """Save settings to persistent storage"""
        # Save window state
        self.settings_manager.save_window_state(self)

        # Save current platform
        self.settings_manager.save_current_platform(self.current_platform)

        # Save current directory for current platform
        if self.current_directory:
            self.platform_directories[self.current_platform] = self.current_directory

        # Save all platform directories
        self.settings_manager.save_platform_directories(self.platform_directories)

        # Save theme preference
        self.settings_manager.save_theme_preference(
            self.theme_manager.dark_mode_override
        )

        # Save table settings
        if hasattr(self.games_table, "horizontalHeader"):
            header = self.games_table.horizontalHeader()
            sort_column = header.sortIndicatorSection()
            sort_order = header.sortIndicatorOrder()
            self.settings_manager.save_table_settings(
                self.current_platform, header, sort_column, sort_order
            )

    def browse_directory(self):
        """Open directory selection dialog"""
        start_dir = (
            self.current_directory
            if self.current_directory
            else os.path.expanduser("~")
        )
        platform_names = {"xbox360": "Xbox 360", "xbla": "Xbox Live Arcade"}

        directory = QFileDialog.getExistingDirectory(
            self,
            f"Select {platform_names[self.current_platform]} Games Directory",
            start_dir,
        )

        if directory:
            # Stop watching old directory
            self.stop_watching_directory()

            self.current_directory = directory
            self.platform_directories[self.current_platform] = directory
            self.directory_label.setText(directory)
            self.scan_button.setEnabled(True)
            self.status_bar.showMessage(f"Selected directory: {directory}")

            # Start watching new directory
            self.start_watching_directory()

            # Start scanning the directory
            self.scan_directory()

    def load_title_database(self):
        """Load the Xbox title database"""
        self.status_bar.showMessage("Loading title database...")
        self.database_loader.load_database()

    def on_database_loaded(self, database: Dict[str, str]):
        """Handle successful database loading"""
        count = len(database)
        self.status_bar.showMessage(
            f"Title database loaded - {count:,} titles available"
        )

        # Enable UI elements
        self.browse_button.setEnabled(True)
        if self.current_directory:
            self.scan_button.setEnabled(True)
            self.start_watching_directory()
            self.scan_directory()

    def on_database_error(self, error_msg: str):
        """Handle database loading error"""
        self.status_bar.showMessage("Failed to load title database")
        QMessageBox.critical(
            self, "Database Error", f"Failed to load title database:\n{error_msg}"
        )

        # Enable UI elements even without database
        self.browse_button.setEnabled(True)
        if self.current_directory:
            self.scan_button.setEnabled(True)

    def start_watching_directory(self):
        """Start watching the current directory for changes"""
        if not self.current_directory:
            return

        # Remove previous paths from watcher
        watched_paths = self.file_watcher.directories()
        if watched_paths:
            self.file_watcher.removePaths(watched_paths)

        # Add current directory to watcher
        if os.path.exists(self.current_directory):
            self.file_watcher.addPath(self.current_directory)

    def stop_watching_directory(self):
        """Stop watching the current directory"""
        watched_paths = self.file_watcher.directories()
        if watched_paths:
            self.file_watcher.removePaths(watched_paths)

    def on_directory_changed(self, path: str):
        """Handle directory changes detected by file system watcher"""
        if path == self.current_directory:
            # Use timer to debounce rapid file system events
            self.scan_timer.stop()
            self.scan_timer.start(self.scan_delay)
            self.status_bar.showMessage(
                f"Directory changed - rescanning in {self.scan_delay//1000}s..."
            )

    def delayed_scan(self):
        """Perform delayed scan after directory changes"""
        if self.current_directory and os.path.exists(self.current_directory):
            self.scan_directory()

    def scan_directory(self):
        """Start scanning the selected directory"""
        if not self.current_directory:
            return

        # Don't scan if already scanning
        if hasattr(self, "scanner") and self.scanner.isRunning():
            return

        # Store current sort settings before clearing table
        if hasattr(self.games_table, "horizontalHeader"):
            header = self.games_table.horizontalHeader()
            self.current_sort_column = header.sortIndicatorSection()
            self.current_sort_order = header.sortIndicatorOrder()

        # Clear previous results
        self.games.clear()
        self.games_table.setRowCount(0)

        # Setup progress bar
        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(0)
        self.scan_button.setEnabled(False)
        self.browse_button.setEnabled(False)

        # Start scanning thread
        self.scanner = DirectoryScanner(
            self.current_directory, self.database_loader.title_database
        )
        self.scanner.progress.connect(self.update_progress)
        self.scanner.game_found.connect(self.add_game)
        self.scanner.finished.connect(self.scan_finished)
        self.scanner.error.connect(self.scan_error)
        self.scanner.start()

        self.status_bar.showMessage("Scanning directory...")

    def update_progress(self, current: int, total: int):
        """Update progress bar"""
        if total > 0:
            percentage = int((current / total) * 100)
            self.progress_bar.setValue(percentage)

    def add_game(self, game_info: GameInfo):
        """Add a game to the table"""
        self.games.append(game_info)

        # Disable sorting during bulk insertion
        self.games_table.setSortingEnabled(False)

        row = self.games_table.rowCount()
        self.games_table.insertRow(row)
        self.games_table.setRowHeight(row, 72)

        # Determine if we should show DLCs column based on platform
        show_dlcs = self.current_platform in ["xbla"]

        # Create table items
        self._create_table_items(row, game_info, show_dlcs)

        # Update status
        self.status_bar.showMessage(f"Found {len(self.games)} games...")

    def _create_table_items(self, row: int, game_info: GameInfo, show_dlcs: bool):
        """Create and populate table items for a game row"""
        col_index = 0

        # Icon column
        icon_item = QTableWidgetItem()
        icon_item.setFlags(icon_item.flags() & ~Qt.ItemFlag.ItemIsEditable)

        # Add icon if we have it cached
        if game_info.title_id in self.icon_cache:
            pixmap = self.icon_cache[game_info.title_id]
            icon = QIcon(pixmap)
            icon_item.setIcon(icon)

        self.games_table.setItem(row, col_index, icon_item)
        col_index += 1

        # Title ID column
        title_id_item = QTableWidgetItem(game_info.title_id)
        title_id_item.setData(Qt.ItemDataRole.UserRole, game_info.title_id)
        title_id_item.setFlags(title_id_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
        self.games_table.setItem(row, col_index, title_id_item)
        col_index += 1

        # Game Name column
        name_item = QTableWidgetItem(game_info.name)
        name_item.setData(Qt.ItemDataRole.UserRole, game_info.name)
        name_item.setFlags(name_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
        self.games_table.setItem(row, col_index, name_item)
        col_index += 1

        # Size column
        size_item = QTableWidgetItem(game_info.size_formatted)
        size_item.setData(Qt.ItemDataRole.UserRole, game_info.size_bytes)
        size_item.setFlags(size_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
        self.games_table.setItem(row, col_index, size_item)
        col_index += 1

        # DLCs column (XBLA only)
        if show_dlcs:
            dlc_folder = Path(game_info.folder_path) / "00000002"
            if dlc_folder.exists() and dlc_folder.is_dir():
                dlcs_count = len([f for f in dlc_folder.iterdir() if f.is_file()])
            else:
                dlcs_count = 0

            dlc_item = QTableWidgetItem(str(dlcs_count))
            dlc_item.setData(Qt.ItemDataRole.UserRole, dlcs_count)
            dlc_item.setFlags(dlc_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.games_table.setItem(row, col_index, dlc_item)
            col_index += 1

        # Folder Path column (always last)
        path_item = QTableWidgetItem(game_info.folder_path)
        path_item.setData(Qt.ItemDataRole.UserRole, game_info.folder_path)
        path_item.setFlags(path_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
        self.games_table.setItem(row, col_index, path_item)

    def scan_finished(self):
        """Handle scan completion"""
        self.progress_bar.setVisible(False)
        self.scan_button.setEnabled(True)
        self.browse_button.setEnabled(True)

        game_count = len(self.games)
        total_size = sum(game.size_bytes for game in self.games)

        # Format total size
        size_formatted = total_size
        for unit in ["B", "KB", "MB", "GB", "TB"]:
            if size_formatted < 1024.0:
                break
            size_formatted /= 1024.0

        # Re-enable sorting and restore previous sort settings
        self.games_table.setSortingEnabled(True)

        # Apply the previous sort order, or default to Game Name
        if hasattr(self, "current_sort_column") and hasattr(self, "current_sort_order"):
            self.games_table.sortItems(
                self.current_sort_column, self.current_sort_order
            )
        else:
            # Default sort (Game Name column is always column 2 with icons)
            self.games_table.sortItems(2, Qt.SortOrder.AscendingOrder)

        self.status_bar.showMessage(
            f"Scan complete - {game_count:,} games found ({size_formatted:.1f} {unit})"
        )

        # Download icons for games that don't have them cached
        if game_count > 0:
            self.download_missing_icons()

        if game_count == 0:
            QMessageBox.information(
                self,
                "No Games Found",
                "No Xbox game folders were found in the selected directory.\n\n"
                "Make sure the directory contains subdirectories named with Title IDs.",
            )

    def download_missing_icons(self):
        """Download icons for games that don't have them cached"""
        missing_title_ids = []

        for game in self.games:
            if game.title_id not in self.icon_cache:
                missing_title_ids.append(game.title_id)

        if missing_title_ids:
            self.status_bar.showMessage(
                f"Downloading {len(missing_title_ids)} game icons..."
            )

            # Start icon downloader thread
            self.icon_downloader = IconDownloader(missing_title_ids)
            self.icon_downloader.icon_downloaded.connect(self.on_icon_downloaded)
            self.icon_downloader.download_failed.connect(self.on_icon_download_failed)
            self.icon_downloader.finished.connect(self.on_icon_download_finished)
            self.icon_downloader.start()

    def on_icon_downloaded(self, title_id: str, pixmap: QPixmap):
        """Handle successful icon download"""
        # Store in cache
        self.icon_cache[title_id] = pixmap

        # Update the table row for this title ID
        title_id_column = 1  # Title ID is always in column 1 when icons are shown

        for row in range(self.games_table.rowCount()):
            title_item = self.games_table.item(row, title_id_column)
            if title_item and title_item.text() == title_id:
                # Set icon in the icon column (column 0)
                icon_item = self.games_table.item(row, 0)
                if icon_item:
                    icon = QIcon(pixmap)
                    icon_item.setIcon(icon)
                break

    def on_icon_download_failed(self, title_id: str):
        """Handle failed icon download"""
        # Could create a placeholder icon or just leave empty
        pass

    def on_icon_download_finished(self):
        """Handle completion of icon download batch"""
        self.status_bar.showMessage("Icon downloads completed")

    def setup_table(self):
        """Setup the games table widget"""
        # Determine if we should show DLCs column based on platform
        show_dlcs = self.current_platform in ["xbla"]

        # Set columns and headers
        if show_dlcs:
            self.games_table.setColumnCount(6)
            headers = ["Icon", "Title ID", "Game Name", "Size", "DLCs", "Folder Path"]
        else:
            self.games_table.setColumnCount(5)
            headers = ["Icon", "Title ID", "Game Name", "Size", "Folder Path"]

        self.games_table.setHorizontalHeaderLabels(headers)

        # Set up custom icon delegate for proper icon rendering
        icon_delegate = IconDelegate()
        self.games_table.setItemDelegateForColumn(0, icon_delegate)

        # Configure column widths and resize modes
        self._setup_table_columns(show_dlcs)

        # Configure table appearance and behavior
        self._configure_table_appearance()

        # Load saved table settings
        self._load_table_settings()

    def _setup_table_columns(self, show_dlcs: bool):
        """Setup table column widths and resize modes"""
        header = self.games_table.horizontalHeader()

        # Icon column - fixed width
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        header.resizeSection(0, 80)

        # Other columns
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Interactive)  # Title ID
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Interactive)  # Game Name
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.Interactive)  # Size

        if show_dlcs:
            header.setSectionResizeMode(4, QHeaderView.ResizeMode.Interactive)  # DLCs
            header.setSectionResizeMode(
                5, QHeaderView.ResizeMode.Stretch
            )  # Folder Path
        else:
            header.setSectionResizeMode(
                4, QHeaderView.ResizeMode.Stretch
            )  # Folder Path

        # Set minimum column widths
        header.setMinimumSectionSize(80)

        # Set initial column widths
        header.resizeSection(1, 100)  # Title ID
        header.resizeSection(2, 300)  # Game Name
        header.resizeSection(3, 100)  # Size
        if show_dlcs:
            header.resizeSection(4, 60)  # DLCs

    def _configure_table_appearance(self):
        """Configure table appearance and styling"""
        # Table settings
        self.games_table.setAlternatingRowColors(True)
        self.games_table.setSortingEnabled(True)
        self.games_table.setFrameStyle(0)  # Remove outer frame/border
        self.games_table.setShowGrid(False)  # Remove grid lines

        # Hide vertical header to remove left padding
        vertical_header = self.games_table.verticalHeader()
        vertical_header.setVisible(False)
        vertical_header.setDefaultSectionSize(0)

        # Remove margins and set row height
        self.games_table.setContentsMargins(0, 0, 0, 0)
        self.games_table.verticalHeader().setDefaultSectionSize(72)

        # Disable row selection
        self.games_table.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)

        # Configure horizontal header
        header = self.games_table.horizontalHeader()
        header.setVisible(True)
        header.setHighlightSections(False)
        header.setStretchLastSection(True)
        header.setContentsMargins(0, 0, 0, 0)

        # Apply custom styling
        self.games_table.setStyleSheet(
            """
            QTableWidget {
                gridline-color: transparent;
                border: none;
                margin: 0px;
                padding: 0px;
            }
            QTableWidget::item {
                border-bottom: 1px solid palette(mid);
                padding: 4px;
            }
            QHeaderView::down-arrow, QHeaderView::up-arrow {
                width: 12px;
                height: 12px;
                right: 4px;
            }
            QHeaderView {
                margin: 0px;
                padding: 0px;
            }
        """
        )

        # Set default sort to Game Name (column 2 with icons)
        self.games_table.sortItems(2, Qt.SortOrder.AscendingOrder)

    def _load_table_settings(self):
        """Load saved table column widths and sort settings"""
        try:
            column_widths, sort_column, sort_order = (
                self.settings_manager.load_table_settings(self.current_platform)
            )

            # Restore column widths
            header = self.games_table.horizontalHeader()
            for i, width in column_widths.items():
                header.resizeSection(i, width)

            # Restore sort settings
            self.games_table.sortItems(sort_column, Qt.SortOrder(sort_order))

        except Exception:
            # If loading fails, use defaults
            pass

    def show_context_menu(self, position):
        """Show context menu when right-clicking on table"""
        item = self.games_table.itemAt(position)
        if item is None:
            return

        row = item.row()
        show_dlcs = self.current_platform in ["xbla"]
        folder_path_column = 5 if show_dlcs else 4

        # Get the folder path from the appropriate column
        folder_item = self.games_table.item(row, folder_path_column)
        if folder_item is None:
            return

        folder_path = folder_item.text()

        # Create context menu
        menu = QMenu(self)

        # Add "Open Folder" action
        open_folder_action = menu.addAction("Open Folder")
        open_folder_action.triggered.connect(
            lambda: SystemUtils.open_folder_in_explorer(folder_path, self)
        )

        # Add "Copy Folder Path" action
        copy_path_action = menu.addAction("Copy Folder Path")
        copy_path_action.triggered.connect(
            lambda: SystemUtils.copy_to_clipboard(folder_path)
        )

        # Show the menu at the cursor position
        menu.exec(self.games_table.mapToGlobal(position))

    def scan_error(self, error_msg: str):
        """Handle scan error"""
        self.progress_bar.setVisible(False)
        self.scan_button.setEnabled(True)
        self.browse_button.setEnabled(True)

        QMessageBox.critical(
            self, "Scan Error", f"An error occurred while scanning:\n{error_msg}"
        )

        self.status_bar.showMessage("Scan failed")

    def closeEvent(self, event):
        """Handle application close event"""
        # Stop file system watcher
        self.stop_watching_directory()

        # Stop any running scans
        if hasattr(self, "scanner") and self.scanner.isRunning():
            self.scanner.terminate()
            self.scanner.wait()

        # Stop any running icon downloads
        if hasattr(self, "icon_downloader") and self.icon_downloader.isRunning():
            self.icon_downloader.terminate()
            self.icon_downloader.wait()

        self.save_settings()
        event.accept()
