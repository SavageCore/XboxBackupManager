#!/usr/bin/env python3
"""
Xbox Backup Manager - Main Window
Refactored main window class using modular components
"""

import ctypes
import hashlib
import json
import os
import platform
import shutil
import sys
import time
import zipfile
from pathlib import Path
from typing import Dict, List

import qtawesome as qta
import requests
from PyQt6.QtCore import QFileSystemWatcher, QProcess, QRect, QSize, Qt, QTimer, QUrl
from PyQt6.QtGui import (
    QAction,
    QActionGroup,
    QDesktopServices,
    QIcon,
    QPainter,
    QPixmap,
)
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMenu,
    QMessageBox,
    QProgressBar,
    QProgressDialog,
    QPushButton,
    QStyle,
    QStyleOptionButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from constants import APP_NAME, VERSION
from database.xbox360_title_database import TitleDatabaseLoader
from database.xbox_title_database import XboxTitleDatabaseLoader

# Import our modular components
from models.game_info import GameInfo
from ui.ftp_browser_dialog import FTPBrowserDialog
from ui.ftp_settings_dialog import FTPSettingsDialog
from ui.icon_manager import IconManager
from ui.theme_manager import ThemeManager
from ui.xboxunity_settings_dialog import XboxUnitySettingsDialog
from ui.xboxunity_tu_dialog import XboxUnityTitleUpdatesDialog
from utils.ftp_client import FTPClient
from utils.github import check_for_update, update
from utils.settings_manager import SettingsManager
from utils.status_manager import StatusManager
from utils.system_utils import SystemUtils
from utils.xboxunity import XboxUnity
from widgets.icon_delegate import IconDelegate
from workers.directory_scanner import DirectoryScanner
from workers.file_transfer import FileTransferWorker
from workers.ftp_connection_tester import FTPConnectionTester
from workers.ftp_transfer import FTPTransferWorker
from workers.icon_downloader import IconDownloader
from workers.zip_extract import ZipExtractorWorker


class XboxBackupManager(QMainWindow):
    """Main application window"""

    def __init__(self):
        super().__init__()

        app = QApplication.instance()
        if app is None:
            app = QApplication(sys.argv)

        # Initialize cache
        self._cache_dir = Path("cache")
        self._cache_dir.mkdir(exist_ok=True)

        # Clean up old cache files
        self._cleanup_old_cache_files()

        # Initialize managers
        self.settings_manager = SettingsManager()
        self.theme_manager = ThemeManager()
        self.database_loader = TitleDatabaseLoader()
        self.icon_manager = IconManager(self.theme_manager)
        self.xboxunity = XboxUnity()

        self.status_bar = self.statusBar()
        self.status_manager = StatusManager(self.status_bar, self)

        self.xbox_database_loader = XboxTitleDatabaseLoader()
        self.xbox_database_loader.database_loaded.connect(self.on_xbox_database_loaded)
        self.xbox_database_loader.database_error.connect(self.on_xbox_database_error)

        # Application state
        self.games: List[GameInfo] = []
        self.current_directory = ""
        self.current_target_directory = ""
        self.current_cache_directory = ""
        self.current_content_directory = ""
        self.current_mode = "usb"
        self.current_platform = "xbox360"  # Default platform
        self.platform_directories = {"xbox": "", "xbox360": "", "xbla": ""}
        self.usb_target_directories = {"xbox": "", "xbox360": "", "xbla": ""}
        self.usb_cache_directory = ""
        self.usb_content_directory = ""
        self.platform_names = {
            "xbox": "Xbox",
            "xbox360": "Xbox 360",
            "xbla": "Xbox Live Arcade",
        }
        self.icon_cache: Dict[str, QPixmap] = {}
        self.ftp_settings = {}
        self.ftp_target_directories = {"xbox": "/", "xbox360": "/", "xbla": "/"}

        self.xboxunity_settings = {}

        # Transfer state
        self._current_transfer_speed = ""
        self._current_transfer_file = ""
        self._current_transfer_speed = ""  # For storing current transfer speed

        # Get the current palette from your theme manager
        palette = self.theme_manager.get_palette()

        # Extract colors from the palette for different states
        self.normal_color = palette.COLOR_BACKGROUND_6
        self.active_color = palette.COLOR_BACKGROUND_6
        self.disabled_color = palette.COLOR_DISABLED

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

        self.setup_colors()
        self.setup_ui()

        self._check_for_updates()

        QTimer.singleShot(100, self._check_required_tools)

    def setup_colors(self):
        """Setup color properties from theme"""
        palette = self.theme_manager.get_palette()

        self.normal_color = palette.COLOR_TEXT_1
        self.active_color = palette.COLOR_TEXT_1
        self.disabled_color = palette.COLOR_DISABLED

    def setup_ui(self):
        """Setup UI with themed icons"""
        self.icon_manager.register_widget_icon(self.browse_action, "fa6s.folder-open")
        self.icon_manager.register_widget_icon(
            self.browse_target_action, "fa6s.bullseye"
        )
        self.icon_manager.register_widget_icon(self.ftp_settings_action, "fa6s.gear")
        self.icon_manager.register_widget_icon(
            self.xbox_unity_settings_action, "fa6s.gear"
        )
        self.icon_manager.register_widget_icon(self.exit_action, "fa6s.xmark")
        self.icon_manager.register_widget_icon(
            self.ftp_mode_action, "fa6s.network-wired"
        )
        self.icon_manager.register_widget_icon(self.usb_mode_action, "fa6s.hard-drive")
        self.icon_manager.register_widget_icon(
            self.ftp_mode_action, "fa6s.network-wired"
        )
        self.icon_manager.register_widget_icon(
            self.extract_iso_action, "fa6s.file-zipper"
        )
        self.icon_manager.register_widget_icon(
            self.create_god_action, "fa6s.compact-disc"
        )
        self.icon_manager.register_widget_icon(self.theme_menu, "fa6s.palette")
        self.icon_manager.register_widget_icon(
            self.auto_theme_action, "fa6s.circle-half-stroke"
        )
        self.icon_manager.register_widget_icon(self.light_theme_action, "fa6s.sun")
        self.icon_manager.register_widget_icon(self.dark_theme_action, "fa6s.moon")
        self.icon_manager.register_widget_icon(self.about_action, "fa6s.circle-info")
        self.icon_manager.register_widget_icon(self.check_updates_action, "fa6s.rotate")
        self.icon_manager.register_widget_icon(
            self.licenses_action, "fa6s.file-contract"
        )

        # Register toolbar icons
        if hasattr(self, "toolbar_actions"):
            for action in self.toolbar_actions:
                icon_name = {
                    "Scan": "fa6s.magnifying-glass",
                    "Transfer": "fa6s.download",
                    "Remove": "fa6s.trash",
                }.get(action.text(), "fa6s.circle")

                self.icon_manager.register_widget_icon(action, icon_name)

    def init_ui(self):
        """Initialize the user interface"""
        self.setWindowTitle(
            f"{APP_NAME} - {self.platform_names[self.current_platform]} - v{VERSION}"
        )
        self.setGeometry(100, 100, 1000, 600)

        # Create menu bar
        self.create_menu_bar()

        # Create toolbar
        self.create_toolbar()

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

    def create_toolbar(self):
        """Create the application toolbar"""
        toolbar = self.addToolBar("Main")
        toolbar.setMovable(False)
        toolbar.setFloatable(False)
        toolbar.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon)
        toolbar.setObjectName("MainToolbar")

        # Set toolbar icon size
        toolbar.setIconSize(QSize(24, 24))

        # Scan Directory
        self.toolbar_scan_action = QAction("Scan", self)
        self.toolbar_scan_action.setIcon(
            qta.icon("fa6s.magnifying-glass", color=self.normal_color)
        )
        self.toolbar_scan_action.setToolTip("Scan current directory for games")
        self.toolbar_scan_action.triggered.connect(
            lambda: self.scan_directory(force=True)
        )
        self.toolbar_scan_action.setEnabled(False)
        toolbar.addAction(self.toolbar_scan_action)

        # Transfer Selected
        self.toolbar_transfer_action = QAction("Transfer", self)
        self.toolbar_transfer_action.setIcon(
            qta.icon("fa6s.download", color=self.normal_color)
        )
        self.toolbar_transfer_action.setToolTip("Transfer selected games to target")
        self.toolbar_transfer_action.triggered.connect(self.transfer_selected_games)
        self.toolbar_transfer_action.setEnabled(False)
        toolbar.addAction(self.toolbar_transfer_action)

        # Remove Selected
        self.toolbar_remove_action = QAction("Remove", self)
        self.toolbar_remove_action.setIcon(
            qta.icon("fa6s.trash", color=self.normal_color)
        )
        self.toolbar_remove_action.setToolTip("Remove selected games from target")
        self.toolbar_remove_action.triggered.connect(self.remove_selected_games)
        self.toolbar_remove_action.setEnabled(False)
        toolbar.addAction(self.toolbar_remove_action)

        # Batch Title Updater
        self.toolbar_batch_tu_action = QAction("Batch Title Updater", self)
        self.toolbar_batch_tu_action.setIcon(
            qta.icon("fa6s.download", color=self.normal_color)
        )
        self.toolbar_batch_tu_action.setToolTip(
            "Download missing title updates for all transferred games"
        )
        self.toolbar_batch_tu_action.triggered.connect(
            self.batch_download_title_updates
        )
        self.toolbar_batch_tu_action.setEnabled(False)
        toolbar.addAction(self.toolbar_batch_tu_action)

        # Store references for icon updates
        self.toolbar_actions = [
            self.toolbar_scan_action,
            self.toolbar_transfer_action,
            self.toolbar_remove_action,
            self.toolbar_batch_tu_action,
        ]

    def create_top_section(self, main_layout):
        """Create the top section with directory controls"""
        top_layout = QVBoxLayout()
        top_layout.setContentsMargins(10, 10, 10, 10)
        top_layout.setSpacing(10)

        # Source directory row
        source_layout = QHBoxLayout()
        source_layout.setSpacing(10)

        self.directory_label = QLabel("No directory selected - click to select")
        self.directory_label.setStyleSheet("QLabel { font-weight: bold; }")

        source_layout.addWidget(QLabel("Source:"))
        source_layout.addWidget(self.directory_label, 0)
        source_layout.addStretch(1)  # Add stretch to push buttons right

        # Target directory row
        target_layout = QHBoxLayout()
        target_layout.setSpacing(1)

        self.target_directory_label = QLabel("No target directory selected")
        self.target_directory_label.setStyleSheet("QLabel { font-weight: bold; }")
        # Set size policy to only take minimum space needed
        self.target_directory_label.setSizePolicy(
            self.target_directory_label.sizePolicy().horizontalPolicy(),
            self.target_directory_label.sizePolicy().verticalPolicy(),
        )

        # Add separate label for free space info
        self.target_space_label = QLabel("")
        # Set size policy to only take minimum space needed
        self.target_space_label.setSizePolicy(
            self.target_space_label.sizePolicy().horizontalPolicy(),
            self.target_space_label.sizePolicy().verticalPolicy(),
        )

        # Platform indicator label
        self.platform_label = QLabel("Xbox 360")
        self.platform_label.setStyleSheet("QLabel { font-weight: bold; }")

        target_layout.addWidget(QLabel("Target:"))
        target_layout.addWidget(self.target_directory_label, 0)  # No stretch factor
        target_layout.addWidget(self.target_space_label, 0)  # No stretch factor
        target_layout.addStretch(1)  # Add stretch to push buttons right
        target_layout.addWidget(self.platform_label, 0)  # Platform next to buttons

        # Search bar (initially hidden)
        self.search_layout = QHBoxLayout()
        self.search_layout.setSpacing(10)

        # Make search label clickable
        self.search_label = QLabel("Search:")

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Search games by title or ID...")
        self.search_input.textChanged.connect(self.filter_games)
        self.search_input.setVisible(True)

        self.search_clear_button = QPushButton("Clear")
        self.search_clear_button.clicked.connect(self.clear_search)
        self.search_clear_button.setVisible(False)
        self.search_clear_button.setCursor(Qt.CursorShape.PointingHandCursor)

        self.search_layout.addWidget(self.search_label)
        self.search_layout.addWidget(self.search_input, 1)
        self.search_layout.addWidget(self.search_clear_button)

        top_layout.addLayout(source_layout)
        top_layout.addLayout(target_layout)
        top_layout.addLayout(self.search_layout)

        self.make_directory_labels_clickable()

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

        # Override mouseMoveEvent for custom cursor handling
        self.games_table.mouseMoveEvent = self._table_mouse_move_event

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
        # menubar = QMenuBar()
        menubar = self.menuBar()

        # menubar.setNativeMenuBar(True)

        # File menu
        self.create_file_menu(menubar)

        # Mode menu (FTP/USB)
        self.create_mode_menu(menubar)

        # Tools menu
        self.create_tools_menu(menubar)

        # Platform menu
        self.create_platform_menu(menubar)

        # View menu
        self.create_view_menu(menubar)

        # Help menu
        self.create_help_menu(menubar)

    def create_file_menu(self, menubar):
        """Create the File menu"""
        file_menu = menubar.addMenu("&File")

        # Set Source directory action
        self.browse_action = QAction("&Set Source Directory...", self)
        self.browse_action.setShortcut("Ctrl+O")
        self.browse_action.setIcon(
            qta.icon("fa6s.folder-open", color=self.normal_color)
        )
        self.browse_action.triggered.connect(self.browse_directory)
        file_menu.addAction(self.browse_action)

        # Set Target directory action
        self.browse_target_action = QAction("&Set Target Directory...", self)
        self.browse_target_action.setShortcut("Ctrl+T")
        self.browse_target_action.setIcon(
            qta.icon("fa6s.bullseye", color=self.normal_color)
        )
        self.browse_target_action.triggered.connect(self.browse_target_directory)
        file_menu.addAction(self.browse_target_action)

        # Set Cache directory action
        self.browse_cache_action = QAction("&Set Cache Directory...", self)
        self.browse_cache_action.setShortcut("Ctrl+K")
        self.browse_cache_action.setIcon(
            qta.icon("fa6s.folder-open", color=self.normal_color)
        )
        self.browse_cache_action.setEnabled(True)
        self.browse_cache_action.triggered.connect(self.browse_cache_directory)
        file_menu.addAction(self.browse_cache_action)

        # Set Content directory action
        self.browse_content_action = QAction("&Set Content Directory...", self)
        self.browse_content_action.setShortcut("Ctrl+N")
        self.browse_content_action.setIcon(
            qta.icon("fa6s.folder-open", color=self.normal_color)
        )
        self.browse_content_action.setEnabled(True)
        self.browse_content_action.triggered.connect(self.browse_content_directory)
        file_menu.addAction(self.browse_content_action)

        file_menu.addSeparator()

        # FTP settings action
        self.ftp_settings_action = QAction("&FTP Settings...", self)
        self.ftp_settings_action.setIcon(qta.icon("fa6s.gear", color=self.normal_color))
        self.ftp_settings_action.triggered.connect(self.show_ftp_settings)
        file_menu.addAction(self.ftp_settings_action)

        # Add Xbox Unity settings action
        self.xbox_unity_settings_action = QAction("&Xbox Unity Settings...", self)
        self.xbox_unity_settings_action.setIcon(
            qta.icon("fa6s.gear", color=self.normal_color)
        )
        self.xbox_unity_settings_action.setEnabled(True)
        self.xbox_unity_settings_action.triggered.connect(self.show_xboxunity_settings)
        file_menu.addAction(self.xbox_unity_settings_action)

        file_menu.addSeparator()

        self.exit_action = QAction("E&xit", self)
        self.exit_action.setShortcut("Ctrl+Q")
        self.exit_action.setIcon(qta.icon("fa6s.xmark", color=self.normal_color))
        self.exit_action.triggered.connect(self.close)
        file_menu.addAction(self.exit_action)

    # Menu to select between FTP or USB mode
    def create_mode_menu(self, menubar):
        """Create the Mode menu"""
        mode_menu = menubar.addMenu("&Mode")
        self.mode_action_group = QActionGroup(self)

        self.ftp_mode_action = QAction("&FTP", self)
        self.ftp_mode_action.setCheckable(True)
        self.ftp_mode_action.setIcon(
            qta.icon(
                "fa6s.network-wired",
                color=self.normal_color,
                color_active=self.active_color,
                color_disabled=self.disabled_color,
            )
        )
        self.ftp_mode_action.triggered.connect(lambda: self.switch_mode("ftp"))
        self.mode_action_group.addAction(self.ftp_mode_action)
        mode_menu.addAction(self.ftp_mode_action)
        self.ftp_mode_action.setEnabled(True)

        self.usb_mode_action = QAction("&USB", self)
        self.usb_mode_action.setCheckable(True)
        self.usb_mode_action.setIcon(
            qta.icon(
                "fa6s.hard-drive",
                color=self.normal_color,
                color_active=self.active_color,
                color_disabled=self.disabled_color,
            )
        )
        self.usb_mode_action.triggered.connect(lambda: self.switch_mode("usb"))
        self.mode_action_group.addAction(self.usb_mode_action)
        mode_menu.addAction(self.usb_mode_action)

        # Set state of menu
        if self.current_mode == "ftp":
            self.ftp_mode_action.setChecked(True)
        else:
            self.usb_mode_action.setChecked(True)

    # Add tools menu with Extract ISO
    def create_tools_menu(self, menubar):
        """Create the Tools menu"""
        tools_menu = menubar.addMenu("&Tools")

        # Extract ISO action
        self.extract_iso_action = QAction("&Extract ISO...", self)
        self.extract_iso_action.setIcon(
            qta.icon("fa6s.file-zipper", color=self.normal_color)
        )
        self.extract_iso_action.triggered.connect(self.browse_for_iso)
        tools_menu.addAction(self.extract_iso_action)

        # Create GOD action
        self.create_god_action = QAction("&Create GOD...", self)
        self.create_god_action.setIcon(
            qta.icon("fa6s.compact-disc", color=self.normal_color)
        )
        self.create_god_action.triggered.connect(self.browse_for_god_creation)
        tools_menu.addAction(self.create_god_action)

    def create_platform_menu(self, menubar):
        """Create the Platform menu"""
        platform_menu = menubar.addMenu("&Platform")
        self.platform_action_group = QActionGroup(self)

        self.xbox_action = QAction("&Xbox", self)
        self.xbox_action.setCheckable(True)
        self.xbox_action.triggered.connect(lambda: self.switch_platform("xbox"))
        self.platform_action_group.addAction(self.xbox_action)
        platform_menu.addAction(self.xbox_action)

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
        view_menu.setTitle("View")

        self.theme_menu = view_menu.addMenu("&Theme")
        self.theme_menu.setIcon(
            qta.icon(
                "fa6s.palette",
                color=self.normal_color,
                color_active=self.active_color,
                color_disabled=self.disabled_color,
            )
        )
        self.theme_action_group = QActionGroup(self)

        self.auto_theme_action = QAction("&Auto", self)
        self.auto_theme_action.setCheckable(True)
        self.auto_theme_action.setChecked(True)
        self.auto_theme_action.setIcon(
            qta.icon(
                "fa6s.circle-half-stroke",
                color=self.normal_color,
                color_active=self.active_color,
                color_disabled=self.disabled_color,
            )
        )
        self.auto_theme_action.triggered.connect(lambda: self.set_theme_override(None))
        self.theme_action_group.addAction(self.auto_theme_action)
        self.theme_menu.addAction(self.auto_theme_action)

        self.light_theme_action = QAction("&Light", self)
        self.light_theme_action.setCheckable(True)
        self.light_theme_action.setIcon(
            qta.icon(
                "fa6s.sun",
                color=self.normal_color,
                color_active=self.active_color,
                color_disabled=self.disabled_color,
            )
        )
        self.light_theme_action.triggered.connect(
            lambda: self.set_theme_override(False)
        )
        self.theme_action_group.addAction(self.light_theme_action)
        self.theme_menu.addAction(self.light_theme_action)

        self.dark_theme_action = QAction("&Dark", self)
        self.dark_theme_action.setCheckable(True)
        self.dark_theme_action.setIcon(
            qta.icon(
                "fa6s.moon",
                color=self.normal_color,
                color_active=self.active_color,
                color_disabled=self.disabled_color,
            )
        )
        self.dark_theme_action.triggered.connect(lambda: self.set_theme_override(True))
        self.theme_action_group.addAction(self.dark_theme_action)
        self.theme_menu.addAction(self.dark_theme_action)

    def create_help_menu(self, menubar):
        """Create the Help menu"""
        help_menu = menubar.addMenu("&Help")

        self.about_action = QAction("&About", self)
        self.about_action.setIcon(
            qta.icon(
                "fa6s.circle-info",
                color=self.normal_color,
                color_active=self.active_color,
                color_disabled=self.disabled_color,
            )
        )
        self.about_action.triggered.connect(self.show_about)
        help_menu.addAction(self.about_action)

        self.check_updates_action = QAction("&Check for Updates...", self)
        self.check_updates_action.setIcon(
            qta.icon(
                "fa6s.rotate",
                color=self.normal_color,
                color_active=self.active_color,
                color_disabled=self.disabled_color,
            )
        )
        self.check_updates_action.triggered.connect(self._check_for_updates)
        help_menu.addAction(self.check_updates_action)

        self.licenses_action = QAction("&Licenses", self)
        self.licenses_action.setIcon(
            qta.icon(
                "fa6s.file-contract",
                color=self.normal_color,
                color_active=self.active_color,
                color_disabled=self.disabled_color,
            )
        )
        self.licenses_action.triggered.connect(self.show_licenses)
        help_menu.addAction(self.licenses_action)

    def _source_directory_clicked(self, event):
        """Handle source directory label click to open folder"""
        if event.button() != Qt.MouseButton.LeftButton:
            return

        if self.current_directory and os.path.exists(self.current_directory):
            SystemUtils.open_folder_in_explorer(self.current_directory, self)
        else:
            self.status_manager.show_message(
                "No source directory set - opening browse dialog..."
            )
            self.browse_directory()

    def _target_directory_clicked(self, event):
        """Handle target directory label click to open folder"""
        if event.button() != Qt.MouseButton.LeftButton:
            return

        if self.current_target_directory and os.path.exists(
            self.current_target_directory
        ):
            SystemUtils.open_folder_in_explorer(self.current_target_directory, self)
        else:
            self.status_manager.show_message(
                "No target directory set - opening browse dialog..."
            )
            self.browse_target_directory()

    def _find_game_row(self, title_id: str) -> int:
        """Find the row index for a game by its title ID"""
        for row in range(self.games_table.rowCount()):
            item = self.games_table.item(row, 2)
            if item and item.text() == title_id:
                return row
        return None

    def _rescan_transferred_state(self):
        """Rescan transferred state of games after directory change"""
        if not self.current_directory or not os.path.exists(self.current_directory):
            return

        # Clear existing transferred state
        for game in self.games:
            game.transferred = False

            is_transferred = self._check_if_transferred(game)
            game.transferred = is_transferred

            # Update the table item state
            row = self._find_game_row(game.title_id)
            if row is not None:
                transferred_column = 5

                show_dlcs = self.current_platform in ["xbla"]
                if show_dlcs:
                    transferred_column = 6

                transferred_item = self.games_table.item(row, transferred_column)
                if transferred_item:
                    transferred_item.setText("✔️" if game.transferred else "❌")

    def make_directory_labels_clickable(self):
        """Make the directory labels clickable to open the folder"""
        self.directory_label.setCursor(Qt.CursorShape.PointingHandCursor)
        self.directory_label.mousePressEvent = self._source_directory_clicked

        # Add target directory label click handling
        self.target_directory_label.setCursor(Qt.CursorShape.PointingHandCursor)
        self.target_directory_label.mousePressEvent = self._target_directory_clicked

        # Optional: Add visual styling to indicate it's clickable
        self.directory_label.setStyleSheet(
            """
            QLabel {
                font-weight: bold;
            }
            QLabel:hover {
                color: palette(highlight);
                text-decoration: underline;
            }
        """
        )

        self.target_directory_label.setStyleSheet(
            """
            QLabel {
                font-weight: bold;
            }
            QLabel:hover {
                color: palette(highlight);
                text-decoration: underline;
            }
        """
        )

    def open_current_directory(self, event):
        """Open the current directory in file explorer"""
        if self.current_directory and os.path.exists(self.current_directory):
            SystemUtils.open_folder_in_explorer(self.current_directory, self)
        else:
            self.status_manager.show_message("No valid directory selected", 3000)

    def open_target_directory(self, event):
        """Open the target directory in file explorer"""
        if self.current_target_directory and os.path.exists(
            self.current_target_directory
        ):
            SystemUtils.open_folder_in_explorer(self.current_target_directory, self)
        else:
            self.status_manager.show_message("No valid target directory selected", 3000)

    def browse_target_directory(self):
        """Open target directory selection dialog"""
        if self.current_mode == "ftp":
            self.browse_ftp_target_directory()
            return

        start_dir = (
            self.current_target_directory
            if self.current_target_directory
            and os.path.exists(self.current_target_directory)
            else os.path.expanduser("~")
        )

        platform_name = self.platform_names[self.current_platform]
        directory = QFileDialog.getExistingDirectory(
            self,
            f"Select Target Directory for {platform_name} Games",
            start_dir,
        )

        if directory:
            # Normalize the path for consistent display and usage
            normalized_directory = os.path.normpath(directory)

            # Verify the selected directory is accessible
            if self._check_target_directory_availability(normalized_directory):
                self.current_target_directory = normalized_directory
                self.usb_target_directories[self.current_platform] = (
                    normalized_directory
                )

                self.target_directory_label.setText(f"{normalized_directory}")
                self._update_target_space_label(normalized_directory)

                # Enable transfer button if we have games and target directory
                self._update_transfer_button_state()

                self.status_manager.show_message(
                    f"Selected target directory: {normalized_directory}"
                )

                # Now rescan to update transferred state
                self._rescan_transferred_state()
            else:
                # Selected directory is not accessible
                QMessageBox.warning(
                    self,
                    "Directory Not Accessible",
                    f"The selected directory is not accessible:\n{normalized_directory}\n\n"
                    "Please ensure the device is properly connected and try again.",
                )
                self.status_manager.show_message(
                    "Selected directory is not accessible", 5000
                )

    def browse_cache_directory(self):
        """Open cache directory selection dialog"""
        if self.current_mode == "ftp":
            self.browse_ftp_cache_directory()
            return

        # Start at existing cache directory if set, if not target directory, else home
        start_dir = (
            self.usb_cache_directory
            if self.usb_cache_directory and os.path.exists(self.usb_cache_directory)
            else (
                self.current_target_directory
                if self.current_target_directory
                and os.path.exists(self.current_target_directory)
                else os.path.expanduser("~")
            )
        )

        directory = QFileDialog.getExistingDirectory(
            self,
            "Select Cache Directory",
            start_dir,
        )

        if directory:
            # Normalize the path for consistent display and usage
            normalized_directory = os.path.normpath(directory)

            # Verify the selected directory is accessible
            if self._check_cache_directory_availability(normalized_directory):
                self.current_cache_directory = normalized_directory
                self.usb_cache_directory = normalized_directory

                self.status_manager.show_message(
                    f"Selected cache directory: {normalized_directory}"
                )
            else:
                # Selected directory is not accessible
                QMessageBox.warning(
                    self,
                    "Directory Not Accessible",
                    f"The selected directory is not accessible:\n{normalized_directory}\n\n"
                    "Please ensure the device is properly connected and try again.",
                )
                self.status_manager.show_message(
                    "Selected directory is not accessible", 5000
                )

    def browse_content_directory(self):
        """Open content directory selection dialog"""
        if self.current_mode == "ftp":
            self.browse_ftp_content_directory()
            return

        # Start at existing content directory if set, if not target directory, else home
        start_dir = (
            self.usb_content_directory
            if self.usb_content_directory and os.path.exists(self.usb_content_directory)
            else (
                self.current_target_directory
                if self.current_target_directory
                and os.path.exists(self.current_target_directory)
                else os.path.expanduser("~")
            )
        )

        directory = QFileDialog.getExistingDirectory(
            self,
            "Select Content Directory",
            start_dir,
        )

        if directory:
            # Normalize the path for consistent display and usage
            normalized_directory = os.path.normpath(directory)

            # Verify the selected directory is accessible
            if self._check_content_directory_availability(normalized_directory):
                self.current_content_directory = normalized_directory
                self.usb_content_directory = normalized_directory

                self.status_manager.show_message(
                    f"Selected content directory: {normalized_directory}"
                )
            else:
                # Selected directory is not accessible
                QMessageBox.warning(
                    self,
                    "Directory Not Accessible",
                    f"The selected directory is not accessible:\n{normalized_directory}\n\n"
                    "Please ensure the device is properly connected and try again.",
                )
                self.status_manager.show_message(
                    "Selected directory is not accessible", 5000
                )

    def _update_transfer_button_state(self):
        """Update transfer and remove button enabled state based on conditions"""
        has_games = len(self.games) > 0
        has_selected = self._get_selected_games_count() > 0

        if self.current_mode == "ftp":
            # For FTP mode, check if we can connect and directory exists
            has_target = bool(
                self.ftp_settings
                and self.ftp_settings.get("host")
                and self.ftp_target_directories[self.current_platform]
            )

            if has_target:
                # Quick validation - don't actually connect here as it's called frequently
                ftp_client = FTPClient()
                try:
                    success, message = ftp_client.connect(
                        self.ftp_settings["host"],
                        self.ftp_settings["username"],
                        self.ftp_settings["password"],
                        self.ftp_settings.get("port", 21),
                        self.ftp_settings.get("use_tls", False),
                    )
                    if success:
                        has_target = ftp_client.directory_exists(
                            self.ftp_target_directories[self.current_platform]
                        )
                    else:
                        has_target = False
                except Exception:
                    has_target = False
                finally:
                    ftp_client.disconnect()
        else:
            # USB mode
            has_target = bool(
                self.usb_target_directories[self.current_platform]
                and os.path.exists(self.usb_target_directories[self.current_platform])
            )

        is_enabled = has_games and has_target and has_selected

        # Update toolbar actions
        self.toolbar_transfer_action.setEnabled(is_enabled)
        self.toolbar_remove_action.setEnabled(is_enabled)
        # Enable batch TU when we have games and target (regardless of selection)
        self.toolbar_batch_tu_action.setEnabled(has_games and has_target)

    def _get_selected_games_count(self):
        """Get count of selected games (checked in checkbox column)"""
        count = 0
        for row in range(self.games_table.rowCount()):
            checkbox_item = self.games_table.item(
                row, 0
            )  # Checkbox is in first column now
            if checkbox_item and checkbox_item.checkState() == Qt.CheckState.Checked:
                count += 1
        return count

    def transfer_selected_games(self):
        """Transfer selected games to target directory"""
        if not self.current_target_directory:
            QMessageBox.warning(
                self, "No Target Directory", "Please select a target directory first."
            )
            return

        selected_games = []
        for row in range(self.games_table.rowCount()):
            checkbox_item = self.games_table.item(row, 0)
            if checkbox_item and checkbox_item.checkState() == Qt.CheckState.Checked:
                # Get game info for this row
                title_id_item = self.games_table.item(
                    row, 2
                )  # Title ID is now column 2
                if title_id_item:
                    title_id = title_id_item.text()
                    # Find the game in our games list
                    for game in self.games:
                        if game.title_id == title_id:
                            selected_games.append(game)
                            break

        if not selected_games:
            QMessageBox.information(
                self,
                "No Games Selected",
                "Please select games to transfer by checking the boxes.",
            )
            return

        # Calculate total size and check disk space
        total_size = sum(game.size_bytes for game in selected_games)
        size_formatted = self._format_size(total_size)

        if self.current_mode == "usb":
            # Check available disk space
            available_space = self._get_available_disk_space(
                self.current_target_directory
            )
            if available_space is None:
                QMessageBox.warning(
                    self,
                    "Disk Space Check Failed",
                    "Could not determine available disk space on target device.\n"
                    "The transfer may fail if there is insufficient space.",
                )
            elif total_size > available_space:
                available_formatted = self._format_size(available_space)
                QMessageBox.critical(
                    self,
                    "Insufficient Disk Space",
                    f"Not enough space on target device!\n\n"
                    f"Required: {size_formatted}\n"
                    f"Available: {available_formatted}\n"
                    f"Additional space needed: {self._format_size(total_size - available_space)}",
                )
                return
        else:
            available_space = None

        # Show confirmation with disk space info
        if available_space is not None and self.current_mode == "usb":
            available_formatted = self._format_size(available_space)
            remaining_after = available_space - total_size
            remaining_formatted = self._format_size(remaining_after)

            space_info = (
                f"Available space: {available_formatted}\n"
                f"Space after transfer: {remaining_formatted}"
            )
        else:
            space_info = "Disk space: Could not determine"

        msg_box = QMessageBox(self)
        msg_box.setWindowTitle("Confirm Transfer")
        msg_box.setText(f"Transfer {len(selected_games)} games ({size_formatted})?")
        msg_box.setInformativeText(
            f"Target: {self.current_target_directory}\n\n{space_info}"
        )
        msg_box.setStandardButtons(
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        msg_box.setDefaultButton(QMessageBox.StandardButton.Yes)

        if msg_box.exec() == QMessageBox.StandardButton.Yes:
            self._start_transfer(selected_games)

    def remove_selected_games(self):
        """Remove selected games from the target directory"""
        selected_rows = []
        for row in range(self.games_table.rowCount()):
            checkbox_item = self.games_table.item(row, 0)
            if checkbox_item and checkbox_item.checkState() == Qt.CheckState.Checked:
                selected_rows.append(row)

        if not selected_rows:
            QMessageBox.information(
                self,
                "No Games Selected",
                "Please select games to remove by checking the boxes.",
            )
            return

        # Confirm removal
        msg_box = QMessageBox(self)
        msg_box.setWindowTitle("Confirm Removal")
        msg_box.setText(f"Remove {len(selected_rows)} selected games?")
        msg_box.setStandardButtons(
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        msg_box.setDefaultButton(QMessageBox.StandardButton.No)

        if msg_box.exec() == QMessageBox.StandardButton.Yes:
            # Remove selected rows
            for row in reversed(selected_rows):
                title_id = self.games_table.item(row, 2).text()
                game_name = self.games_table.item(row, 3).text()
                if self.current_platform == "xbla":
                    source_path = self.games_table.item(row, 7).text()
                else:
                    source_path = self.games_table.item(row, 6).text()
                folder_name = os.path.basename(os.path.dirname(source_path))

                self._remove_game_from_target(title_id, game_name, folder_name)

                # Uncheck the game after successful transfer
                checkbox_item = self.games_table.item(row, 0)
                if checkbox_item:
                    checkbox_item.setCheckState(Qt.CheckState.Unchecked)

    def _get_available_disk_space(self, path: str) -> int:
        """Get available disk space for the given path in bytes"""
        try:
            # shutil.disk_usage returns (total, used, free) in bytes
            _, _, free = shutil.disk_usage(path)
            return free
        except (OSError, AttributeError):
            # Fallback for older Python versions or permission issues
            try:
                if platform.system() == "Windows":
                    # Windows-specific implementation
                    free_bytes = ctypes.c_ulonglong(0)
                    ctypes.windll.kernel32.GetDiskFreeSpaceExW(
                        ctypes.c_wchar_p(path), ctypes.pointer(free_bytes), None, None
                    )
                    return free_bytes.value
                else:
                    # Unix-like systems
                    statvfs = os.statvfs(path)
                    return statvfs.f_frsize * statvfs.f_bavail
            except Exception:
                return None

    def _format_size(self, size_bytes: int) -> str:
        """Format size in bytes to human readable format"""
        size_formatted = float(size_bytes)
        for unit in ["B", "KB", "MB", "GB", "TB"]:
            if size_formatted < 1024.0:
                break
            size_formatted /= 1024.0
        return f"{size_formatted:.1f} {unit}"

    def _start_transfer(self, games_to_transfer: List[GameInfo]):
        """Start the transfer process"""
        self.stop_watching_directory()

        # Disable UI elements during transfer
        self.toolbar_transfer_action.setEnabled(False)
        self.toolbar_remove_action.setEnabled(False)
        self.toolbar_batch_tu_action.setEnabled(False)
        self.browse_action.setEnabled(False)
        self.browse_target_action.setEnabled(False)

        # Show progress bar
        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(0)

        # Add cancel button to status bar
        self._add_cancel_button()

        if self.current_mode == "ftp":
            # Start FTP transfer worker
            self.transfer_worker = FTPTransferWorker(
                games_to_transfer,
                self.ftp_settings["host"],
                self.ftp_settings["username"],
                self.ftp_settings["password"],
                self.current_target_directory,
                self.ftp_settings.get("port", 21),
            )
        else:
            self.transfer_worker = FileTransferWorker(
                games_to_transfer,
                self.current_target_directory,
                max_workers=2,
                buffer_size=2 * 1024 * 1024,
            )

        # Connect signals (same for both transfer types)
        self.transfer_worker.progress.connect(self._update_transfer_progress)
        self.transfer_worker.file_progress.connect(self._update_file_progress)
        if hasattr(self.transfer_worker, "current_file"):
            self.transfer_worker.current_file.connect(self._update_current_file)
        if hasattr(self.transfer_worker, "transfer_speed"):
            self.transfer_worker.transfer_speed.connect(self._update_transfer_speed)
        self.transfer_worker.game_transferred.connect(self._on_game_transferred)
        self.transfer_worker.transfer_complete.connect(self._on_transfer_complete)
        self.transfer_worker.transfer_error.connect(self._on_transfer_error)
        self.transfer_worker.start()

        # Clear any previous transfer speed
        self._current_transfer_speed = ""
        self._current_transfer_file = ""

        mode_text = "via FTP" if self.current_mode == "ftp" else "to USB"
        self.status_manager.show_permanent_message(
            f"Transferring {len(games_to_transfer)} games {mode_text}..."
        )

    def _add_cancel_button(self):
        """Add a cancel button to the status bar"""
        if hasattr(self, "cancel_button"):
            return  # Button already exists

        self.cancel_button = QPushButton("Cancel Transfer")
        self.cancel_button.setIcon(
            qta.icon(
                "fa6s.xmark",
                color=self.normal_color,
                color_active=self.active_color,
                color_disabled=self.disabled_color,
            )
        )
        self.cancel_button.setToolTip("Cancel the current transfer")
        self.cancel_button.clicked.connect(self._cancel_transfer)
        self.cancel_button.setCursor(Qt.CursorShape.PointingHandCursor)

        # Add to status bar on the right side
        self.status_bar.addPermanentWidget(self.cancel_button)

    def _remove_cancel_button(self):
        """Remove the cancel button from the status bar"""
        if hasattr(self, "cancel_button"):
            self.status_bar.removeWidget(self.cancel_button)
            self.cancel_button.deleteLater()
            delattr(self, "cancel_button")

    def _cancel_transfer(self):
        """Cancel the current transfer"""
        if hasattr(self, "transfer_worker") and self.transfer_worker.isRunning():
            # Show confirmation dialog
            msg_box = QMessageBox(self)
            msg_box.setWindowTitle("Cancel Transfer")
            msg_box.setText("Are you sure you want to cancel the transfer?")
            msg_box.setInformativeText(
                "Any files currently being transferred will be incomplete."
            )
            msg_box.setStandardButtons(
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            msg_box.setDefaultButton(QMessageBox.StandardButton.No)

            if msg_box.exec() == QMessageBox.StandardButton.Yes:
                # Stop the transfer worker
                self.transfer_worker.should_stop = True
                self.transfer_worker.terminate()
                self.transfer_worker.wait(3000)  # Wait up to 3 seconds

                # Reset UI state
                self._on_transfer_cancelled()

    def _on_transfer_cancelled(self):
        """Handle transfer cancellation"""
        self.progress_bar.setVisible(False)
        self.toolbar_transfer_action.setEnabled(True)
        self.toolbar_remove_action.setEnabled(True)
        self.toolbar_batch_tu_action.setEnabled(True)
        self.browse_action.setEnabled(True)
        self.browse_target_action.setEnabled(True)

        # Remove cancel button
        self._remove_cancel_button()

        # Restart watching directory
        self.start_watching_directory()

        self.status_manager.show_message("Transfer cancelled")

        # Update transfer button state
        self._update_transfer_button_state()

    def _update_transfer_progress(self, current: int, total: int, current_game: str):
        """Update transfer progress"""
        if total > 0:
            percentage = int((current / total) * 100)
            self.progress_bar.setValue(percentage)
            current_transfer = (
                current + 1
            )  # Current is zero-based, so add 1 for display
            self.status_manager.show_permanent_message(
                f"Transferring: {current_game} ({current_transfer}/{total})"
            )

    def _update_file_progress(self, game_name: str, file_progress: int):
        """Update progress for individual file within current game"""
        if hasattr(self, "transfer_worker") and self.transfer_worker:
            total_games = (
                len(self.transfer_worker.games_to_transfer)
                if hasattr(self.transfer_worker, "games_to_transfer")
                else 1
            )
            current_game_index = getattr(self.transfer_worker, "current_game_index", 0)

            # Calculate overall progress: completed games + current game progress
            overall_progress = (
                (current_game_index * 100) + file_progress
            ) / total_games
            self.progress_bar.setValue(int(overall_progress))

            # Get current speed if available
            speed_text = getattr(self, "_current_transfer_speed", "")
            speed_suffix = f" at {speed_text}" if speed_text else ""

            # Get current file if available
            current_file = getattr(self, "_current_transfer_file", "")
            file_suffix = f" - {current_file}" if current_file else ""

            self.status_manager.show_permanent_message(
                f"Transferring: {game_name} - {file_progress}% ({current_game_index + 1}/{total_games}){speed_suffix}{file_suffix}"
            )

    def _update_transfer_speed(self, game_name: str, speed_bps: float):
        """Update transfer speed in status bar"""
        # Format speed for display
        if speed_bps >= 1024 * 1024:  # MB/s
            self._current_transfer_speed = f"{speed_bps / (1024 * 1024):.1f} MB/s"
        elif speed_bps >= 1024:  # KB/s
            self._current_transfer_speed = f"{speed_bps / 1024:.1f} KB/s"
        else:  # B/s
            self._current_transfer_speed = f"{speed_bps:.0f} B/s"

    def _update_current_file(self, game_name: str, filename: str):
        """Update current file being transferred"""
        self._current_transfer_file = filename

    def _on_game_transferred(self, title_id: str):
        """Handle successful game transfer"""
        # Update the transferred status in the table
        for row in range(self.games_table.rowCount()):
            title_id_item = self.games_table.item(row, 2)  # Title ID column
            if title_id_item and title_id_item.text() == title_id:
                # Update transferred status column
                show_dlcs = self.current_platform in ["xbla"]
                status_column = 6 if show_dlcs else 5  # Transferred column
                status_item = self.games_table.item(row, status_column)
                if status_item:
                    status_item.setText("✔️")
                    status_item.setData(Qt.ItemDataRole.UserRole, True)

                # Uncheck the game after successful transfer
                checkbox_item = self.games_table.item(row, 0)  # Checkbox column
                if checkbox_item:
                    checkbox_item.setCheckState(Qt.CheckState.Unchecked)

                break

    def _on_transfer_complete(self):
        """Handle transfer completion"""
        self.progress_bar.setVisible(False)
        self.toolbar_transfer_action.setEnabled(True)
        self.toolbar_remove_action.setEnabled(True)
        self.toolbar_batch_tu_action.setEnabled(True)
        self.browse_action.setEnabled(True)
        self.browse_target_action.setEnabled(True)

        # Clear transfer speed
        self._current_transfer_speed = ""

        self._remove_cancel_button()

        self.start_watching_directory()

        self.status_manager.show_message("Transfer completed successfully")

        # Update transfer button state
        self._update_transfer_button_state()

    def _on_transfer_error(self, error_message: str):
        """Handle transfer error"""
        self.progress_bar.setVisible(False)
        self.toolbar_transfer_action.setEnabled(True)
        self.toolbar_remove_action.setEnabled(True)
        self.toolbar_batch_tu_action.setEnabled(True)
        self.browse_action.setEnabled(True)
        self.browse_target_action.setEnabled(True)

        # Clear transfer speed
        self._current_transfer_speed = ""
        self.browse_action.setEnabled(True)
        self.browse_target_action.setEnabled(True)

        self._remove_cancel_button()

        self.start_watching_directory()

    def _on_tu_download_started(self, update_name: str):
        """Handle title update download started"""
        self.status_manager.show_message(f"Downloading title update: {update_name}")
        self.progress_bar.setValue(0)
        self.progress_bar.setVisible(True)

    def _on_tu_download_progress(self, update_name: str, progress: int):
        """Handle title update download progress"""
        self.status_manager.show_message(
            f"Downloading title update: {update_name} ({progress}%)"
        )
        self.progress_bar.setValue(progress)

    def _on_tu_download_complete(
        self, update_name: str, success: bool, filename: str, local_path: str
    ):
        """Handle title update download completion"""
        self.progress_bar.setVisible(False)
        if success:
            self.status_manager.show_message(f"Title update installed: {update_name}")
        else:
            self.status_manager.show_message(
                f"Title update installation failed: {update_name}"
            )

    def _on_tu_download_error(self, update_name: str, error_message: str):
        """Handle title update download error"""
        self.progress_bar.setVisible(False)
        self.status_manager.show_message(
            f"Title update download failed: {update_name} - {error_message}"
        )

        QMessageBox.critical(
            self, "Transfer Error", f"Transfer failed:\n{error_message}"
        )
        self.status_manager.show_message("Transfer failed")

    def _check_if_transferred(self, game: GameInfo) -> bool:
        """Check if a game has already been transferred to target directory"""
        if not self.current_target_directory:
            return False

        if self.current_mode == "ftp":
            ftp_client = FTPClient()

            # Are we connected? If not connect
            if not ftp_client.is_connected():
                ftp_client.connect(
                    self.ftp_settings["host"],
                    self.ftp_settings["username"],
                    self.ftp_settings["password"],
                    self.ftp_settings.get("port", 21),
                )

            try:
                target_path = f"{self.current_target_directory.rstrip('/')}/{Path(game.folder_path).name}"
                return ftp_client.directory_exists(target_path)

            except Exception:
                return False
        else:
            target_path = (
                Path(self.current_target_directory) / Path(game.folder_path).name
            )
            return target_path.exists() and target_path.is_dir()

    def browse_directory(self):
        """Open directory selection dialog"""
        start_dir = (
            self.current_directory
            if self.current_directory
            else os.path.expanduser("~")
        )

        directory = QFileDialog.getExistingDirectory(
            self,
            f"Select {self.platform_names[self.current_platform]} Games Directory",
            start_dir,
        )

        if directory:
            # Stop watching old directory
            self.stop_watching_directory()

            # Clear cache for old directory
            self._clear_cache_for_directory()

            # Normalize the path for consistent display and usage
            normalized_directory = os.path.normpath(directory)

            self.current_directory = normalized_directory
            self.platform_directories[self.current_platform] = normalized_directory
            self.directory_label.setText(normalized_directory)
            self.toolbar_scan_action.setEnabled(True)
            self.status_manager.show_message(
                f"Selected directory: {normalized_directory}"
            )

            # Start watching new directory
            self.start_watching_directory()

            # Start scanning the directory
            self.scan_directory(force=True)

    def switch_mode(self, mode: str):
        """Switch between FTP and USB modes with proper timeout handling"""
        if mode == self.current_mode:
            return

        # Update mode first
        self.current_mode = mode

        # Save mode setting immediately
        self.settings_manager.save_current_mode(mode)

        if mode == "ftp":
            self.ftp_target_directories = (
                self.settings_manager.load_ftp_target_directories()
            )
            self.ftp_mode_action.setChecked(True)
            self.usb_mode_action.setChecked(False)

            # Enable FTP settings action
            self.ftp_settings_action.setEnabled(True)

            # Check if FTP settings are configured
            if not self.ftp_settings or not self.ftp_settings.get("host"):
                QMessageBox.information(
                    self,
                    "FTP Settings Required",
                    "FTP mode requires connection settings.\nPlease configure FTP settings first.",
                )
                self.show_ftp_settings()
                # If user cancels settings dialog, switch back to USB mode
                if not self.ftp_settings or not self.ftp_settings.get("host"):
                    self.current_mode = "usb"
                    self.usb_mode_action.setChecked(True)
                    self.ftp_mode_action.setChecked(False)
                    self.settings_manager.save_current_mode("usb")
                    return

            # Test FTP connection before fully switching
            self._test_ftp_connection_for_switch()
            return  # Exit here, _on_ftp_connection_tested will continue the switch

        elif mode == "usb":
            self.usb_target_directories = (
                self.settings_manager.load_usb_target_directories()
            )
            self.ftp_mode_action.setChecked(False)
            self.usb_mode_action.setChecked(True)

            # Continue with normal USB mode setup
            self._complete_mode_switch(mode)

    def switch_platform(self, platform: str):
        """Switch to a different platform"""
        if platform == self.current_platform:
            return

        # Stop any running scanner first
        self._stop_current_scan()

        # Save current directories for current platform
        if self.current_directory:
            self.platform_directories[self.current_platform] = self.current_directory
        if self.current_target_directory:
            self.usb_target_directories[self.current_platform] = (
                self.current_target_directory
            )

        # Update window title
        self.setWindowTitle(
            f"{APP_NAME} - {self.platform_names[platform]} - v{VERSION}"
        )

        # Stop watching current directory
        self.stop_watching_directory()

        # Switch to new platform
        self.current_platform = platform

        # Update platform label
        self.platform_label.setText(self.platform_names[platform])

        # Recreate table with appropriate columns for new platform
        self.setup_table()

        self.load_title_database()

        # Load source directory for new platform
        if self.platform_directories[platform]:
            self.current_directory = self.platform_directories[platform]
            self.directory_label.setText(self.current_directory)
            self.start_watching_directory()
            self.scan_directory()
        else:
            self.current_directory = ""
            self.directory_label.setText("No directory selected - click to select")
            self.games.clear()
            self.games_table.setRowCount(0)

        # Load target directory for new platform
        if self.current_mode == "usb":
            if self.usb_target_directories[platform]:
                self.current_target_directory = self.usb_target_directories[platform]
                self.target_directory_label.setText(self.current_target_directory)
                self._update_target_space_label(self.current_target_directory)
            else:
                self.current_target_directory = ""
                self.target_directory_label.setText(
                    "No target directory selected - click to select"
                )
                self.target_space_label.setText("")
        else:
            if self.ftp_target_directories[platform]:
                self.current_target_directory = self.ftp_target_directories[platform]
                self.target_directory_label.setText(
                    f"FTP: {self.current_target_directory}"
                )
                self._update_target_space_label(self.current_target_directory)
            else:
                self.current_target_directory = ""
                self.target_directory_label.setText("No FTP target set")
                self.target_space_label.setText("")

        # Save platform selection
        self.settings_manager.save_current_platform(platform)
        self.status_manager.show_message(f"Switched to {self.platform_names[platform]}")

    def _select_usb_target_directory(self, platform: str):
        """Select USB target directory for specified platform"""
        platform_name = self.platform_names[platform]
        start_dir = os.path.expanduser("~")

        directory = QFileDialog.getExistingDirectory(
            self,
            f"Select USB Target Directory for {platform_name} Games",
            start_dir,
        )

        if directory:
            # Normalize the path
            normalized_directory = os.path.normpath(directory)

            # Save the target directory
            self.usb_target_directories[platform] = normalized_directory

            # If this is for the current platform, update current target directory
            if platform == self.current_platform:
                self.current_target_directory = normalized_directory
                self.target_directory_label.setText(normalized_directory)
                self._update_target_space_label(self.current_target_directory)

            self.status_manager.show_message(
                f"USB target directory set for {platform_name}: {normalized_directory}"
            )
        else:
            # User cancelled directory selection
            if platform == self.current_platform:
                self._handle_cancelled_usb_directory_selection()

    def _handle_cancelled_usb_directory_selection(self):
        """Handle when user cancels USB target directory selection"""
        self.current_target_directory = ""
        self.target_directory_label.setText("No target directory selected")
        self.status_manager.show_message(
            "USB mode requires a target directory - use Browse Target or File menu to set one"
        )

    def _prompt_for_usb_target_directory(self):
        """Prompt user to select USB target directory for current platform"""
        platform_name = self.platform_names[self.current_platform]

        # Show informational message about USB target directory selection
        msg_box = QMessageBox(self)
        msg_box.setWindowTitle("USB Target Directory Required")
        msg_box.setText(
            f"USB mode requires a target directory for {platform_name} games."
        )
        msg_box.setInformativeText(
            f"Please select the target directory where your {platform_name} games "
            "will be copied to on your USB drive or storage device."
        )
        msg_box.setStandardButtons(
            QMessageBox.StandardButton.Ok | QMessageBox.StandardButton.Cancel
        )
        msg_box.setDefaultButton(QMessageBox.StandardButton.Ok)

        if msg_box.exec() == QMessageBox.StandardButton.Ok:
            self._select_usb_target_directory(self.current_platform)
        else:
            # User cancelled - handle appropriately
            self._handle_cancelled_usb_directory_selection()

    def set_theme_override(self, override_value):
        """Set theme override and apply theme"""
        self.theme_manager.set_override(override_value)
        self.apply_theme()
        self.settings_manager.save_theme_preference(override_value)

    def show_about(self):
        """Show about dialog"""
        msg_box = QMessageBox(self)
        msg_box.setWindowTitle(f"About {APP_NAME}")
        msg_box.setTextFormat(Qt.TextFormat.RichText)
        msg_box.setText(
            f"{APP_NAME} - v{VERSION}<br><br>"
            "A cross-platform GUI for managing Xbox/Xbox 360 game backups.<br><br>"
            "Developed by <a href='https://github.com/SavageCore'>SavageCore</a><br><br>"
            "Issues/Requests: <a href='https://github.com/SavageCore/XboxBackupManager/issues'>GitHub Issues</a>"
        )

        msg_box.setTextInteractionFlags(Qt.TextInteractionFlag.TextBrowserInteraction)

        msg_box.exec()

    def show_licenses(self):
        """Show licenses dialog"""
        msg_box = QMessageBox(self)
        msg_box.setWindowTitle("Licenses")
        msg_box.setTextFormat(Qt.TextFormat.RichText)

        msg_box.setText(
            "This application uses the following libraries:<br><br>"
            "• <a href='https://pypi.org/project/black/'>black</a> (MIT)<br>"
            "• <a href='https://pypi.org/project/darkdetect/'>darkdetect</a> (BSD License (BSD-3-Clause))<br>"
            "• <a href='https://pypi.org/project/PyQt6/'>PyQt6</a> (GPL-3.0-only)<br>"
            "• <a href='https://pypi.org/project/qdarkstyle/'>qdarkstyle</a> (MIT)<br>"
            "• <a href='https://pypi.org/project/QtAwesome/'>QtAwesome</a> (MIT)<br>"
            "• <a href='https://pypi.org/project/requests/'>requests</a> (Apache Software License (Apache-2.0))<br>"
            "<br>"
            "Xbox Database / Icons are from <a href='https://github.com/MobCat/MobCats-original-xbox-game-list'>MobCats</a><br>"
            "Xbox 360 Icons are from <a href='https://github.com/XboxUnity'>XboxUnity</a>"
            "<br>"
            "<br>"
            "For more information, please visit the respective project pages."
        )

        msg_box.setTextInteractionFlags(Qt.TextInteractionFlag.TextBrowserInteraction)

        msg_box.exec()

    def apply_theme(self):
        """Apply the current theme"""
        stylesheet = self.theme_manager.get_stylesheet()
        self.setStyleSheet(stylesheet)
        self.update_theme_menu_state()

        palette = self.theme_manager.get_palette()

        # Update colours
        if self.theme_manager.should_use_dark_mode():
            self.normal_color = palette.COLOR_TEXT_1
            self.active_color = palette.COLOR_TEXT_1
            self.disabled_color = palette.COLOR_DISABLED
        else:
            self.normal_color = palette.COLOR_BACKGROUND_6
            self.active_color = palette.COLOR_BACKGROUND_6
            self.disabled_color = palette.COLOR_DISABLED

        self.icon_manager.update_all_icons()

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

        # Restore current mode
        self.current_mode = self.settings_manager.load_current_mode()

        # Update platform menu state
        platform_actions = {
            "xbox": self.xbox_action,
            "xbox360": self.xbox360_action,
            "xbla": self.xbla_action,
        }
        if self.current_platform in platform_actions:
            platform_actions[self.current_platform].setChecked(True)

        # Update mode menu state
        if self.current_mode == "ftp":
            self.ftp_mode_action.setChecked(True)
            self.usb_mode_action.setChecked(False)
        else:
            self.ftp_mode_action.setChecked(False)
            self.usb_mode_action.setChecked(True)

        # Update window title
        self.setWindowTitle(
            f"{APP_NAME} - {self.platform_names[self.current_platform]} - v{VERSION}"
        )

        # Restore platform directories
        self.platform_directories = self.settings_manager.load_platform_directories()

        # Load USB target directories
        self.usb_target_directories = (
            self.settings_manager.load_usb_target_directories()
        )

        # Load USB cache directory
        self.usb_cache_directory = self.settings_manager.load_usb_cache_directory()

        # Load USB content directory
        self.usb_content_directory = self.settings_manager.load_usb_content_directory()

        # Set current source directory
        if self.platform_directories[self.current_platform]:
            self.current_directory = self.platform_directories[self.current_platform]
            self.directory_label.setText(self.current_directory)

        # Load FTP settings
        self.ftp_settings = self.settings_manager.load_ftp_settings()
        self.ftp_target_directories = (
            self.settings_manager.load_ftp_target_directories()
        )
        self.ftp_cache_directory = self.settings_manager.load_ftp_cache_directory()
        self.ftp_content_directory = self.settings_manager.load_ftp_content_directory()

        self.xboxunity_settings = self.settings_manager.load_xboxunity_settings()

        # Set current target directory based on mode
        if self.current_mode == "ftp":
            # Don't try to connect immediately on startup - just set the labels
            ftp_target = self.ftp_target_directories[self.current_platform]
            self.current_target_directory = ftp_target
            self.target_directory_label.setText(f"FTP: {ftp_target}")
            self.target_space_label.setText("(FTP)")  # Don't try to get space info yet

            # Test connection in background without blocking startup
            QTimer.singleShot(1000, self._test_ftp_connection_on_startup)

        # Set current target directory based on mode and check availability
        if self.current_mode == "usb":
            target_dir = self.usb_target_directories[self.current_platform]
            text = target_dir
        else:
            target_dir = self.ftp_target_directories[self.current_platform]
            text = f"FTP: {target_dir}"
        if target_dir:
            # Check if target directory is available/mounted
            is_available = self._check_target_directory_availability(target_dir)
            if is_available:
                self.current_target_directory = target_dir
                self.target_directory_label.setText(text)
                self._update_target_space_label(target_dir)
                self.status_manager.show_message(
                    f"Target directory available: {target_dir}"
                )
            else:
                # Target directory not available
                self.current_target_directory = ""
                self.target_directory_label.setText("Target directory not available")
                self._handle_unavailable_target_directory(target_dir)
        else:
            self.target_directory_label.setText("No target directory selected")

        # Update platform label
        self.platform_label.setText(self.platform_names[self.current_platform])

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

        # Save current mode
        self.settings_manager.save_current_mode(self.current_mode)

        # Save current directories for current platform
        if self.current_directory:
            self.platform_directories[self.current_platform] = self.current_directory

        # Save all platform directories
        self.settings_manager.save_platform_directories(self.platform_directories)

        # Save USB target directories
        self.settings_manager.save_usb_target_directories(self.usb_target_directories)

        # Save USB cache directory
        self.settings_manager.save_usb_cache_directory(self.usb_cache_directory)

        # Save USB content directory
        self.settings_manager.save_usb_content_directory(self.usb_content_directory)

        # Save FTP target directories
        self.settings_manager.save_ftp_target_directories(self.ftp_target_directories)

        # Save FTP settings
        self.settings_manager.save_ftp_settings(self.ftp_settings)

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

    def load_title_database(self):
        """Load the appropriate title database based on platform"""
        if self.current_platform == "xbox":
            self.xbox_database_loader.load_database()
        else:
            self.database_loader.load_database()

    def on_database_loaded(self, database: Dict[str, str]):
        """Handle successful database loading"""
        # Enable UI elements
        self.browse_action.setEnabled(True)
        self.browse_target_action.setEnabled(True)
        if self.current_directory:
            self.toolbar_scan_action.setEnabled(True)
            self.start_watching_directory()
            self.scan_directory()

    def on_database_error(self, error_msg: str):
        """Handle database loading error"""
        QMessageBox.critical(
            self, "Database Error", f"Failed to load title database:\n{error_msg}"
        )

        # Enable UI elements even without database
        self.browse_action.setEnabled(True)
        self.browse_target_action.setEnabled(True)
        if self.current_directory:
            self.toolbar_scan_action.setEnabled(True)

    def on_xbox_database_loaded(self, database: Dict[str, Dict[str, str]]):
        """Handle successful Xbox database loading"""
        # Enable UI elements
        self.browse_action.setEnabled(True)
        self.browse_target_action.setEnabled(True)
        if self.current_directory:
            self.toolbar_scan_action.setEnabled(True)
            self.start_watching_directory()
            self.scan_directory()

    def on_xbox_database_error(self, error_msg: str):
        """Handle Xbox database loading error"""
        QMessageBox.warning(
            self,
            "Database Error",
            f"Failed to load Xbox title database:\n{error_msg}\n\nGames will use folder names instead.",
        )

        # Enable UI elements even without database
        self.browse_action.setEnabled(True)
        self.browse_target_action.setEnabled(True)
        if self.current_directory:
            self.toolbar_scan_action.setEnabled(True)

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
            # Clear cache when directory changes
            self._clear_cache_for_directory()
            # Use timer to debounce rapid file system events
            self.scan_timer.stop()
            self.scan_timer.start(self.scan_delay)
            self.status_manager.show_message(
                f"Directory changed - rescanning in {self.scan_delay//1000}s..."
            )

    def delayed_scan(self):
        """Perform delayed scan after directory changes"""
        if self.current_directory and os.path.exists(self.current_directory):
            self.scan_directory()

    def _stop_current_scan(self):
        """Stop any currently running scan"""
        if hasattr(self, "scanner") and self.scanner and self.scanner.isRunning():
            self.scanner.should_stop = True
            self.scanner.terminate()
            self.scanner.wait(1000)  # Wait up to 1 second for clean shutdown

            # Reset UI state
            self.progress_bar.setVisible(False)
            self.toolbar_scan_action.setEnabled(True)
            self.browse_action.setEnabled(True)
            self.browse_target_action.setEnabled(True)

    def scan_directory(self, force: bool = False):
        """Start scanning the selected directory"""
        if not self.current_directory:
            return

        # Stop any existing scan first
        self._stop_current_scan()

        self._is_scanning = True

        # Disconnect the itemChanged signal to prevent firing during bulk operations
        try:
            self.games_table.itemChanged.disconnect(self._on_checkbox_changed)
        except TypeError:
            # Signal wasn't connected, which is fine
            pass

        # Try to load from cache first
        if self._load_scan_cache() and not force:
            self._is_scanning = False
            self.status_manager.show_games_status()

            # Update transferred states in background
            QTimer.singleShot(100, self._rescan_transferred_state)
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
        self.toolbar_scan_action.setEnabled(False)
        self.browse_action.setEnabled(False)
        self.browse_target_action.setEnabled(False)

        # Start scanning thread with appropriate database
        xbox_db = self.xbox_database_loader if self.current_platform == "xbox" else None

        self.scanner = DirectoryScanner(
            self.current_directory,
            self.database_loader.title_database,
            platform=self.current_platform,
            xbox_database=xbox_db,
        )
        self.scanner.progress.connect(self.update_progress)
        self.scanner.game_found.connect(self.add_game)
        self.scanner.finished.connect(self.scan_finished)
        self.scanner.error.connect(self.scan_error)
        self.scanner.start()

        self.status_manager.show_permanent_message("Scanning directory...")

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
        self.status_manager.show_permanent_message(f"Found {len(self.games)} games...")

    def _on_checkbox_changed(self, item):
        """Handle checkbox state changes"""
        if item.column() == 0:  # Only handle checkbox column
            self._update_transfer_button_state()  # Only call this once

            # Update status bar with amount of selected games
            selected_games = 0
            selected_size = 0

            for row in range(self.games_table.rowCount()):
                checkbox_item = self.games_table.item(row, 0)
                if (
                    checkbox_item
                    and checkbox_item.checkState() == Qt.CheckState.Checked
                ):
                    selected_games += 1

                    # Get size from the size column (column 4)
                    size_item = self.games_table.item(row, 4)
                    if size_item:
                        # Try to get the size from UserRole data first (for SizeTableWidgetItem)
                        if hasattr(size_item, "size_bytes"):
                            selected_size += size_item.size_bytes
                        else:
                            # Fallback to UserRole data
                            size_data = size_item.data(Qt.ItemDataRole.UserRole)
                            if size_data is not None:
                                selected_size += size_data

            if selected_games > 0:
                plural = "s" if selected_games > 1 else ""
                self.status_manager.show_permanent_message(
                    f"{selected_games} game{plural} selected ({self._format_size(selected_size)})"
                )
            else:
                self.status_bar.clearMessage()

    def _create_table_items(self, row: int, game_info: GameInfo, show_dlcs: bool):
        """Create and populate table items for a game row"""
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
        self.games_table.setItem(row, col_index, checkbox_item)
        col_index += 1

        # Icon column
        icon_item = QTableWidgetItem("")  # Empty text
        icon_item.setFlags(icon_item.flags() & ~Qt.ItemFlag.ItemIsEditable)

        # Add icon if we have it cached
        if game_info.title_id in self.icon_cache:
            pixmap = self.icon_cache[game_info.title_id]
            # Scale pixmap to proper size
            scaled_pixmap = pixmap.scaled(
                48,
                48,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            icon = QIcon(scaled_pixmap)
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
        size_item = SizeTableWidgetItem(game_info.size_formatted, game_info.size_bytes)
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
            dlc_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.games_table.setItem(row, col_index, dlc_item)
            col_index += 1

        # Transferred status column - centered
        is_transferred = self._check_if_transferred(game_info)
        status_text = "✔️" if is_transferred else "❌"
        status_item = QTableWidgetItem(status_text)
        status_item.setData(Qt.ItemDataRole.UserRole, is_transferred)
        status_item.setFlags(status_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
        status_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        self.games_table.setItem(row, col_index, status_item)
        col_index += 1

        # Source Path column (always last)
        path_item = QTableWidgetItem(game_info.folder_path)
        path_item.setData(Qt.ItemDataRole.UserRole, game_info.folder_path)
        path_item.setFlags(path_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
        self.games_table.setItem(row, col_index, path_item)

    def scan_finished(self):
        """Handle scan completion"""
        self.progress_bar.setVisible(False)
        self.toolbar_scan_action.setEnabled(True)
        self.browse_action.setEnabled(True)
        self.browse_target_action.setEnabled(True)

        self._is_scanning = False

        # Clean up scanner reference
        if hasattr(self, "scanner"):
            self.scanner = None

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

        # Connect the checkbox signal AFTER all items are created
        self.games_table.itemChanged.connect(self._on_checkbox_changed)

        # Apply the previous sort order, or default to Game Name
        if hasattr(self, "current_sort_column") and hasattr(self, "current_sort_order"):
            # Adjust sort column if needed (because we added checkbox column)
            if self.current_sort_column >= 1:
                self.current_sort_column += 1  # Shift right due to checkbox column
            self.games_table.sortItems(
                self.current_sort_column, self.current_sort_order
            )
        else:
            # Default sort (Game Name column is now column 3)
            self.games_table.sortItems(3, Qt.SortOrder.AscendingOrder)

        # Re-apply search filter if search bar is visible
        if self.search_input.isVisible() and self.search_input.text():
            self.filter_games(self.search_input.text())

        # Update transfer button state
        self._update_transfer_button_state()

        # Save scan results to cache
        if game_count > 0:
            self._save_scan_cache()

        # Download icons for games that don't have them cached
        if game_count > 0:
            self.download_missing_icons()

        if game_count == 0:
            self.status_manager.show_permanent_message("Scan complete - no games found")
        else:
            self.status_manager.show_games_status()

    def download_missing_icons(self):
        """Download icons for games that don't have them cached"""
        missing_title_ids = []

        for game in self.games:
            if game.title_id not in self.icon_cache:
                missing_title_ids.append(game.title_id)

        if missing_title_ids:
            self.status_manager.show_message(
                f"Downloading {len(missing_title_ids)} game icons..."
            )

            # Start icon downloader thread
            self.icon_downloader = IconDownloader(
                missing_title_ids, self.current_platform
            )
            self.icon_downloader.icon_downloaded.connect(self.on_icon_downloaded)
            self.icon_downloader.download_failed.connect(self.on_icon_download_failed)
            self.icon_downloader.finished.connect(self.on_icon_download_finished)
            self.icon_downloader.start()

    def on_icon_downloaded(self, title_id: str, pixmap: QPixmap):
        """Handle successful icon download"""
        # Store in cache
        self.icon_cache[title_id] = pixmap

        for row in range(self.games_table.rowCount()):
            title_item = self.games_table.item(row, 2)
            if title_item and title_item.text() == title_id:
                # Set icon in the icon column (column 1)
                icon_item = self.games_table.item(row, 1)
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
        self.status_manager.show_message("Icon downloads completed")

    def setup_table(self):
        """Setup the games table widget"""
        # Determine if we should show DLCs column based on platform
        show_dlcs = self.current_platform in ["xbla"]

        # Set columns and headers
        if show_dlcs:
            self.games_table.setColumnCount(8)
            headers = [
                "",
                "Icon",
                "Title ID",
                "Game Name",
                "Size",
                "DLCs",
                "Transferred",
                "Source Path",
            ]
        else:
            self.games_table.setColumnCount(7)
            headers = [
                "",
                "Icon",
                "Title ID",
                "Game Name",
                "Size",
                "Transferred",
                "Source Path",
            ]

        self.games_table.setHorizontalHeaderLabels(headers)

        # Set custom header to disable sorting on columns 0 and 1 (Select and Icon)
        custom_header = NonSortableHeaderView(
            Qt.Orientation.Horizontal, self.games_table
        )
        self.games_table.setHorizontalHeader(custom_header)

        # Set up custom icon delegate for proper icon rendering
        icon_delegate = IconDelegate()
        self.games_table.setItemDelegateForColumn(
            1, icon_delegate
        )  # Icon column is now 1

        # Configure column widths and resize modes
        self._setup_table_columns(show_dlcs)

        # Configure table appearance and behavior
        self._configure_table_appearance()

        # Load saved table settings
        self._load_table_settings()

    def _setup_table_columns(self, show_dlcs: bool):
        """Setup table column widths and resize modes"""
        header = self.games_table.horizontalHeader()

        header.installEventFilter(self)

        # Select column - fixed width, narrow for checkbox only
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        header.resizeSection(0, 25)  # More reasonable size for checkbox

        # Icon column - fixed width
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Fixed)
        header.resizeSection(1, 64)

        # Other columns
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Interactive)  # Title ID
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.Interactive)  # Game Name
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.Interactive)  # Size

        if show_dlcs:
            header.setSectionResizeMode(5, QHeaderView.ResizeMode.Interactive)  # DLCs
            header.setSectionResizeMode(
                6, QHeaderView.ResizeMode.Interactive
            )  # Transferred
            header.setSectionResizeMode(
                7, QHeaderView.ResizeMode.Stretch
            )  # Source Path
        else:
            header.setSectionResizeMode(
                5, QHeaderView.ResizeMode.Interactive
            )  # Transferred
            header.setSectionResizeMode(
                6, QHeaderView.ResizeMode.Stretch
            )  # Source Path

        # Set minimum column widths
        header.setMinimumSectionSize(30)  # More reasonable minimum

        # Set initial column widths
        header.resizeSection(2, 100)  # Title ID
        header.resizeSection(3, 300)  # Game Name
        header.resizeSection(4, 100)  # Size
        if show_dlcs:
            header.resizeSection(5, 60)  # DLCs
            header.resizeSection(6, 100)  # Transferred
        else:
            header.resizeSection(5, 100)  # Transferred

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

        # Enable sorting and indicators
        header.setSortIndicatorShown(True)
        header.setSectionsClickable(True)

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
            for column_index, width in column_widths.items():
                if column_index < header.count():  # Make sure column exists
                    header.resizeSection(column_index, width)

            # Restore sort settings
            self.games_table.sortItems(sort_column, Qt.SortOrder(sort_order))

        except Exception as e:
            print(f"Error loading table settings: {e}")
            # If loading fails, use defaults
            self.games_table.sortItems(
                3, Qt.SortOrder.AscendingOrder
            )  # Game Name column

    def create_remove_action(self, row, show_dlcs):
        if show_dlcs:
            folder_item = self.games_table.item(row, 7)
        else:
            folder_item = self.games_table.item(row, 6)
        if folder_item:
            folder_path = folder_item.text()
            folder_name = os.path.basename(folder_path)

        return lambda: self.remove_game_from_target(
            title_id=self.games_table.item(row, 2).text(),
            game_name=self.games_table.item(row, 3).text(),
            folder_name=folder_name,
        )

    def show_context_menu(self, position):
        """Show context menu when right-clicking on table"""
        item = self.games_table.itemAt(position)
        if item is None:
            return

        row = item.row()
        show_dlcs = self.current_platform in ["xbla"]
        folder_path_column = 7 if show_dlcs else 6  # Adjusted for new columns

        # Get the Source Path from the appropriate column
        folder_item = self.games_table.item(row, folder_path_column)
        if folder_item is None:
            return

        # Get the actual folder path from UserRole data, not display text
        folder_path = folder_item.data(Qt.ItemDataRole.UserRole)
        if not folder_path:
            folder_path = folder_item.text()  # Fallback to text if UserRole is empty

        title_id = self.games_table.item(row, 2).text()

        # Create context menu
        menu = QMenu(self)

        # Add "Open Folder" action
        open_folder_action = menu.addAction("Open Folder")
        open_folder_action.triggered.connect(
            lambda: SystemUtils.open_folder_in_explorer(folder_path, self)
        )

        # Add "Copy Source Path" action
        copy_path_action = menu.addAction("Copy Source Path")
        copy_path_action.triggered.connect(
            lambda: SystemUtils.copy_to_clipboard(folder_path)
        )

        # Add "Copy Title ID" action
        copy_title_id_action = menu.addAction("Copy Title ID")
        copy_title_id_action.triggered.connect(
            lambda: SystemUtils.copy_to_clipboard(title_id)
        )

        # Add "Title Updates" action
        title_updates_action = menu.addAction("Title Updates")
        title_updates_action.triggered.connect(
            lambda: self._show_title_updates_dialog(folder_path, title_id)
        )

        # Add separator
        menu.addSeparator()

        # Add "Transfer" action
        transfer_action = menu.addAction("Transfer")
        transfer_action.triggered.connect(lambda: self._transfer_single_game(row))

        # Add "Remove from Target" action
        remove_action = menu.addAction("Remove from Target")
        remove_action.triggered.connect(self.create_remove_action(row, show_dlcs))

        # Show the menu at the cursor position
        menu.exec(self.games_table.mapToGlobal(position))

    def _show_title_updates_dialog(self, folder_path: str, title_id: str):
        """Show dialog with title updates information"""
        if not title_id:
            return

        media_id = self._get_media_id_for_game(folder_path, title_id)

        if not media_id:
            QMessageBox.information(
                self,
                "Title Updates",
                f"No media ID found for Title ID: {title_id}",
            )
            return

        updates = self.xboxunity.search_title_updates(
            media_id=media_id, title_id=title_id
        )
        if not updates:
            QMessageBox.information(
                self,
                "Title Updates",
                f"No title updates found for Title ID: {title_id}",
            )
            return

        dialog = XboxUnityTitleUpdatesDialog(self, title_id, updates)

        # Connect download signals to main window progress display
        dialog.download_started.connect(self._on_tu_download_started)
        dialog.download_progress.connect(self._on_tu_download_progress)
        dialog.download_complete.connect(self._on_tu_download_complete)
        dialog.download_error.connect(self._on_tu_download_error)

        dialog.exec()

    def batch_download_title_updates(self):
        """Batch download missing title updates for all games in target"""
        from workers.batch_tu_processor import BatchTitleUpdateProcessor

        # Get all games in target directory
        target_games = self._get_all_target_games()

        if not target_games:
            QMessageBox.information(
                self,
                "Batch Title Updates",
                "No games found in target directory.",
            )
            return

        # Confirm with user
        reply = QMessageBox.question(
            self,
            "Batch Title Updates",
            f"This will check for missing title updates for {len(target_games)} games.\n"
            "Only the latest missing update for each game will be downloaded.\n\n"
            "Continue?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.Yes,
        )

        if reply != QMessageBox.StandardButton.Yes:
            return

        # Create progress dialog
        self.batch_progress_dialog = QProgressDialog(
            "Initializing batch title update download...",
            "Cancel",
            0,
            len(target_games),
            self,
        )
        self.batch_progress_dialog.setWindowTitle("Batch Title Updates")
        self.batch_progress_dialog.setModal(True)
        self.batch_progress_dialog.show()

        # Create and setup worker
        self.batch_tu_processor = BatchTitleUpdateProcessor()
        self.batch_tu_processor.setup_batch(target_games, self.current_mode)

        # Connect signals
        self.batch_tu_processor.progress_update.connect(self._on_batch_progress)
        self.batch_tu_processor.game_started.connect(self._on_batch_game_started)
        self.batch_tu_processor.game_completed.connect(self._on_batch_game_completed)
        self.batch_tu_processor.update_downloaded.connect(
            self._on_batch_update_downloaded
        )
        self.batch_tu_processor.batch_complete.connect(self._on_batch_complete)
        self.batch_tu_processor.error_occurred.connect(self._on_batch_error)

        # Connect cancel button
        self.batch_progress_dialog.canceled.connect(
            self.batch_tu_processor.stop_processing
        )
        self.batch_progress_dialog.canceled.connect(self._on_batch_cancelled)

        # Disable toolbar actions during batch processing
        self.toolbar_transfer_action.setEnabled(False)
        self.toolbar_remove_action.setEnabled(False)
        self.toolbar_batch_tu_action.setEnabled(False)
        self.browse_action.setEnabled(False)
        self.browse_target_action.setEnabled(False)

        # Start processing
        self.batch_tu_processor.start()

    def _get_all_target_games(self):
        """Get all games in the target directory"""
        games = []

        if not self.current_target_directory:
            return games

        if self.current_mode == "ftp":
            # Handle FTP directory listing
            ftp_client = FTPClient()

            try:
                success, message = ftp_client.connect(
                    self.ftp_settings["host"],
                    self.ftp_settings["username"],
                    self.ftp_settings["password"],
                    self.ftp_settings.get("port", 21),
                    self.ftp_settings.get("use_tls", False),
                )

                if not success:
                    print(f"[ERROR] Failed to connect to FTP server: {message}")
                    return games

                # List all directories in the target directory
                success, items, error_msg = ftp_client.list_directory(
                    self.current_target_directory
                )

                if not success:
                    print(f"[ERROR] Failed to list FTP directory: {error_msg}")
                    return games

                for item in items:
                    # Only process directories
                    if item["is_directory"]:
                        folder_name = item["name"]
                        folder_path = item["full_path"]

                        # Try to get title ID and game name from the folder
                        title_id = self._extract_title_id_ftp(
                            folder_name, folder_path, ftp_client
                        )
                        if title_id:
                            game_name = self._get_game_display_name(
                                folder_name, title_id
                            )
                            games.append(
                                {
                                    "name": game_name,
                                    "title_id": title_id,
                                    "folder_path": folder_path,
                                    "folder_name": folder_name,
                                }
                            )

            except Exception as e:
                print(f"[ERROR] Failed to scan FTP target directory: {e}")
            finally:
                ftp_client.disconnect()
        else:
            # Handle local directory listing (USB mode)
            if not os.path.exists(self.current_target_directory):
                return games

            try:
                # List all directories in the target directory
                for item in os.listdir(self.current_target_directory):
                    item_path = os.path.join(self.current_target_directory, item)

                    # Only process directories
                    if os.path.isdir(item_path):
                        folder_name = item
                        folder_path = item_path

                        # Try to get title ID and game name from the folder
                        title_id = self._extract_title_id(folder_name, folder_path)
                        if title_id:
                            game_name = self._get_game_display_name(
                                folder_name, title_id
                            )
                            games.append(
                                {
                                    "name": game_name,
                                    "title_id": title_id,
                                    "folder_path": folder_path,
                                    "folder_name": folder_name,
                                }
                            )
            except Exception as e:
                print(f"[ERROR] Failed to scan target directory: {e}")

        return games

    def _extract_title_id(self, folder_name: str, folder_path: str):
        """Extract title ID from folder name or path"""
        # For Xbox 360, folder name is the title ID
        if self.current_platform == "xbox360":
            return folder_name.upper()

        # For Xbox, need to extract from internal structure
        elif self.current_platform == "xbox":
            try:
                # Look for default.xbe or header files
                from pathlib import Path

                # Check for GoD structure
                god_header_path = Path(folder_path) / "00007000"
                if god_header_path.exists():
                    header_files = list(god_header_path.glob("*"))
                    if header_files:
                        # Extract title ID from header file name or content
                        # This is a simplified approach - might need enhancement
                        header_name = header_files[0].name
                        if len(header_name) == 8:  # Title ID length
                            return header_name.upper()

                # Check for default.xbe
                xbe_path = Path(folder_path) / "default.xbe"
                if xbe_path.exists():
                    # Would need to parse XBE file for title ID
                    # For now, use folder name if it looks like a title ID
                    if len(folder_name) == 8 and folder_name.isalnum():
                        return folder_name.upper()

            except Exception:
                pass

        return None

    def _extract_title_id_ftp(
        self, folder_name: str, folder_path: str, ftp_client: FTPClient
    ):
        """Extract title ID from folder name or path for FTP connections"""
        # For Xbox 360, folder name is the title ID
        if self.current_platform == "xbox360":
            return folder_name.upper()

        # For Xbox, need to extract from internal structure
        elif self.current_platform == "xbox":
            try:
                # Check for GoD structure
                god_header_path = f"{folder_path.rstrip('/')}/00007000"
                if ftp_client.directory_exists(god_header_path):
                    # List contents of 00007000 directory to find header files
                    success, items, error_msg = ftp_client.list_directory(
                        god_header_path
                    )
                    if success and items:
                        # Look for header files (should be hex filename)
                        for item in items:
                            if not item["is_directory"]:
                                header_name = item["name"]
                                if len(header_name) == 8:  # Title ID length
                                    return header_name.upper()

                # Check for default.xbe
                try:
                    # Try to check if file exists by listing directory contents
                    success, items, error_msg = ftp_client.list_directory(folder_path)
                    if success:
                        for item in items:
                            if (
                                not item["is_directory"]
                                and item["name"].lower() == "default.xbe"
                            ):
                                # Would need to parse XBE file for title ID
                                # For now, use folder name if it looks like a title ID
                                if len(folder_name) == 8 and folder_name.isalnum():
                                    return folder_name.upper()
                                break
                except Exception:
                    pass

            except Exception:
                pass

        return None

    def _get_game_display_name(self, folder_name: str, title_id: str) -> str:
        """Get display name for a game based on folder name and title ID"""
        # Try to get name from loaded database
        try:
            if hasattr(self, "database_loader") and self.database_loader:
                game_name = self.database_loader.title_database.get(
                    title_id, folder_name
                )
                if game_name != folder_name:  # Found in database
                    return game_name
        except Exception:
            pass

        # Fallback to folder name
        return folder_name

    def _get_media_id_for_game(self, folder_path: str, title_id: str) -> str:
        """Get media ID for a game from its local folder only (used for context menu)"""
        try:
            # Always use local mode for context menu operations
            # First check if this is a GoD game (no .xex file in root)
            folder_path_obj = Path(folder_path)
            xex_files = list(folder_path_obj.glob("*.xex"))

            if xex_files:
                print(
                    "[DEBUG] Game appears to be ISO format (.xex found), skipping GoD media ID extraction"
                )
                return None

            god_header_path = folder_path_obj / "00007000"
            header_files = list(god_header_path.glob("*"))

            if not header_files:
                return None

            # Filter for potential header files (should be hex and reasonable length)
            for file_path in header_files:
                if file_path.is_file():
                    filename = file_path.name
                    # Check for hex filename (8-20 characters for various formats)
                    if (
                        len(filename) >= 8
                        and len(filename) <= 20
                        and all(c in "0123456789ABCDEFabcdef" for c in filename)
                    ):
                        media_id = self.xboxunity.get_media_id(str(file_path))
                        return media_id

            return None

        except Exception as e:
            print(f"[ERROR] Local media ID extraction failed: {e}")
            return None

    def _on_batch_progress(self, current: int, total: int):
        """Handle batch processing progress"""
        if hasattr(self, "batch_progress_dialog"):
            self.batch_progress_dialog.setValue(current)

    def _on_batch_game_started(self, game_name: str):
        """Handle batch game processing started"""
        if hasattr(self, "batch_progress_dialog"):
            self.batch_progress_dialog.setLabelText(f"Processing: {game_name}")

    def _on_batch_game_completed(self, game_name: str, updates_found: int):
        """Handle batch game processing completed"""
        return

    def _on_batch_update_downloaded(self, game_name: str, version: str, file_path: str):
        """Handle successful update download"""

    def _on_batch_complete(self, total_games: int, total_updates: int):
        """Handle batch processing completion"""
        if hasattr(self, "batch_progress_dialog"):
            self.batch_progress_dialog.close()

        # Re-enable toolbar actions
        self.toolbar_transfer_action.setEnabled(True)
        self.toolbar_remove_action.setEnabled(True)
        self.toolbar_batch_tu_action.setEnabled(True)
        self.browse_action.setEnabled(True)
        self.browse_target_action.setEnabled(True)

        # Show completion message
        QMessageBox.information(
            self,
            "Batch Title Updates Complete",
            f"Processed {total_games} games.\n"
            f"Downloaded {total_updates} title updates.\n\n"
            f"See 'batch_tu_download_log.txt' for detailed results.",
        )

    def _on_batch_error(self, error_message: str):
        """Handle batch processing error"""
        if hasattr(self, "batch_progress_dialog"):
            self.batch_progress_dialog.close()

        # Re-enable toolbar actions
        self.toolbar_transfer_action.setEnabled(True)
        self.toolbar_remove_action.setEnabled(True)
        self.toolbar_batch_tu_action.setEnabled(True)
        self.browse_action.setEnabled(True)
        self.browse_target_action.setEnabled(True)

        QMessageBox.critical(
            self,
            "Batch Processing Error",
            f"An error occurred during batch processing:\n\n{error_message}",
        )

    def _on_batch_cancelled(self):
        """Handle batch processing cancellation"""
        # Re-enable toolbar actions
        self.toolbar_transfer_action.setEnabled(True)
        self.toolbar_remove_action.setEnabled(True)
        self.toolbar_batch_tu_action.setEnabled(True)
        self.browse_action.setEnabled(True)
        self.browse_target_action.setEnabled(True)

        self.status_manager.show_message("Batch title update download cancelled")

    def remove_game_from_target(
        self, title_id: str, game_name: str, folder_name: str = ""
    ):
        remove_target = title_id if self.current_platform != "xbox" else folder_name
        if self.current_mode == "ftp":
            target_path = f"{self.current_target_directory.rstrip('/')}/{remove_target}"
        else:
            target_path = str(Path(self.current_target_directory) / remove_target)

        msg_box = QMessageBox(self)
        msg_box.setWindowTitle("Confirm Removal")
        msg_box.setText(
            f"Are you sure you want to remove {game_name}?\n\n{target_path}"
        )
        msg_box.setStandardButtons(
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel
        )
        msg_box.setDefaultButton(QMessageBox.StandardButton.Cancel)

        if msg_box.exec() == QMessageBox.StandardButton.Yes:
            self._remove_game_from_target(title_id, game_name, folder_name)

    def _remove_game_from_target(
        self, title_id: str, game_name: str, folder_name: str = ""
    ):
        """Remove game from target directory"""
        if title_id and game_name:
            remove_target = title_id if self.current_platform != "xbox" else folder_name
            if self.current_mode == "ftp":
                # Handle FTP removal
                target_path = (
                    f"{self.current_target_directory.rstrip('/')}/{remove_target}"
                )

                ftp_client = FTPClient()

                try:
                    success, message = ftp_client.connect(
                        self.ftp_settings["host"],
                        self.ftp_settings["username"],
                        self.ftp_settings["password"],
                        self.ftp_settings.get("port", 21),
                        self.ftp_settings.get("use_tls", False),
                    )

                    if not success:
                        QMessageBox.critical(
                            self,
                            "FTP Connection Error",
                            f"Could not connect to FTP server:\n{message}\n\n"
                            "Please check your FTP settings.",
                        )
                        return False

                    # Remove directory recursively
                    success, message = ftp_client.remove_directory(target_path)

                    if success:
                        self.status_manager.show_message(
                            f"Removed {game_name} from FTP server"
                        )

                        # Update transferred status in table
                        for row in range(self.games_table.rowCount()):
                            title_item = self.games_table.item(row, 2)
                            if title_item and title_item.text() == title_id:
                                show_dlcs = self.current_platform in ["xbla"]
                                status_column = 6 if show_dlcs else 5
                                status_item = self.games_table.item(row, status_column)
                                if status_item:
                                    status_item.setText("❌")
                                    status_item.setData(Qt.ItemDataRole.UserRole, False)
                                break
                    else:
                        QMessageBox.warning(
                            self,
                            "FTP Removal Failed",
                            f"Failed to remove {game_name} from FTP server:\n{message}",
                        )

                except Exception as e:
                    QMessageBox.critical(
                        self,
                        "FTP Error",
                        f"An error occurred while removing {game_name}:\n{str(e)}",
                    )
                finally:
                    ftp_client.disconnect()

            else:
                # USB/local mode - existing code
                target_path = Path(self.current_target_directory) / remove_target

                try:
                    if target_path.exists():
                        shutil.rmtree(target_path, ignore_errors=True)
                        self.status_manager.show_message(
                            f"Removed {game_name} from target directory"
                        )

                        # Update transferred status in table
                        for row in range(self.games_table.rowCount()):
                            title_item = self.games_table.item(row, 2)
                            if title_item and title_item.text() == title_id:
                                show_dlcs = self.current_platform in ["xbla"]
                                status_column = 6 if show_dlcs else 5
                                status_item = self.games_table.item(row, status_column)
                                if status_item:
                                    status_item.setText("❌")
                                    status_item.setData(Qt.ItemDataRole.UserRole, False)
                                break
                    else:
                        QMessageBox.warning(
                            self,
                            "Directory Not Found",
                            f"Game directory not found:\n{target_path}",
                        )
                except Exception as e:
                    QMessageBox.critical(
                        self,
                        "Removal Error",
                        f"Failed to remove {game_name}:\n{str(e)}",
                    )

    def _toggle_row_selection(self, row: int):
        """Toggle the selection state of a row"""
        checkbox_item = self.games_table.item(row, 0)
        if checkbox_item:
            current_state = checkbox_item.checkState()
            new_state = (
                Qt.CheckState.Unchecked
                if current_state == Qt.CheckState.Checked
                else Qt.CheckState.Checked
            )
            checkbox_item.setCheckState(new_state)

    def scan_error(self, error_msg: str):
        """Handle scan error"""
        self.progress_bar.setVisible(False)
        self.toolbar_scan_action.setEnabled(True)
        self.browse_action.setEnabled(True)
        self.browse_target_action.setEnabled(True)

        # Clean up scanner reference
        if hasattr(self, "scanner"):
            self.scanner = None

        QMessageBox.critical(
            self, "Scan Error", f"An error occurred while scanning:\n{error_msg}"
        )

        self.status_manager.show_permanent_message("Scan failed")

    def closeEvent(self, event):
        """Handle application close event"""
        # Stop file system watcher
        self.stop_watching_directory()

        # Stop any running scans
        self._stop_current_scan()

        # Stop any running icon downloads
        if hasattr(self, "icon_downloader") and self.icon_downloader.isRunning():
            self.icon_downloader.terminate()
            self.icon_downloader.wait()

        # Clean up tools watcher
        if hasattr(self, "tools_watcher"):
            self.tools_watcher.removePaths(
                self.tools_watcher.files() + self.tools_watcher.directories()
            )

        self.save_settings()
        event.accept()

    def clear_search(self):
        """Clear the search input and show all games"""
        self.search_input.clear()
        self.filter_games("")

    def filter_games(self, search_text: str):
        """Filter games based on search text"""
        search_text = search_text.lower().strip()

        # If any text is entered, show the clear button
        if search_text:
            self.search_clear_button.setVisible(True)
        else:
            self.search_clear_button.setVisible(False)

        # Show all rows if search is empty
        if not search_text:
            for row in range(self.games_table.rowCount()):
                self.games_table.setRowHidden(row, False)
            return

        # Filter rows based on search text
        visible_count = 0
        for row in range(self.games_table.rowCount()):
            # Get title ID (column 2) and game name (column 3) - adjusted for checkbox column
            title_id_item = self.games_table.item(row, 2)
            name_item = self.games_table.item(row, 3)

            title_id = title_id_item.text().lower() if title_id_item else ""
            name = name_item.text().lower() if name_item else ""

            # Check if search text matches title ID or name
            matches = search_text in title_id or search_text in name

            self.games_table.setRowHidden(row, not matches)
            if matches:
                visible_count += 1

        plural = "s" if visible_count > 1 else ""
        self._update_search_status(f" - {visible_count} game{plural} match search")

    def _update_search_status(self, suffix: str = ""):
        """Update status bar with search results"""
        if hasattr(self, "games") and self.games:
            game_count = len(self.games)
            total_size = sum(game.size_bytes for game in self.games)

            # Format total size
            size_formatted = total_size
            for unit in ["B", "KB", "MB", "GB", "TB"]:
                if size_formatted < 1024.0:
                    break
                size_formatted /= 1024.0

            plural = "s" if game_count > 1 else ""
            base_message = f"{game_count:,} game{plural} ({size_formatted:.1f} {unit})"
            self.status_manager.show_message(base_message + suffix)

    def _check_target_directory_availability(self, target_path: str) -> bool:
        """Check if target directory is available/mounted"""
        try:
            if not target_path:
                return False

            # Handle FTP mode
            if self.current_mode == "ftp":
                ftp_client = FTPClient()
                try:
                    # Try to connect first
                    success, message = ftp_client.connect(
                        self.ftp_settings["host"],
                        self.ftp_settings["username"],
                        self.ftp_settings["password"],
                        self.ftp_settings.get("port", 21),
                        self.ftp_settings.get("use_tls", False),
                    )

                    if not success:
                        print(f"FTP connection failed: {message}")
                        return False

                    # Check if directory exists
                    return ftp_client.directory_exists(target_path)

                except Exception as e:
                    print(f"FTP error checking target directory: {e}")
                    return False
                finally:
                    ftp_client.disconnect()
            else:
                # USB/local mode - existing logic
                if not os.path.exists(target_path):
                    return False

                # Try to access the directory to ensure it's mounted and readable
                try:
                    os.listdir(target_path)
                    return True
                except (OSError, PermissionError):
                    return False

        except Exception:
            return False

    def _check_cache_directory_availability(self, target_path: str) -> bool:
        """Check if cache directory is available/mounted"""
        try:
            if not target_path:
                return False

            # Handle FTP mode
            if self.current_mode == "ftp":
                ftp_client = FTPClient()
                try:
                    # Try to connect first
                    success, message = ftp_client.connect(
                        self.ftp_settings["host"],
                        self.ftp_settings["username"],
                        self.ftp_settings["password"],
                        self.ftp_settings.get("port", 21),
                        self.ftp_settings.get("use_tls", False),
                    )

                    if not success:
                        print(f"FTP connection failed: {message}")
                        return False

                    # Check if directory exists
                    return ftp_client.directory_exists(target_path)

                except Exception as e:
                    print(f"FTP error checking cache directory: {e}")
                    return False
                finally:
                    ftp_client.disconnect()
            else:
                # USB/local mode - existing logic
                if not os.path.exists(target_path):
                    return False

                # Try to access the directory to ensure it's mounted and readable
                try:
                    os.listdir(target_path)
                    return True
                except (OSError, PermissionError):
                    return False

        except Exception:
            return False

    def _check_content_directory_availability(self, target_path: str) -> bool:
        """Check if content directory is available/mounted"""
        try:
            if not target_path:
                return False

            # Handle FTP mode
            if self.current_mode == "ftp":
                ftp_client = FTPClient()
                try:
                    # Try to connect first
                    success, message = ftp_client.connect(
                        self.ftp_settings["host"],
                        self.ftp_settings["username"],
                        self.ftp_settings["password"],
                        self.ftp_settings.get("port", 21),
                        self.ftp_settings.get("use_tls", False),
                    )

                    if not success:
                        print(f"FTP connection failed: {message}")
                        return False

                    # Check if directory exists
                    return ftp_client.directory_exists(target_path)

                except Exception as e:
                    print(f"FTP error checking cache directory: {e}")
                    return False
                finally:
                    ftp_client.disconnect()
            else:
                # USB/local mode - existing logic
                if not os.path.exists(target_path):
                    return False

                # Try to access the directory to ensure it's mounted and readable
                try:
                    os.listdir(target_path)
                    return True
                except (OSError, PermissionError):
                    return False

        except Exception:
            return False

    def _handle_unavailable_target_directory(self, target_path: str):
        """Handle when target directory is not available on startup"""
        platform_name = self.platform_names[self.current_platform]

        # Show warning message
        msg_box = QMessageBox(self)
        msg_box.setWindowTitle("Target Directory Unavailable")
        msg_box.setIcon(QMessageBox.Icon.Warning)
        msg_box.setText(f"Target directory for {platform_name} is not available:")
        msg_box.setInformativeText(
            f"Path: {target_path}\n\n"
            "This could mean:\n"
            "• USB drive is not connected\n"
            "• Network drive is not mounted\n"
            "• Directory has been moved or deleted\n"
            "• Insufficient permissions\n\n"
            "Please connect your target device or select a new target directory."
        )
        msg_box.setStandardButtons(
            QMessageBox.StandardButton.Ok | QMessageBox.StandardButton.Ignore
        )
        msg_box.setDefaultButton(QMessageBox.StandardButton.Ok)

        result = msg_box.exec()

        if result == QMessageBox.StandardButton.Ok:
            # Offer to select new target directory
            self._prompt_for_new_target_directory()
        else:
            # User chose to ignore - show message in status bar
            self.status_manager.show_message(
                f"Warning: Target directory not available - {target_path}", 10000
            )

    def _prompt_for_new_target_directory(self):
        """Prompt user to select a new target directory"""
        platform_name = self.platform_names[self.current_platform]

        msg_box = QMessageBox(self)
        msg_box.setWindowTitle("Select New Target Directory")
        msg_box.setText(
            f"Would you like to select a new target directory for {platform_name}?"
        )
        msg_box.setStandardButtons(
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        msg_box.setDefaultButton(QMessageBox.StandardButton.Yes)

        if msg_box.exec() == QMessageBox.StandardButton.Yes:
            self.browse_target_directory()
        else:
            self.status_manager.show_message("No target directory selected", 5000)

    def _update_target_space_label(self, directory_path: str):
        """Update the target space label with free space information"""
        if self.current_mode == "ftp":
            self.target_space_label.setText("")
            return

        free_space = self._get_available_disk_space(directory_path)
        if free_space is not None:
            free_gb = free_space // (2**30)
            self.target_space_label.setText(f"({free_gb} GB Free)")
        else:
            self.target_space_label.setText("(Free space unknown)")

    def _on_item_changed(self, item):
        if item.column() == 0:
            self.games_table.horizontalHeader().updateSection(0)

    def _table_mouse_move_event(self, event):
        """Custom mouse move event for the games table"""
        index = self.games_table.indexAt(event.pos())
        if index.isValid() and index.column() == 0:  # Check if over checkbox column
            self.games_table.setCursor(Qt.CursorShape.PointingHandCursor)
        else:
            self.games_table.setCursor(Qt.CursorShape.ArrowCursor)
        super(QTableWidget, self.games_table).mouseMoveEvent(event)

    def _check_for_updates(self):
        """Check for application updates in the background"""
        # Set checking for updates status
        self.status_manager.show_message("Checking for updates...")

        update_available, download_url = check_for_update()
        if update_available:
            # add update button pinned to right of status bar
            self._add_update_button(download_url)

    def _add_update_button(self, download_url: str):
        """Add an update button to the status bar"""
        # Check if button already exists
        if hasattr(self, "update_button"):
            return

        self.update_button = QPushButton("Update Available")
        self.update_button.setIcon(
            qta.icon(
                "fa6s.rotate",
                color=self.normal_color,
                color_active=self.active_color,
                color_disabled=self.disabled_color,
            )
        )
        self.update_button.setToolTip("A new version is available. Click to update.")
        self.update_button.clicked.connect(
            lambda: self._on_update_button_clicked(download_url)
        )
        self.update_button.setCursor(Qt.CursorShape.PointingHandCursor)

        # Add to status bar on the right side
        self.status_bar.addPermanentWidget(self.update_button)

    def _on_update_button_clicked(self, download_url: str):
        """Handle update button click"""
        update(download_url)

    def _has_sufficient_space(self, game: GameInfo) -> bool:
        """Check if there is enough space to transfer the game"""
        if self.current_mode == "ftp":
            # For FTP, we cannot reliably check space, so assume true
            return True

        free_space = self._get_available_disk_space(self.current_target_directory)
        if free_space is None:
            return False

        return free_space >= game.size_bytes

    def _transfer_single_game(self, row: int):
        """Transfer a single game by row index"""
        # First ensure the game is selected
        checkbox_item = self.games_table.item(row, 0)
        if checkbox_item:
            checkbox_item.setCheckState(Qt.CheckState.Checked)

        # Get the game info for this specific row
        title_id_item = self.games_table.item(row, 2)
        if title_id_item:
            title_id = title_id_item.text()

            # Find the game in our games list
            selected_game = None
            for game in self.games:
                if game.title_id == title_id:
                    selected_game = game
                    break

            # If we found the selected game and there's enough space, start transfer
            if selected_game and self._has_sufficient_space(selected_game):
                # Start transfer with just this one game
                self._start_transfer([selected_game])

    def show_ftp_settings(self):
        """Show FTP settings dialog"""
        dialog = FTPSettingsDialog(self, self.ftp_settings)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.ftp_settings = dialog.get_settings()
            self.settings_manager.save_ftp_settings(self.ftp_settings)
            self.status_manager.show_message("FTP settings saved")

    def show_xboxunity_settings(self):
        """Show XboxUnity settings dialog"""
        dialog = XboxUnitySettingsDialog(self, self.xboxunity_settings)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.xboxunity_settings = dialog.get_settings()
            self.settings_manager.save_xboxunity_settings(self.xboxunity_settings)
            self.status_manager.show_message("XboxUnity settings saved")

    def browse_ftp_target_directory(self):
        """Browse FTP server for target directory"""
        if not self.ftp_settings or not self.ftp_settings.get("host"):
            QMessageBox.warning(
                self,
                "FTP Settings Required",
                "Please configure FTP settings first (File → FTP Settings).",
            )
            self.show_ftp_settings()
            return

        dialog = FTPBrowserDialog(self, self.ftp_settings)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            selected_path = dialog.get_selected_path()
            self.ftp_target_directories[self.current_platform] = selected_path
            self.current_target_directory = selected_path
            self.target_directory_label.setText(f"FTP: {selected_path}")
            self.target_space_label.setText("(FTP)")

            self.settings_manager.save_ftp_target_directories(
                self.ftp_target_directories
            )
            self._update_transfer_button_state()

            self.status_manager.show_message(
                f"FTP target directory set: {selected_path}"
            )

    def browse_ftp_cache_directory(self):
        """Browse FTP server for cache directory"""
        if not self.ftp_settings or not self.ftp_settings.get("host"):
            QMessageBox.warning(
                self,
                "FTP Settings Required",
                "Please configure FTP settings first (File → FTP Settings).",
            )
            self.show_ftp_settings()
            return

        dialog = FTPBrowserDialog(self, self.ftp_settings)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            selected_path = dialog.get_selected_path()
            self.ftp_cache_directory = selected_path
            self.current_cache_directory = selected_path

            self.settings_manager.save_ftp_cache_directory(self.ftp_cache_directory)

            self.status_manager.show_message(
                f"FTP cache directory set: {selected_path}"
            )

    def browse_ftp_content_directory(self):
        """Browse FTP server for content directory"""
        if not self.ftp_settings or not self.ftp_settings.get("host"):
            QMessageBox.warning(
                self,
                "FTP Settings Required",
                "Please configure FTP settings first (File → FTP Settings).",
            )
            self.show_ftp_settings()
            return

        dialog = FTPBrowserDialog(self, self.ftp_settings)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            selected_path = dialog.get_selected_path()
            self.ftp_content_directory = selected_path
            self.current_content_directory = selected_path

            self.settings_manager.save_ftp_content_directory(self.ftp_content_directory)

            self.status_manager.show_message(
                f"FTP content directory set: {selected_path}"
            )

    def browse_for_iso(self):
        """Browse for ISO/ZIP files to extract"""
        file_dialog = QFileDialog(self)
        file_dialog.setWindowTitle("Select ISO/ZIP File(s)")
        file_dialog.setNameFilter("Game Files (*.iso *.zip);;")
        file_dialog.setFileMode(QFileDialog.FileMode.ExistingFiles)

        if file_dialog.exec() == QFileDialog.DialogCode.Accepted:
            selected_files = file_dialog.selectedFiles()
            if selected_files:
                # Process files sequentially to avoid thread conflicts
                self._extract_multiple_files(selected_files)

    def _extract_multiple_files(self, file_paths):
        """Extract multiple ISO/ZIP files sequentially"""
        total_files = len(file_paths)

        if total_files == 1:
            # Single file - use existing logic
            self.iso_path = file_paths[0]
            self._extract_iso()
            return

        # Multiple files - show confirmation and set up batch processing
        msg_box = QMessageBox(self)
        msg_box.setWindowTitle("Extract Multiple Files")
        msg_box.setText(f"Extract {total_files} files?")
        msg_box.setInformativeText("Each file will be extracted to its own folder.")
        msg_box.setStandardButtons(
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        msg_box.setDefaultButton(QMessageBox.StandardButton.Yes)

        if msg_box.exec() == QMessageBox.StandardButton.Yes:
            self._start_batch_extraction(file_paths)

    def _start_batch_extraction(self, file_paths):
        """Start batch extraction of multiple files"""
        self.current_extraction_batch = file_paths
        self.current_extraction_batch_index = 0
        self.total_extraction_batch_files = len(file_paths)

        # Show progress
        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(0)

        self.status_manager.show_message(
            f"Extracting file 1 of {self.total_extraction_batch_files}..."
        )

        # Start with first file
        self._extract_next_batch_file()

    def _extract_next_batch_file(self):
        """Extract the next file in the batch"""
        if self.current_extraction_batch_index >= len(self.current_extraction_batch):
            # Batch complete
            self._on_batch_extraction_complete()
            return

        self.iso_path = self.current_extraction_batch[
            self.current_extraction_batch_index
        ]

        # Update status
        current_file = self.current_extraction_batch_index + 1
        filename = os.path.basename(self.iso_path)
        self.status_manager.show_message(
            f"Extracting file {current_file} of {self.total_extraction_batch_files}: {filename}"
        )

        # Extract current file - this will call the sequential extraction logic
        self._extract_iso()

    def _extract_iso(self):
        """Extract ISO with extract-xiso.exe"""
        if not self.iso_path:
            QMessageBox.warning(
                self, "No files selected", "Please select an ISO/ZIP file to extract."
            )
            return

        # If a zip file, extract it first
        if self.iso_path.lower().endswith(".zip"):
            self._extract_zip_then_iso(self.iso_path)
        else:
            # ISO selected directly, extract to its own directory
            folder_path = (
                os.path.dirname(self.iso_path)
                + f"/{os.path.basename(self.iso_path).replace('.iso', '')}"
            )

            self.temp_iso_path = self.iso_path  # Store for cleanup later

            self._extract_iso_directly(self.iso_path, folder_path)

    def _extract_zip_then_iso(self, zip_path):
        """Extract ZIP file first, then extract the ISO"""
        self.status_manager.show_message("Extracting ZIP archive...")

        # Clean up any existing zip extractor
        if hasattr(self, "zip_extractor") and self.zip_extractor:
            if self.zip_extractor.isRunning():
                self.zip_extractor.should_stop = True
                self.zip_extractor.wait(1000)  # Wait up to 1 second
            self.zip_extractor.deleteLater()

        # Show progress bar
        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(0)

        self.zip_extractor = ZipExtractorWorker(zip_path)

        # Connect signals
        self.zip_extractor.progress.connect(self._update_zip_progress)
        self.zip_extractor.file_extracted.connect(self._on_file_extracted)
        self.zip_extractor.extraction_complete.connect(
            lambda extracted_iso_path: self._on_zip_extraction_complete(
                extracted_iso_path, zip_path
            )
        )
        self.zip_extractor.extraction_error.connect(self._on_zip_extraction_error)
        self.zip_extractor.finished.connect(self._cleanup_zip_extractor)

        self.zip_extractor.start()

    def _cleanup_zip_extractor(self):
        """Clean up the zip extractor thread"""
        if hasattr(self, "zip_extractor") and self.zip_extractor:
            self.zip_extractor.deleteLater()
            self.zip_extractor = None

    def _on_zip_extraction_complete(self, extracted_iso_path: str, original_zip: str):
        """Handle ZIP extraction completion"""
        self.progress_bar.setVisible(False)

        # If we got an ISO file, proceed with ISO extraction
        if extracted_iso_path and extracted_iso_path.lower().endswith(".iso"):
            # Extract ISO to the original ZIP's directory
            extract_to_dir = (
                os.path.dirname(original_zip)
                + f"/{os.path.basename(extracted_iso_path).replace('.iso', '')}"
            )

            # Store the temp ISO path for cleanup later
            self.temp_iso_path = extracted_iso_path

            self._extract_iso_directly(extracted_iso_path, extract_to_dir)
        else:
            self.status_manager.show_message("ZIP extracted, but no ISO file found")

            # If we're in batch mode, move to next file
            if hasattr(self, "current_extraction_batch"):
                self._move_to_next_extraction_file()
            else:
                QMessageBox.information(
                    self,
                    "No ISO Found",
                    f"ZIP file extracted successfully, but no ISO file was found in:\n{extracted_iso_path}",
                )

    def _extract_iso_directly(self, iso_path, extract_to_dir):
        """Extract ISO directly with extract-xiso.exe"""
        self.status_manager.show_message("Extracting ISO...")

        # Ensure the output directory exists
        os.makedirs(extract_to_dir, exist_ok=True)

        extraction_process = QProcess(self)
        extraction_process.setProgram("extract-xiso.exe")
        extraction_process.setArguments(["-d", extract_to_dir, iso_path])
        extraction_process.finished.connect(self._on_extraction_finished)
        extraction_process.start()

    def _update_zip_progress(self, progress: int):
        """Update progress bar for ZIP extraction"""
        self.progress_bar.setValue(progress)

    def _on_file_extracted(self, filename: str):
        """Handle individual file extraction"""
        self.file_path = filename
        self.status_manager.show_message(f"Extracting: {filename}")

    def _on_zip_extraction_error(self, error_message: str):
        """Handle ZIP extraction error"""
        self.progress_bar.setVisible(False)
        self.status_manager.show_message("ZIP extraction failed")

        QMessageBox.critical(
            self,
            "ZIP Extraction Error",
            f"Failed to extract ZIP file:\n{error_message}",
        )

    def _on_extraction_finished(self):
        """Handle extraction process finished"""
        self.status_manager.show_message("Extraction finished")

        # Clean up temporary ISO file if it exists
        if hasattr(self, "temp_iso_path") and self.temp_iso_path:
            try:
                if os.path.exists(self.temp_iso_path):
                    os.remove(self.temp_iso_path)

                    # Also clean up the temp directory if it's empty
                    temp_dir = os.path.dirname(self.temp_iso_path)
                    if temp_dir and os.path.basename(temp_dir) == "xbbm_zip_extract":
                        try:
                            os.rmdir(temp_dir)  # Only removes if empty
                        except OSError:
                            # Directory not empty or other error, ignore
                            pass

            except OSError as e:
                print(f"Failed to delete temporary ISO: {e}")
            finally:
                # Clear the reference
                self.temp_iso_path = None

        # If we're in batch mode, move to next file
        if hasattr(self, "current_extraction_batch"):
            self._move_to_next_extraction_file()

    def _move_to_next_extraction_file(self):
        """Move to the next file in extraction batch"""
        self.current_extraction_batch_index += 1

        # Update overall progress
        overall_progress = (
            self.current_extraction_batch_index / self.total_extraction_batch_files
        ) * 100
        self.progress_bar.setValue(int(overall_progress))

        # Extract next file
        self._extract_next_batch_file()

    def _on_batch_extraction_complete(self):
        """Handle completion of entire extraction batch"""
        self.progress_bar.setVisible(False)

        # Clear batch variables
        if hasattr(self, "current_extraction_batch"):
            delattr(self, "current_extraction_batch")
        if hasattr(self, "current_extraction_batch_index"):
            delattr(self, "current_extraction_batch_index")
        if hasattr(self, "total_extraction_batch_files"):
            total_completed = self.total_extraction_batch_files
            delattr(self, "total_extraction_batch_files")
        else:
            total_completed = 0

        self.status_manager.show_message("Batch extraction completed")

        QMessageBox.information(
            self,
            "Batch Extraction Complete",
            f"Successfully extracted {total_completed} files.",
        )

    def browse_for_god_creation(self):
        """Browse for ISO files to convert to GOD format"""
        file_dialog = QFileDialog(self)
        file_dialog.setWindowTitle("Select ISO File(s) to Convert to GOD")
        file_dialog.setNameFilter("Game Files (*.iso *.zip);;")
        file_dialog.setFileMode(QFileDialog.FileMode.ExistingFiles)

        if file_dialog.exec() == QFileDialog.DialogCode.Accepted:
            selected_files = file_dialog.selectedFiles()
            if selected_files:
                self._create_god_from_files(selected_files)

    def _create_god_from_files(self, file_paths):
        """Create GOD files from selected ISOs/ZIPs"""
        if not self.current_directory:
            QMessageBox.warning(
                self,
                "No Source Directory",
                "Please select a source directory first. GOD files will be created there.",
            )
            return

        total_files = len(file_paths)

        if total_files == 1:
            # Single file - use existing logic
            self.god_file_path = file_paths[0]
            self._create_god()
            return

        # Multiple files - show confirmation
        msg_box = QMessageBox(self)
        msg_box.setWindowTitle("Create Multiple GOD Files")
        msg_box.setText(f"Convert {total_files} files to GOD format?")
        msg_box.setInformativeText(
            f"GOD files will be created in:\n{self.current_directory}"
        )
        msg_box.setStandardButtons(
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        msg_box.setDefaultButton(QMessageBox.StandardButton.Yes)

        if msg_box.exec() == QMessageBox.StandardButton.Yes:
            self._start_batch_god_creation(file_paths)

    def _start_batch_god_creation(self, file_paths):
        """Start batch GOD creation of multiple files"""
        self.current_god_batch = file_paths
        self.current_god_batch_index = 0
        self.total_god_batch_files = len(file_paths)

        # Initialize temp ISO tracking for batch
        if not hasattr(self, "god_temp_isos"):
            self.god_temp_isos = []

        # Show progress
        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(0)

        self.status_manager.show_message(
            f"Processing file 1 of {self.total_god_batch_files}..."
        )

        # Start with first file
        self._create_next_god_file()

    def _create_next_god_file(self):
        """Create the next GOD file in the batch"""
        if self.current_god_batch_index >= len(self.current_god_batch):
            # Batch complete
            self._on_batch_god_creation_complete()
            return

        self.god_file_path = self.current_god_batch[self.current_god_batch_index]

        # Update status
        current_file = self.current_god_batch_index + 1
        filename = os.path.basename(self.god_file_path)
        self.status_manager.show_message(
            f"Processing file {current_file} of {self.total_god_batch_files}: {filename}"
        )

        # Check if it's a ZIP or ISO
        if self.god_file_path.lower().endswith(".zip"):
            self._extract_zip_then_create_god_batch(self.god_file_path)
        else:
            # ISO file directly
            self._create_god_directly(self.god_file_path, self.current_directory)

    def _extract_zip_then_create_god_batch(self, zip_path):
        """Extract ZIP file in batch mode for GOD creation"""
        self.god_zip_extractor = ZipExtractorWorker(zip_path)

        # Connect batch-specific signals for GOD
        self.god_zip_extractor.progress.connect(self._update_batch_god_zip_progress)
        self.god_zip_extractor.extraction_complete.connect(
            lambda extracted_iso_path: self._on_batch_god_zip_extraction_complete(
                extracted_iso_path, zip_path
            )
        )
        self.god_zip_extractor.extraction_error.connect(
            self._on_batch_god_zip_extraction_error
        )

        self.god_zip_extractor.start()

    def _update_batch_god_zip_progress(self, progress: int):
        """Update progress for batch ZIP extraction during GOD creation"""
        # Calculate overall batch progress
        file_progress = progress / 100.0
        overall_progress = (
            (self.current_god_batch_index + file_progress) / self.total_god_batch_files
        ) * 100
        self.progress_bar.setValue(int(overall_progress))

    def _on_batch_god_zip_extraction_complete(
        self, extracted_iso_path: str, original_zip: str
    ):
        """Handle batch ZIP extraction completion for GOD creation"""
        if extracted_iso_path and extracted_iso_path.lower().endswith(".iso"):
            # Store temp ISO for cleanup
            self.god_temp_isos.append(extracted_iso_path)

            # Create GOD from extracted ISO
            self._create_god_directly(extracted_iso_path, self.current_directory)
        else:
            # No ISO found, move to next file
            self._move_to_next_god_file()

    def _on_batch_god_zip_extraction_error(self, error_message: str):
        """Handle batch ZIP extraction error for GOD creation"""
        filename = os.path.basename(self.god_file_path)

        msg_box = QMessageBox(self)
        msg_box.setWindowTitle("ZIP Extraction Error")
        msg_box.setText(f"Failed to extract {filename}")
        msg_box.setInformativeText(
            f"Error: {error_message}\n\nContinue with remaining files?"
        )
        msg_box.setStandardButtons(
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )

        if msg_box.exec() == QMessageBox.StandardButton.Yes:
            self._move_to_next_god_file()
        else:
            self._cancel_batch_god_creation()

    def _on_god_creation_finished(self):
        """Handle GOD creation process finished"""
        self.status_manager.show_message("GOD creation finished")

        # Clean up temp ISOs for single file
        self._cleanup_god_temp_isos()

        # Rescan directory to show new GOD files
        if self.current_directory:
            self.scan_directory(force=True)

    def _on_batch_god_creation_finished(self):
        """Handle individual GOD creation completion in batch"""
        self._move_to_next_god_file()

    def _on_batch_god_creation_complete(self):
        """Handle completion of entire GOD batch"""
        self.progress_bar.setVisible(False)

        # Clean up all temp ISOs from batch
        self._cleanup_god_temp_isos()

        # Clear batch variables
        if hasattr(self, "current_god_batch"):
            delattr(self, "current_god_batch")
        if hasattr(self, "current_god_batch_index"):
            delattr(self, "current_god_batch_index")
        if hasattr(self, "total_god_batch_files"):
            delattr(self, "total_god_batch_files")

        self.status_manager.show_message("Batch GOD creation completed")

        QMessageBox.information(
            self,
            "Batch GOD Creation Complete",
            f"Successfully created GOD files from {self.total_god_batch_files} files.",
        )

        # Rescan directory to show new GOD files
        if self.current_directory:
            self.scan_directory(force=True)

    def _cancel_batch_god_creation(self):
        """Cancel the batch GOD creation process"""
        self.progress_bar.setVisible(False)

        # Clean up any temp files created so far
        self._cleanup_god_temp_isos()

        self.status_manager.show_message("Batch GOD creation cancelled")

    def _cleanup_god_temp_isos(self):
        """Clean up temporary ISO files from GOD creation"""
        if hasattr(self, "god_temp_isos"):
            for temp_iso in self.god_temp_isos:
                try:
                    if os.path.exists(temp_iso):
                        os.remove(temp_iso)

                        # Also clean up the temp directory if it's empty
                        temp_dir = os.path.dirname(temp_iso)
                        if (
                            temp_dir
                            and os.path.basename(temp_dir) == "xbbm_zip_extract"
                        ):
                            try:
                                os.rmdir(temp_dir)  # Only removes if empty
                                print(f"Deleted temporary directory: {temp_dir}")
                            except OSError:
                                # Directory not empty or other error, ignore
                                pass
                except OSError as e:
                    print(f"Failed to delete temporary ISO: {e}")

            # Clear the list
            self.god_temp_isos = []

    def _create_god(self):
        """Create GOD file with iso2god-x86_64-windows.exe"""
        if not self.god_file_path:
            QMessageBox.warning(
                self, "No files selected", "Please select an ISO/ZIP file to convert."
            )
            return

        if not self.current_directory:
            QMessageBox.warning(
                self,
                "No destination directory",
                "Please select a source directory first. GOD files will be created there.",
            )
            return

        # Check if it's a ZIP file
        if self.god_file_path.lower().endswith(".zip"):
            self._extract_zip_then_create_god(self.god_file_path)
        else:
            # ISO file directly
            self._create_god_directly(self.god_file_path, self.current_directory)

    def _extract_zip_then_create_god(self, zip_path):
        """Extract ZIP file first, then create GOD from the ISO"""
        self.status_manager.show_message("Extracting ZIP archive for GOD creation...")

        # Show progress bar
        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(0)

        self.god_zip_extractor = ZipExtractorWorker(zip_path)

        # Connect signals for GOD creation
        self.god_zip_extractor.progress.connect(self._update_god_zip_progress)
        self.god_zip_extractor.extraction_complete.connect(
            lambda extracted_iso_path: self._on_god_zip_extraction_complete(
                extracted_iso_path, zip_path
            )
        )
        self.god_zip_extractor.extraction_error.connect(
            self._on_god_zip_extraction_error
        )

        self.god_zip_extractor.start()

    def _update_god_zip_progress(self, progress: int):
        """Update progress bar for ZIP extraction during GOD creation"""
        self.progress_bar.setValue(progress)

    def _on_god_zip_extraction_complete(
        self, extracted_iso_path: str, original_zip: str
    ):
        """Handle ZIP extraction completion for GOD creation"""
        self.progress_bar.setVisible(False)

        # If we got an ISO file, proceed with GOD creation
        if extracted_iso_path and extracted_iso_path.lower().endswith(".iso"):
            # Store the temp ISO path for cleanup later
            if not hasattr(self, "god_temp_isos"):
                self.god_temp_isos = []
            self.god_temp_isos.append(extracted_iso_path)

            # Create GOD from extracted ISO
            self._create_god_directly(extracted_iso_path, self.current_directory)
        else:
            self.status_manager.show_message("ZIP extracted, but no ISO file found")
            QMessageBox.information(
                self,
                "No ISO Found",
                f"ZIP file extracted successfully, but no ISO file was found in:\n{extracted_iso_path}",
            )

    def _on_god_zip_extraction_error(self, error_message: str):
        """Handle ZIP extraction error during GOD creation"""
        self.progress_bar.setVisible(False)
        self.status_manager.show_message("ZIP extraction failed")

        QMessageBox.critical(
            self,
            "ZIP Extraction Error",
            f"Failed to extract ZIP file for GOD creation:\n{error_message}",
        )

    def _create_god_directly(self, iso_path, dest_dir):
        """Create GOD file directly with iso2god-x86_64-windows.exe"""
        self.status_manager.show_message("Creating GOD file...")

        # Ensure the output directory exists
        os.makedirs(dest_dir, exist_ok=True)

        god_process = QProcess(self)
        god_process.setProgram("iso2god-x86_64-windows.exe")

        god_process.setArguments(["--trim", iso_path, dest_dir])

        # Connect appropriate finished handler based on batch mode
        if hasattr(self, "current_god_batch"):
            god_process.finished.connect(self._on_batch_god_creation_finished)
        else:
            god_process.finished.connect(self._on_god_creation_finished)

        god_process.start()

    def _on_god_creation_finished(self):
        """Handle GOD creation process finished"""
        self.status_manager.show_message("GOD creation finished")

        # Clean up temp ISOs for single file
        self._cleanup_god_temp_isos()

        # Rescan directory to show new GOD files
        if self.current_directory:
            self.scan_directory(force=True)

    def _on_batch_god_creation_finished(self):
        """Handle individual GOD creation completion in batch"""
        self._move_to_next_god_file()

    def _move_to_next_god_file(self):
        """Move to the next file in GOD batch"""
        self.current_god_batch_index += 1

        # Update overall progress
        overall_progress = (
            self.current_god_batch_index / self.total_god_batch_files
        ) * 100
        self.progress_bar.setValue(int(overall_progress))

        # Create next GOD file
        self._create_next_god_file()

    def _on_batch_god_creation_complete(self):
        """Handle completion of entire GOD batch"""
        self.progress_bar.setVisible(False)

        # Clean up all temp ISOs from batch
        self._cleanup_god_temp_isos()

        # Clear batch variables
        if hasattr(self, "current_god_batch"):
            delattr(self, "current_god_batch")
        if hasattr(self, "current_god_batch_index"):
            delattr(self, "current_god_batch_index")
        if hasattr(self, "total_god_batch_files"):
            total_completed = self.total_god_batch_files  # Store before deletion
            delattr(self, "total_god_batch_files")
        else:
            total_completed = 0

        self.status_manager.show_message("Batch GOD creation completed")

        QMessageBox.information(
            self,
            "Batch GOD Creation Complete",
            f"Successfully created GOD files from {total_completed} files.",
        )

        # Rescan directory to show new GOD files
        if self.current_directory:
            self.scan_directory(force=True)

    def _check_required_tools(self):
        """Check for required executables and set up watchers"""
        self.extract_xiso_path = os.path.join(os.getcwd(), "extract-xiso.exe")
        self.iso2god_path = os.path.join(os.getcwd(), "iso2god-x86_64-windows.exe")
        self.xextool_path = os.path.join(os.getcwd(), "XexTool.exe")

        self.extract_xiso_found = os.path.exists(self.extract_xiso_path)
        self.iso2god_found = os.path.exists(self.iso2god_path)
        self.xextool_found = os.path.exists(self.xextool_path)

        # Update status bar
        self._update_tools_status()

        # If all tools are found, no need for dialog
        if self.extract_xiso_found and self.iso2god_found and self.xextool_found:
            return

        # Set up file system watchers
        self._setup_tools_watchers()

        # Show download dialog
        self._show_tools_download_dialog()

    def _update_tools_status(self):
        """Update status bar with tools status"""
        extract_status = "✔️" if self.extract_xiso_found else "❌"
        iso2god_status = "✔️" if self.iso2god_found else "❌"
        xextool_status = "✔️" if self.xextool_found else "❌"

        # Update download button
        if self.extract_xiso_found:
            xiso_button = self.findChild(QPushButton, "extract_xiso_download_button")
            if xiso_button:
                xiso_button.setEnabled(False)
        if self.iso2god_found:
            iso2god_button = self.findChild(QPushButton, "iso2god_download_button")
            if iso2god_button:
                iso2god_button.setEnabled(False)
                iso2god_button.setText("✔️ Downloaded")
                xiso_button.setText("✔️ Downloaded")
        if self.xextool_found:
            xextool_button = self.findChild(QPushButton, "xextool_download_button")
            if xextool_button:
                xextool_button.setEnabled(False)
                xextool_button.setText("✔️ Downloaded")

        # If both tools are now found, close the dialog and update status bar
        if self.extract_xiso_found and self.iso2god_found:
            if hasattr(self, "tools_dialog") and self.tools_dialog:
                self.tools_dialog.accept()
                delattr(self, "tools_dialog")
            # Set a status message of tools ready for use, then 5 seconds later return to games found
            self.status_manager.show_message("✔️ Required tools are ready for use")
            return

        status_text = f"extract-xiso: {extract_status} | iso2god: {iso2god_status} | xextool: {xextool_status}"
        self.status_manager.show_message(status_text)

    def _show_tools_download_dialog(self):
        """Show dialog with download links for missing tools"""
        dialog = QDialog(self)
        dialog.setWindowTitle("Required Tools Missing")
        dialog.setModal(True)

        layout = QVBoxLayout(dialog)

        label = QLabel("The following tools are required but not found:")
        layout.addWidget(label)

        # Extract-xiso download
        if not self.extract_xiso_found:
            extract_layout = QHBoxLayout()
            extract_label = QLabel("extract-xiso.exe:")
            extract_button = QPushButton("Download")
            extract_button.setObjectName("extract_xiso_download_button")
            extract_button.clicked.connect(
                lambda: QDesktopServices.openUrl(
                    QUrl(
                        "https://github.com/XboxDev/extract-xiso/releases/latest/download/extract-xiso-Win64_Release.zip"
                    )
                )
            )
            extract_layout.addWidget(extract_label)
            extract_layout.addWidget(extract_button)
            layout.addLayout(extract_layout)

        # iso2god download
        if not self.iso2god_found:
            iso2god_layout = QHBoxLayout()
            iso2god_label = QLabel("iso2god-x86_64-windows.exe:")
            iso2god_button = QPushButton("Download")
            iso2god_button.setObjectName("iso2god_download_button")
            iso2god_button.clicked.connect(
                lambda: QDesktopServices.openUrl(
                    QUrl(
                        "https://github.com/iliazeus/iso2god-rs/releases/latest/download/iso2god-x86_64-windows.exe"
                    )
                )
            )
            iso2god_layout.addWidget(iso2god_label)
            iso2god_layout.addWidget(iso2god_button)
            layout.addLayout(iso2god_layout)

        # XexTool download
        if not self.xextool_found:
            api_url = "https://api.github.com/repos/mLoaDs/XexTool/releases/latest"
            try:
                response = requests.get(api_url, timeout=5)
                response.raise_for_status()
                release_info = response.json()
                assets = release_info.get("assets", [])
                download_url = None
                for asset in assets:
                    if asset.get("name", "").endswith(".zip"):
                        download_url = asset.get("browser_download_url")
                        break
                if not download_url:
                    download_url = "https://github.com/mLoaDs/XexTool/releases/download/v6.6/xextool_v6.6.zip"

                xextool_layout = QHBoxLayout()
                xextool_label = QLabel("XexTool.exe:")
                xextool_button = QPushButton("Download")
                xextool_button.setObjectName("xextool_download_button")
                xextool_button.clicked.connect(
                    lambda: QDesktopServices.openUrl(QUrl(download_url))
                )
                xextool_layout.addWidget(xextool_label)
                xextool_layout.addWidget(xextool_button)
                layout.addLayout(xextool_layout)
            except requests.RequestException as e:
                print(f"Error fetching XexTool download URL: {e}")

        instructions = QLabel(
            "After downloading:\n"
            "• Place files next to the application executable or your Downloads folder\n"
            "• The app will automatically detect and move them if required\n"
            "• extract-xiso and XexTool will be extracted from the ZIP automatically"
        )
        instructions.setWordWrap(True)
        layout.addWidget(instructions)

        close_button = QPushButton("Close")
        close_button.clicked.connect(dialog.accept)
        layout.addWidget(close_button)

        # Store dialog reference for auto-closing
        self.tools_dialog = dialog
        dialog.exec()

    def _setup_tools_watchers(self):
        """Set up file system watchers for tools detection"""
        self.tools_watcher = QFileSystemWatcher()

        # Watch the current directory
        self.tools_watcher.addPath(os.getcwd())

        # Watch Downloads directory on Windows
        downloads_path = os.path.join(os.path.expanduser("~"), "Downloads")
        if os.path.exists(downloads_path):
            self.tools_watcher.addPath(downloads_path)
            self.tools_watcher.addPath(downloads_path)

        # Connect to directory changed signal
        self.tools_watcher.directoryChanged.connect(self._on_tools_directory_changed)

    def _on_tools_directory_changed(self, path):
        """Handle directory changes for tools detection"""
        # Check if it's the Downloads directory
        downloads_path = os.path.join(os.path.expanduser("~"), "Downloads")
        is_downloads = path == downloads_path

        # Check for new files
        try:
            for filename in os.listdir(path):
                file_path = os.path.join(path, filename)

                # Handle extract-xiso ZIP
                if (
                    filename == "extract-xiso-Win64_Release.zip"
                    and not self.extract_xiso_found
                ):
                    if is_downloads:
                        # Move ZIP to current directory
                        dest_path = os.path.join(os.getcwd(), filename)
                        shutil.move(file_path, dest_path)
                        self._extract_xiso_zip(dest_path)
                    else:
                        # Already in current directory, extract it
                        self._extract_xiso_zip(file_path)

                # Handle iso2god EXE
                elif (
                    filename == "iso2god-x86_64-windows.exe" and not self.iso2god_found
                ):
                    if is_downloads:
                        # Move EXE to current directory
                        dest_path = self.iso2god_path
                        shutil.move(file_path, dest_path)
                        self.iso2god_found = True
                        self._update_tools_status()
                    else:
                        # Already in current directory
                        self.iso2god_found = True
                        self._update_tools_status()

                # Handle XexTool ZIP
                elif (
                    filename.startswith("xextool_v")
                    and filename.endswith(".zip")
                    and not self.xextool_found
                ):
                    if is_downloads:
                        # Move ZIP to current directory
                        dest_path = os.path.join(os.getcwd(), filename)
                        shutil.move(file_path, dest_path)
                        self._extract_xextool_zip(dest_path)
                    else:
                        # Already in current directory, extract it
                        self._extract_xextool_zip(file_path)

        except Exception as e:
            print(f"Error handling file change: {e}")

    def _extract_xiso_zip(self, zip_path):
        """Extract extract-xiso.exe from the ZIP file"""
        try:
            extracted = False
            with zipfile.ZipFile(zip_path, "r") as zip_ref:
                # Look for the exe file in the ZIP, it is under the `artifacts` subdirectory, ensure we only extract that file into the current directory
                for zip_info in zip_ref.infolist():
                    if zip_info.filename.endswith("extract-xiso.exe"):
                        zip_info.filename = os.path.basename(zip_info.filename)
                        zip_ref.extract(zip_info, os.getcwd())
                        extracted = True
                        break

            if extracted:
                self.extract_xiso_found = True
                self._update_tools_status()

                os.remove(zip_path)

        except Exception as e:
            print(f"Error extracting extract-xiso: {e}")

    def _extract_xextool_zip(self, zip_path):
        """Extract XexTool.exe from the ZIP file"""
        try:
            extracted = False
            with zipfile.ZipFile(zip_path, "r") as zip_ref:
                # Look for the exe file in the ZIP
                for zip_info in zip_ref.infolist():
                    if zip_info.filename.endswith("xextool.exe"):
                        zip_info.filename = os.path.basename(zip_info.filename)
                        zip_ref.extract(zip_info, os.getcwd())
                        extracted = True
                        break

            if extracted:
                self.xextool_found = True
                self._update_tools_status()

                os.remove(zip_path)

        except Exception as e:
            print(f"Error extracting XexTool: {e}")

    def _test_ftp_connection_for_switch(self):
        """Test FTP connection before switching modes"""
        # Disable UI during connection test
        self.setEnabled(False)
        self.status_manager.show_message("Testing FTP connection...")

        # Create and start connection tester thread
        self.ftp_tester = FTPConnectionTester(
            self.ftp_settings["host"], self.ftp_settings.get("port", 21), timeout=5
        )
        self.ftp_tester.connection_result.connect(self._on_ftp_connection_tested)
        self.ftp_tester.start()

    def _on_ftp_connection_tested(self, success: bool, message: str):
        """Handle FTP connection test result"""
        # Re-enable UI
        self.setEnabled(True)

        if success:
            # Connection successful, complete the switch to FTP mode
            self.status_manager.show_message("FTP connection successful")
            self._complete_mode_switch("ftp")
        else:
            # Connection failed, revert to USB mode
            self.current_mode = "usb"
            self.usb_mode_action.setChecked(True)
            self.ftp_mode_action.setChecked(False)
            self.settings_manager.save_current_mode("usb")

            # Show error message
            QMessageBox.warning(
                self,
                "FTP Connection Failed",
                f"Cannot connect to FTP server:\n{message}\n\n"
                "Switching back to USB mode.\n\n"
                "Please check your FTP settings and ensure the Xbox FTP server is running.",
            )

            self.status_manager.show_message(
                "FTP connection failed - switched back to USB mode"
            )

            # Complete switch to USB mode
            self._complete_mode_switch("usb")

    def _complete_mode_switch(self, mode: str):
        """Complete the mode switch after connection test"""
        if mode == "ftp":
            # Load FTP target directory
            ftp_target = self.ftp_target_directories[self.current_platform]
            self.current_target_directory = ftp_target
            self.target_directory_label.setText(f"FTP: {ftp_target}")
            self._update_target_space_label(ftp_target)

        elif mode == "usb":
            # Show target directory controls and load saved target
            usb_target = self.usb_target_directories[self.current_platform]

            if usb_target and os.path.exists(usb_target):
                self.current_target_directory = usb_target
                self.target_directory_label.setText(usb_target)
                self._update_target_space_label(usb_target)
                self.status_manager.show_message(
                    "Switched to USB mode - target directory loaded"
                )
            else:
                # Prompt for USB target directory
                self._prompt_for_usb_target_directory()

        # Source directory remains the same regardless of mode
        platform_dir = self.platform_directories[self.current_platform]
        if platform_dir:
            self.current_directory = platform_dir
            self.directory_label.setText(self.current_directory)
            self.toolbar_scan_action.setEnabled(True)

        # Update transfer button state
        self._update_transfer_button_state()

        # Rescan directory if we have one
        if self.current_directory:
            self.scan_directory()

    def _get_cache_file_path(self) -> Path:
        """Get the cache file path for current platform and directory"""
        if not self.current_directory:
            print("No current directory set.")
            return None

        # Create a safe filename from directory path
        dir_hash = hashlib.md5(
            self.current_directory.lower().encode("utf-8")
        ).hexdigest()[:10]
        cache_filename = f"scan_cache_{self.current_platform}_{dir_hash}.json"
        return self._cache_dir / cache_filename

    def _save_scan_cache(self):
        """Save current scan results to cache"""
        if not self.games or not self.current_directory:
            return

        cache_file = self._get_cache_file_path()
        if not cache_file:
            return

        try:
            cache_data = {
                "version": VERSION,
                "platform": self.current_platform,
                "directory": self.current_directory,
                "scan_time": time.time(),
                "games": [],
            }

            # Convert games to serializable format
            for game in self.games:
                game_data = {
                    "title_id": game.title_id,
                    "name": game.name,
                    "folder_path": game.folder_path,
                    "size_bytes": game.size_bytes,
                    "size_formatted": game.size_formatted,
                    "transferred": game.transferred,
                    "last_modified": getattr(game, "last_modified", 0),
                }
                cache_data["games"].append(game_data)

            with open(cache_file, "w", encoding="utf-8") as f:
                json.dump(cache_data, f, indent=2)

        except Exception as e:
            print(f"Error saving scan cache: {e}")

    def _load_scan_cache(self) -> bool:
        """Load scan results from cache if valid"""
        if not self.current_directory:
            print("No current directory set.")
            return False

        cache_file = self._get_cache_file_path()
        if not cache_file or not cache_file.exists():
            return False

        try:
            with open(cache_file, "r", encoding="utf-8") as f:
                cache_data = json.load(f)

            # Validate cache
            if not self._is_cache_valid(cache_data):
                print("Scan cache is invalid or outdated.")
                return False

            # Load games from cache
            self.games.clear()
            self.games_table.setRowCount(0)

            # Disable sorting during bulk insertion
            self.games_table.setSortingEnabled(False)

            for game_data in cache_data["games"]:
                game_info = GameInfo(
                    title_id=game_data["title_id"],
                    name=game_data["name"],
                    folder_path=game_data["folder_path"],
                    size_bytes=game_data["size_bytes"],
                    size_formatted=game_data["size_formatted"],
                )
                game_info.transferred = game_data.get("transferred", False)
                game_info.last_modified = game_data.get("last_modified", 0)

                self.games.append(game_info)

                # Add to table
                row = self.games_table.rowCount()
                self.games_table.insertRow(row)
                self.games_table.setRowHeight(row, 72)

                show_dlcs = self.current_platform in ["xbla"]
                self._create_table_items(row, game_info, show_dlcs)

            # Re-enable sorting
            self.games_table.setSortingEnabled(True)

            # Connect checkbox signal
            self.games_table.itemChanged.connect(self._on_checkbox_changed)

            # Update status
            game_count = len(self.games)

            # Download missing icons
            if game_count > 0:
                self.download_missing_icons()

            # Update transfer button state
            self._update_transfer_button_state()
            return True

        except Exception as e:
            print(f"Error loading scan cache: {e}")
            # # If cache is corrupted, delete it
            # try:
            #     cache_file.unlink()
            # except Exception:
            #     pass
            return False

    def _is_cache_valid(self, cache_data: dict) -> bool:
        """Check if cache data is valid and up-to-date"""
        try:
            # Check version compatibility
            if cache_data.get("version") != VERSION:
                print("Cache version is incompatible.")
                return False

            # Check platform match
            if cache_data.get("platform") != self.current_platform:
                print("Cache platform is incompatible.")
                return False

            # Check directory match
            if cache_data.get("directory") != self.current_directory:
                print("Cache directory is incompatible.")
                return False

            # Check if directory still exists
            if not os.path.exists(self.current_directory):
                print("Cache directory does not exist.")
                return False

            # Check cache age (invalidate if older than 24 hours)
            cache_time = cache_data.get("scan_time", 0)
            if time.time() - cache_time > 86400:  # 24 hours
                print("Cache is stale.")
                return False

            # Check if directory was modified since cache
            dir_modified = os.path.getmtime(self.current_directory)
            if dir_modified > cache_time:
                print("Cache directory was modified.")
                return False

            # Validate that cached games still exist
            games_data = cache_data.get("games", [])
            if not games_data:
                print("Cache is empty.")
                return False

            # Quick validation - check if some of the games still exist
            sample_size = min(5, len(games_data))
            for i in range(0, len(games_data), max(1, len(games_data) // sample_size)):
                game_path = games_data[i]["folder_path"]
                if not os.path.exists(game_path):
                    print(f"Cached game folder does not exist: {game_path}")
                    return False

                # # Check if game folder was modified
                # game_modified = os.path.getmtime(game_path)
                # cached_modified = games_data[i].get("last_modified", 0)
                # if game_modified > cached_modified:
                #     print(f"Cached game folder was modified: {game_path}")
                #     return False

            return True

        except Exception as e:
            print(f"Error validating cache: {e}")
            return False

    def _clear_cache_for_directory(self):
        """Clear cache for current directory"""
        cache_file = self._get_cache_file_path()
        if cache_file and cache_file.exists():
            try:
                cache_file.unlink()
            except Exception as e:
                print(f"Error clearing cache: {e}")

    def _cleanup_old_cache_files(self):
        """Clean up old cache files on startup"""
        try:
            cache_files = list(self._cache_dir.glob("scan_cache_*.json"))
            current_time = time.time()

            for cache_file in cache_files:
                try:
                    # Remove cache files older than 7 days
                    if current_time - cache_file.stat().st_mtime > 604800:  # 7 days
                        cache_file.unlink()
                except Exception:
                    continue

        except Exception as e:
            print(f"Error cleaning up cache files: {e}")

    def _test_ftp_connection_on_startup(self):
        """Test FTP connection on startup without blocking UI"""
        if not self.ftp_settings or not self.ftp_settings.get("host"):
            self.status_manager.show_message("FTP settings not configured")
            return

        # Test connection without changing modes
        self.status_manager.show_message("Testing FTP connection...")

        self.startup_ftp_tester = FTPConnectionTester(
            self.ftp_settings["host"], self.ftp_settings.get("port", 21), timeout=5
        )
        self.startup_ftp_tester.connection_result.connect(
            self._on_startup_ftp_connection_tested
        )
        self.startup_ftp_tester.start()

    def _on_startup_ftp_connection_tested(self, success: bool, message: str):
        """Handle startup FTP connection test result"""
        if success:
            self.status_manager.show_message("FTP connection ready")
            # Now it's safe to check target directory availability
            if self.current_target_directory:
                is_available = self._check_target_directory_availability(
                    self.current_target_directory
                )
                if not is_available:
                    self.status_manager.show_message(
                        "FTP target directory not accessible"
                    )
        else:
            self.status_manager.show_message(f"FTP connection failed: {message}")
            # Optionally switch to USB mode or show warning
            QMessageBox.warning(
                self,
                "FTP Connection Failed",
                f"Cannot connect to FTP server on startup:\n{message}\n\n"
                "FTP operations will not be available until connection is restored.",
            )


class NonSortableHeaderView(QHeaderView):
    """Custom header view to disable sorting and indicators on specific sections"""

    def __init__(self, orientation, parent=None):
        super().__init__(orientation, parent)

    def _get_header_check_state(self):
        table = self.parent()
        row_count = table.rowCount()
        if row_count == 0:
            return Qt.CheckState.Unchecked
        checked_count = sum(
            1
            for r in range(row_count)
            if table.item(r, 0).checkState() == Qt.CheckState.Checked
        )
        if checked_count == 0:
            return Qt.CheckState.Unchecked
        elif checked_count == row_count:
            return Qt.CheckState.Checked
        else:
            return Qt.CheckState.PartiallyChecked

    def paintSection(self, painter: QPainter, rect: QRect, logicalIndex: int):
        if logicalIndex != 0:
            super().paintSection(painter, rect, logicalIndex)
            return

        painter.save()
        opt = QStyleOptionButton()
        indicator_width = self.style().pixelMetric(QStyle.PixelMetric.PM_IndicatorWidth)
        indicator_height = self.style().pixelMetric(
            QStyle.PixelMetric.PM_IndicatorHeight
        )
        x = rect.x() + (rect.width() - indicator_width) // 2
        y = rect.y() + (rect.height() - indicator_height) // 2
        opt.rect = QRect(x, y, indicator_width, indicator_height)
        opt.state = QStyle.StateFlag.State_Enabled

        check_state = self._get_header_check_state()
        if check_state == Qt.CheckState.Checked:
            opt.state |= QStyle.StateFlag.State_On
        elif check_state == Qt.CheckState.PartiallyChecked:
            opt.state |= QStyle.StateFlag.State_NoChange
        # else State_Off by default

        self.style().drawControl(QStyle.ControlElement.CE_CheckBox, opt, painter)
        painter.restore()

    def mousePressEvent(self, event):
        section = self.logicalIndexAt(event.pos())
        if section == 1:  # Disable for icon (1) column
            event.ignore()
            return

        if section == 0:
            table = self.parent()
            row_count = self.model().rowCount()
            current_state = self._get_header_check_state()
            new_state = (
                Qt.CheckState.Unchecked
                if current_state == Qt.CheckState.Checked
                else Qt.CheckState.Checked
            )
            for row in range(row_count):
                item = table.item(row, 0)
                if item:
                    item.setCheckState(new_state)
            event.ignore()
            return

        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        section = self.logicalIndexAt(event.pos())

        # Check if we're near a column boundary (resize area)
        resize_margin = 5  # pixels on each side of boundary
        x = event.pos().x()

        # Check each section boundary
        for i in range(self.count()):
            section_start = self.sectionPosition(i)
            section_end = section_start + self.sectionSize(i)

            # Check if we're within resize margin of this section's end
            if abs(x - section_end) <= resize_margin and i < self.count() - 1:
                # We're in a resize area - show resize cursor
                self.setCursor(Qt.CursorShape.SplitHCursor)
                super().mouseMoveEvent(event)
                return

        # Not in resize area - handle normal cursor logic
        if section >= 0 and section != 1:  # Valid section, not the icon column
            self.setCursor(Qt.CursorShape.PointingHandCursor)
            return
        else:
            self.setCursor(Qt.CursorShape.ArrowCursor)

        super().mouseMoveEvent(event)

    def leaveEvent(self, event):
        self.setCursor(Qt.CursorShape.ArrowCursor)
        super().leaveEvent(event)


class SizeTableWidgetItem(QTableWidgetItem):
    """Custom table widget item that sorts by byte values instead of text"""

    def __init__(self, formatted_text: str, size_bytes: int):
        super().__init__(formatted_text)
        self.size_bytes = size_bytes

    def __lt__(self, other):
        """Override less than operator for proper sorting"""
        if isinstance(other, SizeTableWidgetItem):
            return self.size_bytes < other.size_bytes
        return super().__lt__(other)
