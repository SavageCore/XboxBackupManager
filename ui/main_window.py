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
import tempfile
import time
import zipfile
from pathlib import Path
from typing import Dict, List, Optional

import qtawesome as qta
import requests
from PyQt6.QtCore import QFileSystemWatcher, QSize, Qt, QTimer, QUrl
from PyQt6.QtGui import (
    QAction,
    QActionGroup,
    QDesktopServices,
    QIcon,
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
    QPushButton,
    QTableWidget,
    QVBoxLayout,
    QWidget,
)

from constants import APP_NAME, VERSION

# Import our modular components
from managers.directory_manager import DirectoryManager
from managers.game_manager import GameManager
from managers.table_manager import TableManager
from managers.transfer_manager import TransferManager
from models.game_info import GameInfo
from ui.batch_dlc_import_progress_dialog import (
    BatchDLCImportProgressDialog,
)
from ui.batch_tu_progress_dialog import BatchTUProgressDialog
from ui.dlc_info_dialog import DLCInfoDialog
from ui.dlc_list_dialog import DLCListDialog
from ui.file_processing_dialog import FileProcessingDialog
from ui.ftp_browser_dialog import FTPBrowserDialog
from ui.ftp_settings_dialog import FTPSettingsDialog
from ui.icon_manager import IconManager
from ui.theme_manager import ThemeManager
from ui.xboxunity_settings_dialog import XboxUnitySettingsDialog
from ui.xboxunity_tu_dialog import XboxUnityTitleUpdatesDialog
from utils.dlc_utils import DLCUtils
from utils.ftp_client import FTPClient
from utils.ftp_connection_manager import get_ftp_manager
from utils.github import check_for_update, update
from utils.settings_manager import SettingsManager
from utils.status_manager import StatusManager
from utils.system_utils import SystemUtils
from workers.title_update_fetcher import TitleUpdateFetchWorker
from utils.ui_utils import UIUtils
from utils.xboxunity import XboxUnity
from workers.batch_dlc_import import BatchDLCImportWorker
from workers.batch_dlc_install_processor import BatchDLCInstallProcessor
from workers.batch_tu_processor import BatchTitleUpdateProcessor
from workers.file_transfer import FileTransferWorker
from workers.ftp_connection_tester import FTPConnectionTester
from workers.ftp_transfer import FTPTransferWorker
from workers.icon_downloader import IconDownloader
from workers.zip_extract import ZipExtractorWorker


class XboxBackupManager(QMainWindow):
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
        self.icon_manager = IconManager(self.theme_manager)
        self.xboxunity = XboxUnity()

        # Initialize directory manager
        self.directory_manager = DirectoryManager(self)

        # Connect directory manager signals
        self.directory_manager.directory_changed.connect(self._on_directory_changed)
        self.directory_manager.directory_files_changed.connect(
            self._on_directory_files_changed
        )

        # Initialize game manager
        self.game_manager = GameManager(self)

        # Connect game manager signals
        self.game_manager.scan_started.connect(self._on_scan_started)
        self.game_manager.scan_progress.connect(self._on_scan_progress)
        self.game_manager.scan_complete.connect(self._on_scan_complete)
        self.game_manager.scan_error.connect(self._on_scan_error)

        # Initialize table manager (will be set up properly after UI creation)
        self.table_manager = None

        # Initialize transfer manager
        self.transfer_manager = TransferManager(self)

        self.dlc_utils = DLCUtils(self)

        # Connect transfer manager signals
        self.transfer_manager.transfer_started.connect(self._on_transfer_started)
        self.transfer_manager.transfer_progress.connect(self._on_transfer_progress)
        self.transfer_manager.transfer_complete.connect(self._on_transfer_complete)
        self.transfer_manager.transfer_error.connect(self._on_transfer_error)
        self.transfer_manager.transfer_cancelled.connect(self._on_transfer_cancelled)

        self.status_bar = self.statusBar()
        self.status_manager = StatusManager(self.status_bar, self)

        # Application state
        self.games: List[GameInfo] = []
        self.current_directory = ""
        self.current_target_directory = ""
        self.current_cache_directory = ""
        self.current_content_directory = ""
        self.current_dlc_directory = ""
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

        # Current processing dialog (to reuse during batch operations)
        self._current_processing_dialog = None

        # Timer to debounce file system events
        self.scan_timer = QTimer()
        self.scan_timer.setSingleShot(True)
        self.scan_timer.timeout.connect(self.delayed_scan)
        self.scan_delay = 2000  # 2 seconds delay

        # Initialize UI and load settings
        self.init_ui()
        self.load_settings()

        # Enable UI immediately since we don't need database loading for either platform
        self.browse_action.setEnabled(True)
        self.browse_target_action.setEnabled(True)
        if self.current_directory:
            self.toolbar_scan_action.setEnabled(True)
            # Directory watching is now handled by DirectoryManager in load_settings()
            self.scan_directory()

        self.setup_colors()
        self.setup_ui()

        self._check_for_updates()

        QTimer.singleShot(100, self._check_required_tools)

    def setup_colors(self):
        """Setup color properties from theme"""
        # palette = self.theme_manager.get_palette()

        # self.normal_color = palette.COLOR_TEXT_1
        # self.active_color = palette.COLOR_TEXT_1
        # self.disabled_color = palette.COLOR_DISABLED

    def setup_ui(self):
        """Setup UI with themed icons"""
        self.icon_manager.register_widget_icon(self.browse_action, "fa6s.folder-open")
        self.icon_manager.register_widget_icon(
            self.browse_target_action, "fa6s.bullseye"
        )
        self.icon_manager.register_widget_icon(
            self.ftp_settings_action, "fa6s.network-wired"
        )
        self.icon_manager.register_widget_icon(
            self.xbox_unity_settings_action, "fa6s.gear"
        )
        self.icon_manager.register_widget_icon(self.exit_action, "fa6s.xmark")
        self.icon_manager.register_widget_icon(
            self.ftp_mode_action, "fa6s.network-wired"
        )
        self.icon_manager.register_widget_icon(self.usb_mode_action, "fa6b.usb")
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

        self.refresh_toolbar_icons()

    def refresh_toolbar_icons(self):
        """Refresh toolbar icons to match the current theme colors."""
        if self.theme_manager.should_use_dark_mode():
            normal_color = "#ffffff"
            hover_color = "#1de9b6"
            disabled_color = "#4f5b62"
        else:
            normal_color = "#3c3c3c"
            hover_color = "#1de9b6"
            disabled_color = "#e6e6e6"

        if hasattr(self, "toolbar_actions"):
            icon_mappings = {
                "Scan": "fa6s.magnifying-glass",
                "Transfer": "fa6s.arrow-right",
                "Remove": "fa6s.trash",
                "Batch Title Updater": "fa6s.download",
                "Batch DLC Installer": "fa6s.cube",
            }
            for action in self.toolbar_actions:
                icon_name = icon_mappings.get(action.text(), "fa6s.circle")
                icon = qta.icon(
                    icon_name,
                    color=normal_color,
                    color_active=hover_color,
                    color_disabled=disabled_color,
                )
                action.setIcon(icon)
        # Also force toolbar repaint if present
        if hasattr(self, "toolbar"):
            self.toolbar.update()
            self.toolbar.repaint()

    def set_theme_override(self, override_value):
        """Set theme override and apply theme, then update toolbar icons"""
        self.theme_manager.set_override(override_value)
        self.apply_theme()
        self.refresh_toolbar_icons()
        self.settings_manager.save_theme_preference(override_value)

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

        # Remove hover background effect
        toolbar.setStyleSheet(
            """
            QToolBar {
                background: transparent;
                border: none;
            }
            QToolButton {
                background: transparent;
                border: none;
                padding: 5px;
            }
            QToolButton:hover {
                background: transparent;  /* Remove gray hover background */
                border: none;
            }
            QToolButton:pressed {
                background: transparent;
                border: none;
            }
        """
        )

        # Scan Directory
        self.toolbar_scan_action = QAction("Scan", self)
        self.toolbar_scan_action.setIcon(
            self.icon_manager.create_icon("fa6s.magnifying-glass")
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
            self.icon_manager.create_icon("fa6s.arrow-right")
        )
        self.toolbar_transfer_action.setToolTip("Transfer selected games to target")
        self.toolbar_transfer_action.triggered.connect(self.transfer_selected_games)
        self.toolbar_transfer_action.setEnabled(False)
        toolbar.addAction(self.toolbar_transfer_action)

        # Remove Selected
        self.toolbar_remove_action = QAction("Remove", self)
        self.toolbar_remove_action.setIcon(self.icon_manager.create_icon("fa6s.trash"))
        self.toolbar_remove_action.setToolTip("Remove selected games from target")
        self.toolbar_remove_action.triggered.connect(self.remove_selected_games)
        self.toolbar_remove_action.setEnabled(False)
        toolbar.addAction(self.toolbar_remove_action)

        # Batch Title Updater
        self.toolbar_batch_tu_action = QAction("Batch Title Updater", self)
        self.toolbar_batch_tu_action.setIcon(
            self.icon_manager.create_icon("fa6s.download")
        )
        self.toolbar_batch_tu_action.setToolTip(
            "Download missing title updates for all transferred games"
        )
        self.toolbar_batch_tu_action.triggered.connect(
            self.batch_download_title_updates
        )
        self.toolbar_batch_tu_action.setEnabled(False)
        toolbar.addAction(self.toolbar_batch_tu_action)

        # Batch DLC Installer
        self.toolbar_batch_dlc_install_action = QAction("Batch DLC Installer", self)
        self.toolbar_batch_dlc_install_action.setIcon(
            self.icon_manager.create_icon("fa6s.cube")
        )
        self.toolbar_batch_dlc_install_action.setToolTip(
            "Install all available DLCs for all transferred games"
        )
        self.toolbar_batch_dlc_install_action.triggered.connect(self.batch_install_dlcs)
        self.toolbar_batch_dlc_install_action.setEnabled(False)
        toolbar.addAction(self.toolbar_batch_dlc_install_action)

        # Store references for icon updates
        self.toolbar_actions = [
            self.toolbar_scan_action,
            self.toolbar_transfer_action,
            self.toolbar_remove_action,
            self.toolbar_batch_tu_action,
            self.toolbar_batch_dlc_install_action,
        ]

    def batch_install_dlcs(self):
        """Batch install all DLCs for all transferred games in target directory"""
        # Get all games in target directory (reuse _get_all_target_games)
        target_games = self._get_all_target_games()
        if not target_games:
            QMessageBox.information(
                self,
                "Batch DLC Install",
                "No games found in target directory.",
            )
            return

        reply = QMessageBox.question(
            self,
            "Batch DLC Install",
            f"This will install all available DLCs for {len(target_games)} games.\nContinue?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.Yes,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        # Create progress dialog
        from ui.batch_dlc_import_progress_dialog import BatchDLCImportProgressDialog

        self.batch_dlc_install_progress_dialog = BatchDLCImportProgressDialog(
            len(target_games), self
        )
        self.batch_dlc_install_progress_dialog.setWindowTitle(
            "Batch DLC Install Progress"
        )
        self.batch_dlc_install_progress_dialog.show()

        # Create and setup worker
        self.batch_dlc_install_worker = BatchDLCInstallProcessor(parent=self)
        self.batch_dlc_install_worker.setup_batch(target_games, self.current_mode)

        # Connect signals
        self.batch_dlc_install_worker.progress_update.connect(
            self._on_batch_dlc_install_progress
        )
        self.batch_dlc_install_worker.game_started.connect(
            self._on_batch_dlc_install_game_started
        )
        self.batch_dlc_install_worker.game_completed.connect(
            self._on_batch_dlc_install_game_completed
        )
        self.batch_dlc_install_worker.dlc_installed.connect(
            self._on_batch_dlc_installed
        )
        self.batch_dlc_install_worker.dlc_progress.connect(
            self._on_batch_dlc_install_file_progress
        )
        self.batch_dlc_install_worker.dlc_speed.connect(
            self._on_batch_dlc_install_speed
        )
        self.batch_dlc_install_worker.batch_complete.connect(
            self._on_batch_dlc_install_complete
        )
        self.batch_dlc_install_worker.error_occurred.connect(
            self._on_batch_dlc_install_error
        )
        self.batch_dlc_install_progress_dialog.cancel_requested.connect(
            self.batch_dlc_install_worker.stop_processing
        )
        self.batch_dlc_install_progress_dialog.cancel_requested.connect(
            self._on_batch_dlc_install_cancelled
        )

        # Disable toolbar actions during batch processing
        self.toolbar_transfer_action.setEnabled(False)
        self.toolbar_remove_action.setEnabled(False)
        self.toolbar_batch_tu_action.setEnabled(False)
        self.toolbar_batch_dlc_install_action.setEnabled(False)
        self.browse_action.setEnabled(False)
        self.browse_target_action.setEnabled(False)

        # Start processing
        self.batch_dlc_install_worker.start()

    def _on_batch_dlc_install_progress(self, current: int, total: int):
        if hasattr(self, "batch_dlc_install_progress_dialog"):
            self.batch_dlc_install_progress_dialog.update_progress(current)

    def _on_batch_dlc_install_game_started(self, game_name: str):
        if hasattr(self, "batch_dlc_install_progress_dialog"):
            self.batch_dlc_install_progress_dialog.label.setText(
                f"Installing DLCs: {game_name}"
            )

    def _on_batch_dlc_install_game_completed(self, game_name: str, dlcs_installed: int):
        # Optionally update status or log
        pass

    def _on_batch_dlc_installed(self, game_name: str, dlc_file: str):
        # Optionally update status or log
        # Reset file progress when a file completes
        if hasattr(self, "batch_dlc_install_progress_dialog"):
            self.batch_dlc_install_progress_dialog.reset_file_progress()

    def _on_batch_dlc_install_file_progress(self, dlc_file: str, progress: int):
        """Handle per-file progress updates"""
        if hasattr(self, "batch_dlc_install_progress_dialog"):
            self.batch_dlc_install_progress_dialog.update_file_progress(
                dlc_file, progress
            )

    def _on_batch_dlc_install_speed(self, dlc_file: str, speed_bps: float):
        """Handle transfer speed updates"""
        if hasattr(self, "batch_dlc_install_progress_dialog"):
            self.batch_dlc_install_progress_dialog.update_speed(speed_bps)

    def _on_batch_dlc_install_complete(self, total_games: int, total_dlcs: int):
        if hasattr(self, "batch_dlc_install_progress_dialog"):
            self.batch_dlc_install_progress_dialog.close()
            del self.batch_dlc_install_progress_dialog
        if hasattr(self, "batch_dlc_install_worker"):
            self.batch_dlc_install_worker.quit()
            self.batch_dlc_install_worker.wait()
            del self.batch_dlc_install_worker
        self.toolbar_transfer_action.setEnabled(True)
        self.toolbar_remove_action.setEnabled(True)
        self.toolbar_batch_tu_action.setEnabled(True)
        self.toolbar_batch_dlc_install_action.setEnabled(True)
        self.browse_action.setEnabled(True)
        self.browse_target_action.setEnabled(True)
        QMessageBox.information(
            self,
            "Batch DLC Install Complete",
            f"Processed {total_games} games.\nInstalled {total_dlcs} DLCs.\n\nSee 'batch_dlc_install_log.txt' for details.",
        )

    def _on_batch_dlc_install_error(self, error_message: str):
        if hasattr(self, "batch_dlc_install_progress_dialog"):
            self.batch_dlc_install_progress_dialog.close()
            del self.batch_dlc_install_progress_dialog
        if hasattr(self, "batch_dlc_install_worker"):
            self.batch_dlc_install_worker.quit()
            self.batch_dlc_install_worker.wait()
            del self.batch_dlc_install_worker
        self.toolbar_transfer_action.setEnabled(True)
        self.toolbar_remove_action.setEnabled(True)
        self.toolbar_batch_tu_action.setEnabled(True)
        self.toolbar_batch_dlc_install_action.setEnabled(True)
        self.browse_action.setEnabled(True)
        self.browse_target_action.setEnabled(True)
        QMessageBox.critical(
            self,
            "Batch DLC Install Error",
            f"An error occurred during batch DLC install:\n\n{error_message}",
        )

    def _on_batch_dlc_install_cancelled(self):
        self.toolbar_transfer_action.setEnabled(True)
        self.toolbar_remove_action.setEnabled(True)
        self.toolbar_batch_tu_action.setEnabled(True)
        self.toolbar_batch_dlc_install_action.setEnabled(True)
        self.browse_action.setEnabled(True)
        self.browse_target_action.setEnabled(True)
        self.status_manager.show_message("Batch DLC install cancelled")

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
        self.games_table = ClickableFirstColumnTableWidget()
        self.games_table.setContentsMargins(0, 0, 0, 0)

        # Enable context menu
        self.games_table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.games_table.customContextMenuRequested.connect(self.show_context_menu)

        # Override mouseMoveEvent for custom cursor handling
        self.games_table.mouseMoveEvent = self._table_mouse_move_event

        main_layout.addWidget(self.games_table)

        # Initialize table manager now that table is created
        self.table_manager = TableManager(self.games_table, self)

        # Connect table manager signals
        self.table_manager.selection_changed.connect(self._update_transfer_button_state)

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
        self.browse_action = QAction("Set &Source Directory...", self)
        self.browse_action.setShortcut("Ctrl+O")
        self.browse_action.setIcon(self.icon_manager.create_icon("fa6s.folder-open"))
        self.icon_manager.register_widget_icon(self.browse_action, "fa6s.folder-open")
        self.browse_action.triggered.connect(self.browse_directory)
        file_menu.addAction(self.browse_action)

        # Set Target directory action
        self.browse_target_action = QAction("Set &Target Directory...", self)
        self.browse_target_action.setShortcut("Ctrl+T")
        self.browse_target_action.setIcon(
            self.icon_manager.create_icon("fa6s.bullseye")
        )
        self.icon_manager.register_widget_icon(
            self.browse_target_action, "fa6s.bullseye"
        )
        self.browse_target_action.triggered.connect(self.browse_target_directory)
        file_menu.addAction(self.browse_target_action)

        # Set Cache directory action
        self.browse_cache_action = QAction("Set C&ache Directory...", self)
        self.browse_cache_action.setShortcut("Ctrl+K")
        self.browse_cache_action.setIcon(self.icon_manager.create_icon("fa6s.database"))
        self.icon_manager.register_widget_icon(
            self.browse_cache_action, "fa6s.database"
        )
        self.browse_cache_action.setEnabled(True)
        self.browse_cache_action.triggered.connect(self.browse_cache_directory)
        file_menu.addAction(self.browse_cache_action)

        # Set Content directory action
        self.browse_content_action = QAction("Set C&ontent Directory...", self)
        self.browse_content_action.setShortcut("Ctrl+N")
        self.browse_content_action.setIcon(
            self.icon_manager.create_icon("fa6s.folder-tree")
        )
        self.icon_manager.register_widget_icon(
            self.browse_content_action, "fa6s.folder-tree"
        )
        self.browse_content_action.setEnabled(True)
        self.browse_content_action.triggered.connect(self.browse_content_directory)
        file_menu.addAction(self.browse_content_action)

        # Set DLC directory action
        self.browse_dlc_action = QAction("Set &DLC Directory...", self)
        self.browse_dlc_action.setShortcut("Ctrl+D")
        self.browse_dlc_action.setIcon(self.icon_manager.create_icon("fa6s.cube"))
        self.icon_manager.register_widget_icon(self.browse_dlc_action, "fa6s.cube")
        self.browse_dlc_action.triggered.connect(self.browse_dlc_directory)
        file_menu.addAction(self.browse_dlc_action)

        file_menu.addSeparator()

        # FTP settings action
        self.ftp_settings_action = QAction("&FTP Settings...", self)
        self.ftp_settings_action.setIcon(
            self.icon_manager.create_icon("fa6s.network-wired")
        )
        self.icon_manager.register_widget_icon(
            self.ftp_settings_action, "fa6s.network-wired"
        )
        self.ftp_settings_action.triggered.connect(self.show_ftp_settings)
        file_menu.addAction(self.ftp_settings_action)

        # Add Xbox Unity settings action
        self.xbox_unity_settings_action = QAction("&Xbox Unity Settings...", self)
        self.xbox_unity_settings_action.setIcon(
            self.icon_manager.create_icon("fa6s.gear")
        )
        self.icon_manager.register_widget_icon(
            self.xbox_unity_settings_action, "fa6s.gear"
        )
        self.xbox_unity_settings_action.setEnabled(True)
        self.xbox_unity_settings_action.triggered.connect(self.show_xboxunity_settings)
        file_menu.addAction(self.xbox_unity_settings_action)

        file_menu.addSeparator()

        self.exit_action = QAction("&Quit", self)
        self.exit_action.setShortcut("Ctrl+Q")
        self.exit_action.setIcon(qta.icon("fa6s.xmark"))
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
                # color=self.normal_color,
                # color_active=self.active_color,
                # color_disabled=self.disabled_color,
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
                "fa6b.usb",
                # color=self.normal_color,
                # color_active=self.active_color,
                # color_disabled=self.disabled_color,
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
        self.extract_iso_action.setIcon(qta.icon("fa6s.file-zipper"))
        self.extract_iso_action.triggered.connect(self.browse_for_iso)
        tools_menu.addAction(self.extract_iso_action)

        # Create GOD action
        self.create_god_action = QAction("&Create GOD...", self)
        self.create_god_action.setIcon(qta.icon("fa6s.compact-disc"))
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

        self.xbox360_action = QAction("Xbox &360", self)
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
        view_menu.setTitle("&View")

        self.theme_menu = view_menu.addMenu("&Theme")
        self.theme_menu.setIcon(
            qta.icon(
                "fa6s.palette",
                # color=self.normal_color,
                # color_active=self.active_color,
                # color_disabled=self.disabled_color,
            )
        )
        self.theme_action_group = QActionGroup(self)

        self.auto_theme_action = QAction("&Auto", self)
        self.auto_theme_action.setCheckable(True)
        self.auto_theme_action.setChecked(True)
        self.auto_theme_action.setIcon(
            qta.icon(
                "fa6s.circle-half-stroke",
                # color=self.normal_color,
                # color_active=self.active_color,
                # color_disabled=self.disabled_color,
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
                # color=self.normal_color,
                # color_active=self.active_color,
                # color_disabled=self.disabled_color,
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
                # color=self.normal_color,
                # color_active=self.active_color,
                # color_disabled=self.disabled_color,
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
                # color=self.normal_color,
                # color_active=self.active_color,
                # color_disabled=self.disabled_color,
            )
        )
        self.about_action.triggered.connect(self.show_about)
        help_menu.addAction(self.about_action)

        self.check_updates_action = QAction("&Check for Updates...", self)
        self.check_updates_action.setIcon(
            qta.icon(
                "fa6s.rotate",
                # color=self.normal_color,
                # color_active=self.active_color,
                # color_disabled=self.disabled_color,
            )
        )
        self.check_updates_action.triggered.connect(self._check_for_updates)
        help_menu.addAction(self.check_updates_action)

        self.licenses_action = QAction("&Licenses", self)
        self.licenses_action.setIcon(
            qta.icon(
                "fa6s.file-contract",
                # color=self.normal_color,
                # color_active=self.active_color,
                # color_disabled=self.disabled_color,
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

        # Skip transferred state check in FTP mode if not connected (don't block startup)
        if self.current_mode == "ftp":
            ftp_manager = get_ftp_manager()
            # Check if there's an EXISTING connection without trying to create one
            if not (ftp_manager._client and ftp_manager._client.is_connected()):
                # Just mark all as not transferred for now
                for game in self.games:
                    game.transferred = False
                return

        # Clear existing transferred state
        for game in self.games:
            game.transferred = False

            is_transferred = self._check_if_transferred(game)
            game.transferred = is_transferred

            # Update the table item state
            row = self._find_game_row(game.title_id)
            if row is not None:
                match self.current_platform:
                    case "xbox":
                        transferred_column = 5
                    case "xbox360" | "xbla":
                        transferred_column = 7

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
                UIUtils.show_warning(
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
                UIUtils.show_warning(
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
                UIUtils.show_warning(
                    self,
                    "Directory Not Accessible",
                    f"The selected directory is not accessible:\n{normalized_directory}\n\n"
                    "Please ensure the device is properly connected and try again.",
                )
                self.status_manager.show_message(
                    "Selected directory is not accessible", 5000
                )

    def browse_dlc_directory(self):
        """Open DLC directory selection dialog"""
        # Start at existing DLC directory if set, else home
        start_dir = (
            self.current_dlc_directory
            if self.current_dlc_directory and os.path.exists(self.current_dlc_directory)
            else (os.path.expanduser("~"))
        )

        directory = QFileDialog.getExistingDirectory(
            self,
            "Select DLC Directory",
            start_dir,
        )

        if directory:
            # Use DirectoryManager to set the directory
            if self.directory_manager.set_dlc_directory(directory):
                # The signal handlers will take care of updating UI and starting scan
                pass

    def _update_transfer_button_state(self):
        """Update transfer and remove button enabled state based on conditions"""
        has_games = len(self.games) > 0
        has_selected = self._get_selected_games_count() > 0

        if self.current_mode == "ftp":
            # For FTP mode, just check if settings are configured and target directory is set
            # Don't try to connect here as it's called frequently and can block the UI
            has_target = bool(
                self.ftp_settings
                and self.ftp_settings.get("host")
                and self.ftp_target_directories[self.current_platform]
            )
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
        self.toolbar_batch_dlc_install_action.setEnabled(has_games and has_target)

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
            UIUtils.show_information(
                self,
                "No Games Selected",
                "Please select games to transfer by checking the boxes.",
            )
            return

        # Calculate total size and check disk space
        total_size = sum(game.size_bytes for game in selected_games)
        size_formatted = UIUtils.format_file_size(total_size)

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
                available_formatted = UIUtils.format_file_size(available_space)
                QMessageBox.critical(
                    self,
                    "Insufficient Disk Space",
                    f"Not enough space on target device!\n\n"
                    f"Required: {size_formatted}\n"
                    f"Available: {available_formatted}\n"
                    f"Additional space needed: {UIUtils.format_file_size(total_size - available_space)}",
                )
                return
        else:
            available_space = None

        # Show confirmation with disk space info
        if available_space is not None and self.current_mode == "usb":
            available_formatted = UIUtils.format_file_size(available_space)
            remaining_after = available_space - total_size
            remaining_formatted = UIUtils.format_file_size(remaining_after)

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
                game = self._get_game_from_row(row)

                self._remove_game_from_target(game)

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

    def _start_transfer(self, games_to_transfer: List[GameInfo]):
        """Start the transfer process"""
        self.directory_manager.stop_watching_directory()

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
                current_platform=self.current_platform,
            )
        else:
            self.transfer_worker = FileTransferWorker(
                games_to_transfer,
                self.current_target_directory,
                max_workers=2,
                buffer_size=2 * 1024 * 1024,
                current_platform=self.current_platform,
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
                # color=self.normal_color,
                # color_active=self.active_color,
                # color_disabled=self.disabled_color,
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
        self.directory_manager.start_watching_directory()

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
                # If Xbox, column is 5
                # If XBLA or Xbox 360, column is 6 or 7 if DLCs
                show_dlcs = self.current_platform in ["xbox360", "xbla"]
                if show_dlcs:
                    status_column = 7
                else:
                    status_column = 5
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

        self.directory_manager.start_watching_directory()

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

        self.directory_manager.start_watching_directory()

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
            try:
                # Use persistent connection manager - don't block on connection
                ftp_manager = get_ftp_manager()
                ftp_client = ftp_manager.get_connection()

                # If we can't get a connection, just return False (don't block)
                if not ftp_client or not ftp_client.is_connected():
                    return False  # For extracted ISO games, always use game.name
                if getattr(game, "is_extracted_iso", False):
                    target_path = (
                        f"{self.current_target_directory.rstrip('/')}/{game.name}"
                    )
                    return ftp_client.directory_exists(target_path)
                else:
                    # For GoD games, check both game.name and title_id (for backward compatibility)
                    target_path_by_name = (
                        f"{self.current_target_directory.rstrip('/')}/{game.name}"
                    )
                    target_path_by_id = (
                        f"{self.current_target_directory.rstrip('/')}/{game.title_id}"
                    )

                    return ftp_client.directory_exists(
                        target_path_by_name
                    ) or ftp_client.directory_exists(target_path_by_id)

            except Exception:
                return False
        else:
            # For extracted ISO games, always use game.name
            if getattr(game, "is_extracted_iso", False):
                target_path = Path(self.current_target_directory) / game.name
                return target_path.exists() and target_path.is_dir()
            else:
                # For GoD games, check both game.name and title_id (for backward compatibility)
                target_path_by_name = Path(self.current_target_directory) / game.name
                target_path_by_id = Path(self.current_target_directory) / game.title_id

                return (
                    target_path_by_name.exists() and target_path_by_name.is_dir()
                ) or (target_path_by_id.exists() and target_path_by_id.is_dir())

    def browse_directory(self):
        """Open directory selection dialog using DirectoryManager"""
        start_dir = (
            self.current_directory
            if self.current_directory
            else os.path.expanduser("~")
        )

        directory = self.directory_manager.browse_directory(
            self, self.platform_names[self.current_platform], start_dir
        )

        if directory:
            # Use DirectoryManager to set the directory
            if self.directory_manager.set_current_directory(
                directory, self.current_platform
            ):
                # The signal handlers will take care of updating UI and starting scan
                pass

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

        # Clear current games list
        self.games.clear()
        self.game_manager.clear_games()  # Also clear GameManager's games

        # Save current directories for current platform
        if self.current_directory:
            self.platform_directories[self.current_platform] = self.current_directory
        if self.current_target_directory:
            self.usb_target_directories[self.current_platform] = (
                self.current_target_directory
            )

        # Save current table settings for current platform
        if hasattr(self.games_table, "horizontalHeader"):
            header = self.games_table.horizontalHeader()
            sort_column = header.sortIndicatorSection()
            sort_order = header.sortIndicatorOrder()
            self.settings_manager.save_table_settings(
                self.current_platform, header, sort_column, sort_order
            )

        # Update window title
        self.setWindowTitle(
            f"{APP_NAME} - {self.platform_names[platform]} - v{VERSION}"
        )

        # Stop watching current directory
        self.directory_manager.stop_watching_directory()

        # Switch to new platform
        self.current_platform = platform

        # Update platform label
        self.platform_label.setText(self.platform_names[platform])

        # Recreate table with appropriate columns for new platform
        self.setup_table()

        # Load source directory for new platform
        if self.platform_directories[platform]:
            self.current_directory = self.platform_directories[platform]
            self.directory_label.setText(self.current_directory)
            # Update DirectoryManager and start watching
            self.directory_manager.current_directory = self.current_directory
            self.directory_manager.start_watching_directory()
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
            "• <a href='https://pypi.org/project/psutil/'>psutil</a> (BSD License (BSD-3-Clause))<br>"
            "• <a href='https://pypi.org/project/darkdetect/'>darkdetect</a> (BSD License (BSD-3-Clause))<br>"
            "• <a href='https://pypi.org/project/PyQt6/'>PyQt6</a> (GPL-3.0-only)<br>"
            "• <a href='https://pypi.org/project/pyxbe/'>pyxbe</a> (MIT)<br>"
            "• <a href='https://pypi.org/project/QtAwesome/'>QtAwesome</a> (MIT)<br>"
            "• <a href='https://pypi.org/project/qt-material/'>qt-material</a> (BSD License (BSD-2-Clause))<br>"
            "• <a href='https://pypi.org/project/requests/'>requests</a> (Apache Software License (Apache-2.0))<br>"
            "• <a href='https://pypi.org/project/semver/'>semver</a> (BSD License (BSD-3-Clause))<br>"
            "<br>"
            "Thanks to the developers of <a href='https://github.com/antangelo/xdvdfs'>xdvdfs</a>, <a href='https://github.com/iliazeus/iso2god-rs'>iso2god-rs</a> and <a href='https://github.com/mLoaDs/XexTool'>XexTool</a>.<br>"
            "<br>"
            "pyxbe is used to extract Xbox icons and metadata.<br>"
            "XexTool is used to extract Xbox 360 icons and metadata.<br>"
            "<br>"
            "If either of those fail to extract an icon we download them from the below sources.<br>"
            "<br>"
            "<a href='https://github.com/MobCat/MobCats-original-xbox-game-list'>MobCats</a> for Xbox<br>"
            "<a href='https://github.com/XboxUnity'>XboxUnity</a> for Xbox 360"
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

        # palette = self.theme_manager.get_palette()

        # # Update colours
        # if self.theme_manager.should_use_dark_mode():
        #     self.normal_color = palette.COLOR_TEXT_1
        #     self.active_color = palette.COLOR_TEXT_1
        #     self.disabled_color = palette.COLOR_DISABLED
        # else:
        #     self.normal_color = palette.COLOR_BACKGROUND_6
        #     self.active_color = palette.COLOR_BACKGROUND_6
        #     self.disabled_color = palette.COLOR_DISABLED

        # Refresh table styling to apply theme-aware colors
        if hasattr(self, "games_table"):
            self._configure_table_appearance()

        # Ensure table header remains visible after theme changes
        if hasattr(self, "table_manager") and self.table_manager:
            self.table_manager.ensure_header_visible()

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

        # Load directories using DirectoryManager
        self.directory_manager.load_directories_from_settings(self.settings_manager)

        # Update local references from DirectoryManager
        self.platform_directories = self.directory_manager.platform_directories
        self.usb_target_directories = self.directory_manager.usb_target_directories
        self.ftp_target_directories = self.directory_manager.ftp_target_directories
        self.usb_cache_directory = self.directory_manager.usb_cache_directory
        self.usb_content_directory = self.directory_manager.usb_content_directory
        self.current_dlc_directory = self.directory_manager.dlc_directory

        # Ensure DLC directory is set
        if not self.current_dlc_directory:
            self.browse_dlc_directory()

        # Set current source directory
        if self.platform_directories[self.current_platform]:
            self.current_directory = self.platform_directories[self.current_platform]
            self.directory_label.setText(self.current_directory)
            # Use DirectoryManager for watching
            self.directory_manager.current_directory = self.current_directory
            self.directory_manager.start_watching_directory()

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
            # Quick FTP availability check - don't block
            ftp_manager = get_ftp_manager()
            ftp_client = ftp_manager.get_connection()

            if not ftp_client or not ftp_client.is_connected():
                # FTP not available, switch to USB mode
                self.current_mode = "usb"
                self.usb_mode_action.setChecked(True)
                self.ftp_mode_action.setChecked(False)
                self.status_manager.show_message(
                    "FTP server not available, switched to USB mode"
                )
            else:
                # FTP is available
                ftp_target = self.ftp_target_directories[self.current_platform]
                self.current_target_directory = ftp_target
                self.target_directory_label.setText(f"FTP: {ftp_target}")
                self.target_space_label.setText("(FTP)")
                self.status_manager.show_message("FTP mode active")

        # Set current target directory for USB mode
        if self.current_mode == "usb":
            target_dir = self.usb_target_directories[self.current_platform]
            text = target_dir
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
                    self.target_directory_label.setText(
                        "Target directory not available"
                    )
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

        # self.dlc_utils.reprocess_dlc(self.game_manager.get_game_name)

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
            self.directory_manager.platform_directories[self.current_platform] = (
                self.current_directory
            )

        # Update DirectoryManager with current state
        self.directory_manager.platform_directories = self.platform_directories
        self.directory_manager.usb_target_directories = self.usb_target_directories
        self.directory_manager.ftp_target_directories = self.ftp_target_directories
        self.directory_manager.usb_cache_directory = self.usb_cache_directory
        self.directory_manager.usb_content_directory = self.usb_content_directory

        # Save all directories using DirectoryManager
        self.directory_manager.save_directories_to_settings(self.settings_manager)

        # Save FTP settings
        self.settings_manager.save_ftp_settings(self.ftp_settings)

        # Save theme preference
        # self.settings_manager.save_theme_preference(
        #     self.theme_manager.dark_mode_override
        # )

        # Save table settings
        if hasattr(self.games_table, "horizontalHeader"):
            header = self.games_table.horizontalHeader()
            sort_column = header.sortIndicatorSection()
            sort_order = header.sortIndicatorOrder()
            self.settings_manager.save_table_settings(
                self.current_platform, header, sort_column, sort_order
            )

    # Directory watching is now handled by DirectoryManager
    # def start_watching_directory(self):
    #     """Start watching the current directory for changes"""
    #     if not self.current_directory:
    #         return
    #
    #     # Remove previous paths from watcher
    #     watched_paths = self.file_watcher.directories()
    #     if watched_paths:
    #         self.file_watcher.removePaths(watched_paths)
    #
    #     # Add current directory to watcher
    #     if os.path.exists(self.current_directory):
    #         self.file_watcher.addPath(self.current_directory)
    #
    # def stop_watching_directory(self):
    #     """Stop watching the current directory"""
    #     watched_paths = self.file_watcher.directories()
    #     if watched_paths:
    #         self.file_watcher.removePaths(watched_paths)

    def on_directory_changed(self, path: str):
        """Handle directory changes detected by file system watcher"""
        if path == self.current_directory:
            # Clear cache when directory changes
            self._clear_cache_for_directory()
            # Use timer to debounce rapid file system events
            self.scan_timer.stop()
            self.scan_timer.start(self.scan_delay)
            self.status_manager.show_message(
                f"Directory changed - rescanning in {self.scan_delay // 1000}s..."
            )

    def _on_directory_changed(self, new_directory: str):
        """Handle directory change from DirectoryManager"""
        self.current_directory = new_directory
        self.platform_directories[self.current_platform] = new_directory
        self.directory_label.setText(new_directory)
        self.toolbar_scan_action.setEnabled(True)
        self.status_manager.show_message(f"Selected directory: {new_directory}")

        # Clear cache for old directory
        self._clear_cache_for_directory()

        # Start scanning the new directory
        self.scan_directory(force=True)

    def _on_directory_files_changed(self):
        """Handle file changes in watched directory"""
        # Clear cache when directory changes
        self._clear_cache_for_directory()
        # Use timer to debounce rapid file system events
        self.scan_timer.stop()
        self.scan_timer.start(self.scan_delay)
        self.status_manager.show_message(
            f"Directory changed - rescanning in {self.scan_delay // 1000}s..."
        )

    def _on_scan_started(self):
        """Handle scan start from GameManager"""
        self._is_scanning = True
        # Disconnect the itemChanged signal to prevent firing during bulk operations
        try:
            self.games_table.itemChanged.disconnect(self._on_checkbox_changed)
        except TypeError:
            # Signal wasn't connected, which is fine
            pass

        # Clear previous results
        self.games.clear()
        self.games_table.setRowCount(0)

        # Setup progress bar
        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(0)
        self.toolbar_scan_action.setEnabled(False)
        self.browse_action.setEnabled(False)
        self.browse_target_action.setEnabled(False)

        self.status_manager.show_permanent_message("Scanning directory...")

    def _on_scan_progress(self, current: int, total: int):
        """Handle scan progress from GameManager"""
        if total > 0:
            percentage = int((current / total) * 100)
            self.progress_bar.setValue(percentage)

    def _on_scan_complete(self, games: List[GameInfo]):
        """Handle scan completion from GameManager"""
        self.games = games

        # Populate the table using TableManager - use refresh to replace all data
        if self.table_manager:
            self.table_manager.refresh_games(games)

        self._finalize_scan()

    def _on_scan_error(self, error_message: str):
        """Handle scan error from GameManager"""
        self.progress_bar.setVisible(False)
        self.toolbar_scan_action.setEnabled(True)
        self.browse_action.setEnabled(True)
        self.browse_target_action.setEnabled(True)
        self._is_scanning = False

        UIUtils.show_critical(
            self, "Scan Error", f"Failed to scan directory: {error_message}"
        )

    def _on_transfer_started(self):
        """Handle transfer start from TransferManager"""
        self.directory_manager.stop_watching_directory()

        # Disable UI elements during transfer
        self.toolbar_transfer_action.setEnabled(False)
        self.toolbar_remove_action.setEnabled(False)
        self.toolbar_batch_tu_action.setEnabled(False)
        self.browse_action.setEnabled(False)
        self.browse_target_action.setEnabled(False)

        # Show progress bar
        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(0)

    def _on_transfer_progress(self, current: int, total: int, current_game: str):
        """Handle transfer progress from TransferManager"""
        if total > 0:
            percentage = int((current / total) * 100)
            self.progress_bar.setValue(percentage)
            self.status_manager.show_permanent_message(
                f"Transferring {current_game} ({current}/{total})"
            )

    def _on_transfer_complete(self):
        """Handle transfer completion from TransferManager"""
        self.progress_bar.setVisible(False)
        self.toolbar_transfer_action.setEnabled(True)
        self.toolbar_remove_action.setEnabled(True)
        self.toolbar_batch_tu_action.setEnabled(True)
        self.browse_action.setEnabled(True)
        self.browse_target_action.setEnabled(True)

        self.directory_manager.start_watching_directory()
        self.status_manager.show_message("Transfer completed successfully")
        self._update_transfer_button_state()

    def _on_transfer_error(self, error_message: str):
        """Handle transfer error from TransferManager"""
        self.progress_bar.setVisible(False)
        self.toolbar_transfer_action.setEnabled(True)
        self.toolbar_remove_action.setEnabled(True)
        self.toolbar_batch_tu_action.setEnabled(True)
        self.browse_action.setEnabled(True)
        self.browse_target_action.setEnabled(True)

        self.directory_manager.start_watching_directory()
        UIUtils.show_critical(
            self, "Transfer Error", f"Transfer failed: {error_message}"
        )
        self._update_transfer_button_state()

    def _on_transfer_cancelled(self):
        """Handle transfer cancellation from TransferManager"""
        self.progress_bar.setVisible(False)
        self.toolbar_transfer_action.setEnabled(True)
        self.toolbar_remove_action.setEnabled(True)
        self.toolbar_batch_tu_action.setEnabled(True)
        self.browse_action.setEnabled(True)
        self.browse_target_action.setEnabled(True)

        self.directory_manager.start_watching_directory()
        self.status_manager.show_message("Transfer cancelled")
        self._update_transfer_button_state()

    def delayed_scan(self):
        """Perform delayed scan after directory changes"""
        if self.current_directory and os.path.exists(self.current_directory):
            self.scan_directory()

    def _stop_current_scan(self):
        """Stop any currently running scan"""
        # Use GameManager's safe stop method
        if self.game_manager.is_scanning:
            self.game_manager.stop_scan()

            # Reset UI state
            self.progress_bar.setVisible(False)
            self.toolbar_scan_action.setEnabled(True)
            self.browse_action.setEnabled(True)
            self.browse_target_action.setEnabled(True)

    def scan_directory(self, force: bool = False):
        """Start scanning the selected directory using GameManager"""
        if not self.current_directory:
            return

        # Stop any existing scan first
        self._stop_current_scan()

        # Try to load from cache first
        if self._load_scan_cache() and not force:
            self.status_manager.show_games_status()
            # Update transferred states in background
            QTimer.singleShot(100, self._rescan_transferred_state)
            return

        # Load cache data to pass to scanner for hash checking
        cache_data = self._get_cache_data()

        # Store current sort settings before clearing table
        if hasattr(self.games_table, "horizontalHeader"):
            header = self.games_table.horizontalHeader()
            self.current_sort_column = header.sortIndicatorSection()
            self.current_sort_order = header.sortIndicatorOrder()

        # Start scan using GameManager - use refresh_scan to clear previous games
        self.game_manager.refresh_scan(
            self.current_directory, self.current_platform, cache_data
        )

    def _finalize_scan(self):
        """Finalize the scan process"""
        self.progress_bar.setVisible(False)
        self.toolbar_scan_action.setEnabled(True)
        self.browse_action.setEnabled(True)
        self.browse_target_action.setEnabled(True)

        self._is_scanning = False

        game_count = len(self.games)

        # Re-enable sorting and restore previous sort settings
        self.games_table.setSortingEnabled(True)

        # Connect the checkbox signal AFTER all items are created
        self.games_table.itemChanged.connect(self._on_checkbox_changed)

        # Apply the previous sort order, or default to Game Name
        if hasattr(self, "current_sort_column") and hasattr(self, "current_sort_order"):
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

        # Update transferred states after scan completion
        if game_count > 0:
            QTimer.singleShot(100, self._rescan_transferred_state)

        if game_count == 0:
            self.status_manager.show_permanent_message("Scan complete - no games found")
        else:
            self.status_manager.show_games_status()

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

                    # Get size from the size column (column 5)
                    if self.current_platform in ["xbox360", "xbla"]:
                        size_item = self.games_table.item(row, 5)
                    else:
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
                    f"{selected_games} game{plural} selected ({UIUtils.format_file_size(selected_size)})"
                )
            else:
                self.status_bar.clearMessage()

    def download_missing_icons(self):
        """Download icons for games that don't have them cached"""
        missing_title_ids = []

        for game in self.games:
            if game.title_id not in self.icon_cache:
                # If extracted iso game then add the folder name instead of title ID
                if game.is_extracted_iso:
                    folder_name = Path(game.folder_path).name.upper()
                    missing_title_ids.append((game.title_id, folder_name))
                else:
                    missing_title_ids.append((game.title_id, game.title_id))

        if missing_title_ids:
            self.status_manager.show_message(
                f"Downloading {len(missing_title_ids)} game icons..."
            )

            # Start icon downloader thread
            self.icon_downloader = IconDownloader(
                missing_title_ids, self.current_platform, self.current_directory
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
        """Setup the games table widget using TableManager"""
        if self.table_manager:
            self.table_manager.set_platform(self.current_platform)
            # Reapply table appearance styling after platform change
            self._configure_table_appearance()
            self._load_table_settings()

    def _setup_table_columns(self, show_dlcs: bool):
        """Setup table column widths and resize modes"""
        header = self.games_table.horizontalHeader()

        header.installEventFilter(self)

        # Select column - fixed width
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        header.resizeSection(0, 50)  # Reduced width for better checkbox centering

        # Icon column - fixed width
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Fixed)
        header.resizeSection(1, 70)  # Slightly reduced for better proportions

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
        self.games_table.setAlternatingRowColors(False)
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
        # Use theme-appropriate colors that work with qt-material
        if self.theme_manager.should_use_dark_mode():
            # Dark theme colors - use a lighter header that matches qt-material dark theme
            header_bg_color = "#262a2e"
            header_bg_hover_color = "#3b3f42"
            header_text_color = "#ffffff"
            border_color = "#222529"
            border_hover_color = "#262a2e"
        else:
            # Light theme colors - use a slightly darker header than white
            header_bg_color = "#f5f5f5"  # Very light gray
            header_bg_hover_color = "#dcdcdc"
            header_text_color = "#3b3f42"
            border_color = "#e0e0e0"
            border_hover_color = "#f5f5f5"

        self.games_table.setStyleSheet(
            f"""
            QTableWidget {{
                gridline-color: transparent;
                border: none;
                margin: 0px;
                padding: 0px;
            }}
            QTableWidget::item {{
                padding-left: 16px;
            }}
            QTableWidget::indicator {{
                width: 16px;
                height: 16px;
                border: none;
                background: transparent;
            }}
            QTableWidget::item:first-child {{
                padding-left: 12px;
                border-left: none;
                border-top: none;
                border-bottom: 1px solid {border_color};
            }}
            QHeaderView::down-arrow, QHeaderView::up-arrow {{
                width: 12px;
                height: 12px;
                right: 4px;
            }}
            QHeaderView {{
                margin: 0px;
                padding: 0px;
            }}
            QHeaderView::section {{
                background-color: {header_bg_color};
                color: {header_text_color};
                border: none;
                border-right: 1px solid {border_color};
                border-bottom: 1px solid {border_color};
                padding: 4px;
                font-weight: normal;
            }}
            QHeaderView::section:hover {{
                background-color: {header_bg_hover_color};
                color: {header_text_color};
                border: none;
                border-right: 1px solid {border_hover_color};
                border-bottom: 1px solid {border_hover_color};
                padding: 4px;
                font-weight: normal;
            }}
            QHeaderView::section:first {{
                border-left: none;
            }}
            QHeaderView::section:last {{
                border-right: none;
            }}
        """
        )

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

    def _get_game_from_row(self, row: int) -> GameInfo:
        """Retrieve GameInfo object for a given table row"""
        title_id_item = self.games_table.item(row, 2)  # Title ID column
        if not title_id_item:
            return None

        title_id = title_id_item.text()
        for game in self.games:
            if game.title_id == title_id:
                return game
        return None

    def create_remove_action(self, row):
        game = self._get_game_from_row(row)

        return lambda: self.remove_game_from_target(game)

    def show_context_menu(self, position):
        """Show context menu when right-clicking on table"""
        item = self.games_table.itemAt(position)
        if item is None:
            return

        row = item.row()

        # Determine folder path column based on platform
        if self.current_platform == "xbox":
            folder_path_column = 6
        else:  # xbox360, xbla
            folder_path_column = 8

        # Get the Source Path from the appropriate column
        folder_item = self.games_table.item(row, folder_path_column)
        if folder_item is None:
            return

        # Get the actual folder path from UserRole data, not display text
        folder_path = folder_item.data(Qt.ItemDataRole.UserRole)
        if not folder_path:
            folder_path = folder_item.text()  # Fallback to text if UserRole is empty

        title_id = self.games_table.item(row, 2).text()
        game_name = self.games_table.item(row, 3).text()

        # Media ID and Size columns depend on platform
        if self.current_platform == "xbox":
            # Xbox has no Media ID column
            media_id = ""
            size_text = self.games_table.item(row, 4).text()
        else:
            # Xbox 360 and XBLA have Media ID column
            media_id = self.games_table.item(row, 4).text()
            size_text = self.games_table.item(row, 5).text()

        # Create context menu
        menu = QMenu(self)

        # Add "Open Folder" action
        open_folder_action = menu.addAction("Open Folder")
        open_folder_action.setIcon(self.icon_manager.create_icon("fa6s.folder-open"))
        open_folder_action.triggered.connect(
            lambda: SystemUtils.open_folder_in_explorer(folder_path, self)
        )

        # Create Copy submenu
        copy_submenu = menu.addMenu("Copy")
        copy_submenu.setIcon(self.icon_manager.create_icon("fa6s.copy"))

        # Add copy actions to submenu
        copy_title_id_action = copy_submenu.addAction("Title ID")
        copy_title_id_action.setIcon(self.icon_manager.create_icon("fa6s.hashtag"))
        copy_title_id_action.triggered.connect(
            lambda: SystemUtils.copy_to_clipboard(title_id)
        )

        copy_game_name_action = copy_submenu.addAction("Game Name")
        copy_game_name_action.setIcon(self.icon_manager.create_icon("fa6s.tag"))
        copy_game_name_action.triggered.connect(
            lambda: SystemUtils.copy_to_clipboard(game_name)
        )

        # Only add Media ID copy option for platforms that have it
        if self.current_platform in ["xbox360", "xbla"]:
            copy_media_id_action = copy_submenu.addAction("Media ID")
            copy_media_id_action.setIcon(self.icon_manager.create_icon("fa6s.id-card"))
            copy_media_id_action.triggered.connect(
                lambda: SystemUtils.copy_to_clipboard(media_id)
            )

        copy_size_action = copy_submenu.addAction("Size")
        copy_size_action.setIcon(self.icon_manager.create_icon("fa6s.weight-hanging"))
        copy_size_action.triggered.connect(
            lambda: SystemUtils.copy_to_clipboard(size_text)
        )

        copy_path_action = copy_submenu.addAction("Source Path")
        copy_path_action.setIcon(self.icon_manager.create_icon("fa6s.route"))
        copy_path_action.triggered.connect(
            lambda: SystemUtils.copy_to_clipboard(folder_path)
        )

        # Add "Title Updates" action
        title_updates_action = menu.addAction("Title Updates")
        title_updates_action.setIcon(self.icon_manager.create_icon("fa6s.download"))
        title_updates_action.triggered.connect(
            lambda: self._show_title_updates_dialog(folder_path, title_id)
        )

        # Add "Show DLCs" action (Xbox 360/XBLA only)
        if self.current_platform in ["xbox360", "xbla"]:
            # Get amount of DLCs
            dlc_count = self.dlc_utils.get_dlc_count(title_id)
            if dlc_count > 0:
                show_dlcs_action = menu.addAction("Manage DLC")
                show_dlcs_action.setIcon(self.icon_manager.create_icon("fa6s.cube"))
                show_dlcs_action.triggered.connect(
                    lambda: self._show_dlc_list_dialog(title_id)
                )

        # Add separator
        menu.addSeparator()

        # Add "Transfer" action
        transfer_action = menu.addAction("Transfer")
        transfer_action.setIcon(self.icon_manager.create_icon("fa6s.arrow-right"))
        transfer_action.triggered.connect(lambda: self._transfer_single_game(row))

        # Add "Remove from Target" action
        remove_action = menu.addAction("Remove from Target")
        remove_action.setIcon(self.icon_manager.create_icon("fa6s.trash"))
        remove_action.triggered.connect(self.create_remove_action(row))

        # Show the menu at the cursor position
        menu.exec(self.games_table.mapToGlobal(position))

    def _show_dlc_list_dialog(self, title_id: str):
        """Show dialog listing DLC files"""
        dialog = DLCListDialog(title_id, self)
        dialog.exec()

    def _show_title_updates_dialog(self, folder_path: str, title_id: str):
        """Show dialog with title updates information"""
        if not title_id:
            return

        # Show loading dialog (but only after a delay to avoid flashing)
        from PyQt6.QtWidgets import QProgressDialog
        from PyQt6.QtCore import Qt

        progress_dialog = QProgressDialog(
            "Reading game data from disk...",
            None,  # No cancel button
            0,
            0,  # Indeterminate progress
            self,
        )
        progress_dialog.setWindowTitle("Loading Title Updates")
        progress_dialog.setWindowModality(Qt.WindowModality.WindowModal)
        progress_dialog.setMinimumDuration(500)  # Only show if it takes more than 500ms
        progress_dialog.setValue(0)

        # Flag to track if worker completed
        worker_completed = False

        # Create and start the worker
        self.tu_fetch_worker = TitleUpdateFetchWorker(folder_path, title_id, self)

        def on_status_update(message):
            """Update the progress dialog message"""
            progress_dialog.setLabelText(message)

        def on_fetch_complete(media_id, updates):
            nonlocal worker_completed
            worker_completed = True
            progress_dialog.close()

            # Open the title updates dialog with the fetched data
            dialog = XboxUnityTitleUpdatesDialog(self, title_id, updates)

            # Connect download signals to main window progress display
            dialog.download_started.connect(self._on_tu_download_started)
            dialog.download_progress.connect(self._on_tu_download_progress)
            dialog.download_complete.connect(self._on_tu_download_complete)
            dialog.download_error.connect(self._on_tu_download_error)

            dialog.exec()

        def on_fetch_error(error_message):
            nonlocal worker_completed
            worker_completed = True
            progress_dialog.close()
            QMessageBox.information(
                self,
                "Title Updates",
                error_message,
            )

        # Connect signals
        self.tu_fetch_worker.status_update.connect(on_status_update)
        self.tu_fetch_worker.fetch_complete.connect(on_fetch_complete)
        self.tu_fetch_worker.fetch_error.connect(on_fetch_error)

        # Start the worker
        self.tu_fetch_worker.start()

    def batch_download_title_updates(self):
        """Batch download missing title updates for all games in target"""
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
        self.batch_tu_progress_dialog = BatchTUProgressDialog(
            total_files=len(target_games), parent=self
        )
        self.batch_tu_progress_dialog.setModal(True)
        self.batch_tu_progress_dialog.show()

        # Create and setup worker
        self.batch_tu_processor = BatchTitleUpdateProcessor()
        self.batch_tu_processor.setup_batch(target_games, self.current_mode)

        # Connect signals
        self.batch_tu_processor.progress_update.connect(self._on_batch_tu_progress)
        self.batch_tu_processor.game_started.connect(self._on_batch_tu_game_started)
        self.batch_tu_processor.game_completed.connect(self._on_batch_tu_game_completed)
        self.batch_tu_processor.update_downloaded.connect(
            self._on_batch_tu_update_downloaded
        )
        self.batch_tu_processor.update_progress.connect(self._on_batch_tu_file_progress)
        self.batch_tu_processor.update_progress_bytes.connect(
            self._on_batch_tu_progress_bytes
        )
        self.batch_tu_processor.status_update.connect(self._on_batch_tu_status_update)
        self.batch_tu_processor.searching.connect(self._on_batch_tu_searching)
        self.batch_tu_processor.batch_complete.connect(self._on_batch_tu_complete)
        self.batch_tu_processor.error_occurred.connect(self._on_batch_tu_error)

        # Connect cancel button
        self.batch_tu_progress_dialog.cancel_requested.connect(
            self.batch_tu_processor.stop_processing
        )
        self.batch_tu_progress_dialog.cancel_requested.connect(
            self._on_batch_tu_cancelled
        )

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
                            # Check if this is an extracted ISO game for FTP
                            is_extracted_iso = False
                            if self.current_platform == "xbox360":
                                # Check if default.xex exists by listing directory contents
                                try:
                                    success, dir_items, error_msg = (
                                        ftp_client.list_directory(folder_path)
                                    )
                                    if success:
                                        is_extracted_iso = any(
                                            not dir_item["is_directory"]
                                            and dir_item["name"].lower()
                                            == "default.xex"
                                            for dir_item in dir_items
                                        )
                                except Exception:
                                    pass  # If we can't check, assume it's not extracted ISO

                            game_name = self.game_manager.get_game_name(title_id)
                            games.append(
                                {
                                    "name": game_name,
                                    "title_id": title_id,
                                    "folder_path": folder_path,
                                    "folder_name": folder_name,
                                    "is_extracted_iso": is_extracted_iso,
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
                            # Check if this is an extracted ISO game
                            is_extracted_iso = False
                            if self.current_platform == "xbox360":
                                xex_path = Path(folder_path) / "default.xex"
                                is_extracted_iso = xex_path.exists()

                            game_name = self.game_manager.get_game_name(title_id)
                            games.append(
                                {
                                    "name": game_name,
                                    "title_id": title_id,
                                    "folder_path": folder_path,
                                    "folder_name": folder_name,
                                    "is_extracted_iso": is_extracted_iso,
                                }
                            )
            except Exception as e:
                print(f"[ERROR] Failed to scan target directory: {e}")

        return games

    def _extract_title_id(self, folder_name: str, folder_path: str):
        """Extract title ID from folder name or path"""
        # For XBLA, the folder name is always the title ID
        if self.current_platform == "xbla":
            # Check if folder name looks like a hex title ID (8 characters)
            if len(folder_name) == 8 and all(
                c in "0123456789ABCDEFabcdef" for c in folder_name
            ):
                return folder_name.upper()
            return None

        # For Xbox 360, check if it's an extracted ISO game first
        if self.current_platform == "xbox360":
            folder_path_obj = Path(folder_path)

            # Check if this is an extracted ISO game (has default.xex)
            xex_path = folder_path_obj / "default.xex"
            if xex_path.exists():
                try:
                    # Use xextool to extract the actual title ID from XEX
                    xex_info = SystemUtils.extract_xex_info(str(xex_path))
                    if xex_info and xex_info.get("title_id"):
                        return xex_info["title_id"]
                except Exception as e:
                    print(f"Error extracting title ID from XEX: {e}")

            # For GoD format games, folder name is the title ID
            # Check if folder name looks like a hex title ID (8 characters)
            if len(folder_name) == 8 and all(
                c in "0123456789ABCDEFabcdef" for c in folder_name
            ):
                return folder_name.upper()

            # If not a GoD format and no XEX found, return None
            return None

        # For Xbox, need to extract from internal structure
        elif self.current_platform == "xbox":
            try:
                # Look for default.xbe or header files

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
        # For XBLA, the folder name is always the title ID
        if self.current_platform == "xbla":
            # Check if folder name looks like a hex title ID (8 characters)
            if len(folder_name) == 8 and all(
                c in "0123456789ABCDEFabcdef" for c in folder_name
            ):
                return folder_name.upper()
            return None

        # For Xbox 360, check if it's an extracted ISO game first
        if self.current_platform == "xbox360":
            # Check if this is an extracted ISO game (has default.xex)
            try:
                # Try to check if default.xex exists by listing directory contents
                success, items, error_msg = ftp_client.list_directory(folder_path)
                if success:
                    has_default_xex = any(
                        not item["is_directory"]
                        and item["name"].lower() == "default.xex"
                        for item in items
                    )

                    if has_default_xex:
                        # Download default.xex temporarily to extract title ID
                        default_xex_path = f"{folder_path.rstrip('/')}/default.xex"

                        with tempfile.NamedTemporaryFile(
                            delete=False, suffix=".xex"
                        ) as temp_file:
                            temp_path = temp_file.name

                        try:
                            success, message = ftp_client.download_file(
                                default_xex_path, temp_path
                            )
                            if success:
                                xex_info = SystemUtils.extract_xex_info(temp_path)
                                if xex_info and xex_info.get("title_id"):
                                    return xex_info["title_id"]
                        finally:
                            # Clean up temporary file
                            if os.path.exists(temp_path):
                                os.unlink(temp_path)
            except Exception as e:
                print(f"Error extracting title ID from FTP XEX: {e}")

            # For GoD format games, folder name is the title ID
            # Check if folder name looks like a hex title ID (8 characters)
            if len(folder_name) == 8 and all(
                c in "0123456789ABCDEFabcdef" for c in folder_name
            ):
                return folder_name.upper()

            # If not a GoD format and no XEX found, return None
            return None

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

    def _on_batch_tu_progress(self, current: int, total: int):
        """Handle batch processing progress"""
        if hasattr(self, "batch_tu_progress_dialog"):
            self.batch_tu_progress_dialog.update_progress(current)

    def _on_batch_tu_game_started(self, game_name: str):
        """Handle batch game processing started"""
        if hasattr(self, "batch_tu_progress_dialog"):
            self.batch_tu_progress_dialog.update_progress(
                self.batch_tu_progress_dialog.progress_bar.value(),
                f"Processing: {game_name}",
            )

    def _on_batch_tu_game_completed(self, game_name: str, updates_found: int):
        """Handle batch game processing completed"""
        # Reset file progress when a game completes
        if hasattr(self, "batch_tu_progress_dialog"):
            self.batch_tu_progress_dialog.reset_file_progress()

    def _on_batch_tu_update_downloaded(
        self, game_name: str, version: str, file_path: str
    ):
        """Handle successful update download"""
        pass

    def _on_batch_tu_file_progress(self, update_name: str, progress: int):
        """Handle per-file progress updates"""
        if hasattr(self, "batch_tu_progress_dialog"):
            self.batch_tu_progress_dialog.update_file_progress(update_name, progress)

    def _on_batch_tu_progress_bytes(
        self, update_name: str, current_bytes: int, total_bytes: int
    ):
        """Handle progress with bytes for time remaining calculation (includes speed)"""
        if hasattr(self, "batch_tu_progress_dialog"):
            self.batch_tu_progress_dialog.update_progress_with_speed(
                current_bytes, total_bytes
            )

    def _on_batch_tu_status_update(self, status_message: str):
        """Handle status updates during processing"""
        if hasattr(self, "batch_tu_progress_dialog"):
            self.batch_tu_progress_dialog.update_status(status_message)

    def _on_batch_tu_searching(self, is_searching: bool):
        """Handle indeterminate progress during search phase"""
        if hasattr(self, "batch_tu_progress_dialog"):
            if is_searching:
                self.batch_tu_progress_dialog.set_file_progress_indeterminate()
            else:
                self.batch_tu_progress_dialog.set_file_progress_determinate()

    def _on_batch_tu_complete(self, total_games: int, total_updates: int):
        """Handle batch processing completion"""
        if hasattr(self, "batch_tu_progress_dialog"):
            self.batch_tu_progress_dialog.close()
            del self.batch_tu_progress_dialog
        if hasattr(self, "batch_tu_processor"):
            self.batch_tu_processor.quit()
            self.batch_tu_processor.wait()
            del self.batch_tu_processor

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

    def _on_batch_tu_error(self, error_message: str):
        """Handle batch processing error"""
        if hasattr(self, "batch_tu_progress_dialog"):
            self.batch_tu_progress_dialog.close()
            del self.batch_tu_progress_dialog
        if hasattr(self, "batch_tu_processor"):
            self.batch_tu_processor.quit()
            self.batch_tu_processor.wait()
            del self.batch_tu_processor

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

    def _on_batch_tu_cancelled(self):
        """Handle batch processing cancellation"""
        if hasattr(self, "batch_tu_progress_dialog"):
            self.batch_tu_progress_dialog.close()
            del self.batch_tu_progress_dialog
        if hasattr(self, "batch_tu_processor"):
            self.batch_tu_processor.quit()
            self.batch_tu_processor.wait()
            del self.batch_tu_processor

        # Re-enable toolbar actions
        self.toolbar_transfer_action.setEnabled(True)
        self.toolbar_remove_action.setEnabled(True)
        self.toolbar_batch_tu_action.setEnabled(True)
        self.browse_action.setEnabled(True)
        self.browse_target_action.setEnabled(True)

        self.status_manager.show_message("Batch title update download cancelled")

    def remove_game_from_target(self, game):
        # Removed target is always title_id for XBLA and folder_name for Xbox
        # Xbox 360 is either title_id or folder_name, we need to check both
        match self.current_platform:
            case "xbox":
                remove_target = game.name
            case "xbla":
                remove_target = game.title_id
            case "xbox360":
                if game.is_extracted_iso:
                    remove_target = game.name
                else:
                    remove_target = game.title_id

        if self.current_mode == "ftp":
            target_path = f"{self.current_target_directory.rstrip('/')}/{remove_target}"
        else:
            target_path = str(Path(self.current_target_directory) / remove_target)

        msg_box = QMessageBox(self)
        msg_box.setWindowTitle("Confirm Removal")
        msg_box.setText(
            f"Are you sure you want to remove {game.name}?\n\n{target_path}"
        )
        msg_box.setStandardButtons(
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel
        )
        msg_box.setDefaultButton(QMessageBox.StandardButton.Cancel)

        if msg_box.exec() == QMessageBox.StandardButton.Yes:
            self._remove_game_from_target(game)

    def _remove_game_from_target(self, game):
        """Remove game from target directory"""
        if game.title_id and game.name:
            # Xbox 360 we need to check both title_id and folder_name
            match self.current_platform:
                case "xbox":
                    remove_target = game.name
                case "xbla":
                    remove_target = game.title_id
                case "xbox360":
                    if game.is_extracted_iso:
                        remove_target = game.name
                    else:
                        remove_target = game.title_id

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
                            f"Removed {game.name} from FTP server"
                        )

                        # Update transferred status in table
                        for row in range(self.games_table.rowCount()):
                            title_item = self.games_table.item(row, 2)
                            if title_item and title_item.text() == game.title_id:
                                # Determine the correct column index based on platform
                                # Xbox 360 and XBLA have an extra column for Media ID
                                match self.current_platform:
                                    case "xbox":
                                        transferred_column = 5
                                    case "xbox360" | "xbla":
                                        transferred_column = 7
                                status_item = self.games_table.item(
                                    row, transferred_column
                                )
                                if status_item:
                                    status_item.setText("❌")
                                    status_item.setData(Qt.ItemDataRole.UserRole, False)
                                break
                    else:
                        QMessageBox.warning(
                            self,
                            "FTP Removal Failed",
                            f"Failed to remove {game.name} from FTP server:\n{message}",
                        )

                except Exception as e:
                    QMessageBox.critical(
                        self,
                        "FTP Error",
                        f"An error occurred while removing {game.name}:\n{str(e)}",
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
                            f"Removed {game.name} from target directory"
                        )

                        # Update transferred status in table
                        for row in range(self.games_table.rowCount()):
                            title_item = self.games_table.item(row, 2)
                            if title_item and title_item.text() == game.title_id:
                                # Determine the correct column index based on platform
                                # Xbox 360 and XBLA have an extra column for Media ID
                                match self.current_platform:
                                    case "xbox":
                                        transferred_column = 5
                                    case "xbox360" | "xbla":
                                        transferred_column = 7
                                status_item = self.games_table.item(
                                    row, transferred_column
                                )
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
                        f"Failed to remove {game.name}:\n{str(e)}",
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
        self.directory_manager.stop_watching_directory()

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
                try:
                    # Use persistent connection manager for fast check
                    ftp_manager = get_ftp_manager()
                    ftp_client = ftp_manager.get_connection()

                    if not ftp_client or not ftp_client.is_connected():
                        return False

                    # Check if directory exists
                    return ftp_client.directory_exists(target_path)

                except Exception as e:
                    print(f"FTP error checking target directory: {e}")
                    return False
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
                try:
                    # Use persistent connection manager for fast check
                    ftp_manager = get_ftp_manager()
                    ftp_client = ftp_manager.get_connection()

                    if not ftp_client or not ftp_client.is_connected():
                        return False

                    # Check if directory exists
                    return ftp_client.directory_exists(target_path)

                except Exception as e:
                    print(f"FTP error checking cache directory: {e}")
                    return False
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
                try:
                    # Use persistent connection manager for fast check
                    ftp_manager = get_ftp_manager()
                    ftp_client = ftp_manager.get_connection()

                    if not ftp_client or not ftp_client.is_connected():
                        return False

                    # Check if directory exists
                    return ftp_client.directory_exists(target_path)

                except Exception as e:
                    print(f"FTP error checking content directory: {e}")
                    return False
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
                # color=self.normal_color,
                # color_active=self.active_color,
                # color_disabled=self.disabled_color,
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

        # Extract current file - this will call the sequential extraction logic
        self._extract_iso()

    def _extract_iso(self):
        """Extract ISO with xdvdfs"""
        if not self.iso_path:
            QMessageBox.warning(
                self, "No files selected", "Please select an ISO/ZIP file to extract."
            )
            return

        # If a zip file, the unified dialog will handle ZIP extraction automatically
        if self.iso_path.lower().endswith(".zip"):
            # Extract to directory named after ZIP file
            folder_path = (
                os.path.dirname(self.iso_path)
                + f"/{os.path.basename(self.iso_path).replace('.zip', '')}"
            )
            # Check if we're in batch mode and not the first file
            is_batch_mode = hasattr(self, "current_extraction_batch")
            is_first_file = (
                not is_batch_mode or self.current_extraction_batch_index == 0
            )
            self._extract_iso_directly(
                self.iso_path, folder_path, reuse_dialog=not is_first_file
            )
        else:
            # ISO selected directly, extract to its own directory
            folder_path = (
                os.path.dirname(self.iso_path)
                + f"/{os.path.basename(self.iso_path).replace('.iso', '')}"
            )

            self.temp_iso_path = self.iso_path  # Store for cleanup later

            # Check if we're in batch mode and not the first file
            is_batch_mode = hasattr(self, "current_extraction_batch")
            is_first_file = (
                not is_batch_mode or self.current_extraction_batch_index == 0
            )
            self._extract_iso_directly(
                self.iso_path, folder_path, reuse_dialog=not is_first_file
            )

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

            # Use reuse_dialog for batch operations
            reuse_dialog = hasattr(self, "current_extraction_batch")
            self._extract_iso_directly(
                extracted_iso_path, extract_to_dir, reuse_dialog=reuse_dialog
            )
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

    def _extract_iso_directly(self, iso_path, extract_to_dir, reuse_dialog=False):
        """Extract ISO directly with xdvdfs using progress dialog"""
        # Ensure the output directory exists
        os.makedirs(extract_to_dir, exist_ok=True)

        if reuse_dialog and self._current_processing_dialog:
            # Reuse existing dialog for batch operations
            dialog = self._current_processing_dialog
            # Reset with explicit parameter names to ensure correct assignment
            dialog.reset_for_new_operation(
                operation_type="extract",
                input_path=iso_path,
                output_path=extract_to_dir,
                is_batch_mode=True,
            )
            dialog.output_text.clear()

            # Reconnect signals for new operation
            dialog.processing_complete.disconnect()
            dialog.processing_error.disconnect()
            dialog.processing_complete.connect(self._on_extraction_finished)
            dialog.processing_error.connect(self._on_extraction_failed)
        else:
            # Create new dialog
            dialog = FileProcessingDialog(
                self,
                operation_type="extract",
                input_path=iso_path,
                output_path=extract_to_dir,
            )

            # Connect unified signals
            dialog.processing_complete.connect(self._on_extraction_finished)
            dialog.processing_error.connect(self._on_extraction_failed)

            # Store reference for potential reuse
            self._current_processing_dialog = dialog

        # Start the extraction process
        if not dialog.start_processing():
            # Failed to start extraction
            return

        if not reuse_dialog:
            # Show the dialog (modal) and handle the result
            result = dialog.exec()
            if result == QDialog.DialogCode.Rejected:
                # User cancelled or dialog was closed
                self._current_processing_dialog = None
                self._on_extraction_cancelled()
        # When reusing dialog, it's already shown - just continue processing

    def _update_zip_progress(self, progress: int):
        """Update progress bar for ZIP extraction"""
        self.progress_bar.setValue(progress)

    def _on_file_extracted(self, filename: str):
        """Handle individual file extraction"""
        self.file_path = filename

    def _on_zip_extraction_error(self, error_message: str):
        """Handle ZIP extraction error"""
        self.progress_bar.setVisible(False)

        QMessageBox.critical(
            self,
            "ZIP Extraction Error",
            f"Failed to extract ZIP file:\n{error_message}",
        )

    def _on_extraction_finished(self):
        """Handle extraction process finished"""
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

    def _on_extraction_failed(self, error_message: str):
        """Handle extraction process failed"""
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

        # Show error message
        QMessageBox.critical(
            self,
            "Extraction Error",
            f"Failed to extract ISO file:\n{error_message}",
        )

        # If we're in batch mode, move to next file
        if hasattr(self, "current_extraction_batch"):
            self._move_to_next_extraction_file()

    def _on_extraction_cancelled(self):
        """Handle extraction process cancelled"""
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

        # Start with first file
        self._create_next_god_file()

    def _create_next_god_file(self):
        """Create the next GOD file in the batch"""
        if self.current_god_batch_index >= len(self.current_god_batch):
            # Batch complete
            self._on_batch_god_creation_complete()
            return

        self.god_file_path = self.current_god_batch[self.current_god_batch_index]

        # Check if it's a ZIP or ISO - the unified dialog will handle ZIP extraction automatically
        # Use reuse_dialog=True for batch operations to replace instead of showing new dialogs
        # Only show dialog for the first file, others reuse silently
        is_first_file = self.current_god_batch_index == 0

        if self.god_file_path.lower().endswith(".zip"):
            self._create_god_directly(
                self.god_file_path,
                reuse_dialog=not is_first_file,
            )
        else:
            # ISO file directly
            self._create_god_directly(
                self.god_file_path,
                reuse_dialog=not is_first_file,
            )

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

            # Create GOD from extracted ISO - use reuse_dialog for batch operations
            self._create_god_directly(extracted_iso_path, reuse_dialog=True)
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

    def _cancel_batch_god_creation(self):
        """Cancel the batch GOD creation process"""
        self.progress_bar.setVisible(False)

        # Clean up any temp files created so far
        self._cleanup_god_temp_isos()

    def _on_god_creation_finished(self):
        """Handle GOD creation process finished"""
        # Clean up temp ISOs for single file
        self._cleanup_god_temp_isos()

        # If we're in batch mode, move to next file
        if hasattr(self, "current_god_batch"):
            self._move_to_next_god_file()
        else:
            # Single file mode - rescan directory to show new GOD files
            if self.current_directory and self.current_platform == "xbox360":
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
            delattr(self, "total_god_batch_files")

        # Rescan directory to show new GOD files
        if self.current_directory and self.current_platform == "xbox360":
            self.scan_directory(force=True)

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

        # Check if it's a ZIP file - the unified dialog will handle ZIP extraction automatically
        if self.god_file_path.lower().endswith(".zip"):
            self._create_god_directly(self.god_file_path)
        else:
            # ISO file directly
            self._create_god_directly(self.god_file_path)

    def _extract_zip_then_create_god(self, zip_path):
        """Extract ZIP file first, then create GOD from the ISO"""
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
            self._create_god_directly(extracted_iso_path)

    def _on_god_zip_extraction_error(self, error_message: str):
        """Handle ZIP extraction error during GOD creation"""
        self.progress_bar.setVisible(False)

    def _create_god_directly(self, iso_path, reuse_dialog=False):
        """Create GOD file directly with iso2god-x86_64-windows.exe using progress dialog"""
        usb_content_dir = self.settings_manager.load_usb_content_directory()
        dest_dir = os.path.join(usb_content_dir, "0000000000000000")

        # Ensure the output directory exists
        os.makedirs(dest_dir, exist_ok=True)

        if reuse_dialog and self._current_processing_dialog:
            # Reuse existing dialog for batch operations
            dialog = self._current_processing_dialog
            # Reset with explicit parameter names to ensure correct assignment
            dialog.reset_for_new_operation(
                operation_type="create_god",
                input_path=iso_path,
                output_path=dest_dir,
                is_batch_mode=True,
            )

            # Reconnect signals for new operation
            dialog.processing_complete.disconnect()
            dialog.processing_error.disconnect()
            # Use unified handler that checks for batch mode
            dialog.processing_complete.connect(self._on_god_creation_finished)
            dialog.processing_error.connect(self._on_god_creation_failed)
        else:
            # Create new dialog
            dialog = FileProcessingDialog(
                self,
                operation_type="create_god",
                input_path=iso_path,
                output_path=dest_dir,
            )

            # Connect unified signals
            dialog.processing_complete.connect(self._on_god_creation_finished)
            dialog.processing_error.connect(self._on_god_creation_failed)

            # Store reference for potential reuse
            self._current_processing_dialog = dialog

        # Start the GOD creation process
        if not dialog.start_processing():
            # Failed to start GOD creation
            return

        if not reuse_dialog:
            # Show the dialog (modal) and handle the result
            result = dialog.exec()
            if result == QDialog.DialogCode.Rejected:
                # User cancelled or dialog was closed
                self._current_processing_dialog = None
                self._on_god_creation_cancelled()
        # When reusing dialog, it's already shown - just continue processing

    def _on_god_creation_failed(self, error_message: str):
        """Handle GOD creation process failed"""
        # Clean up temporary ISO files if they exist
        self._cleanup_god_temp_isos()

        # Show error message
        QMessageBox.critical(
            self,
            "GOD Creation Error",
            f"Failed to create GOD file:\n{error_message}",
        )

        # If we're in batch mode, move to next file
        if hasattr(self, "current_god_batch"):
            self._move_to_next_god_file()

    def _on_god_creation_cancelled(self):
        """Handle GOD creation process cancelled"""
        # Clean up temporary ISO files if they exist
        self._cleanup_god_temp_isos()

        # If we're in batch mode, move to next file
        if hasattr(self, "current_god_batch"):
            self._move_to_next_god_file()

    def _check_required_tools(self):
        """Check for required executables and set up watchers"""
        self.xdvdfs_path = os.path.join(os.getcwd(), "xdvdfs.exe")
        self.iso2god_path = os.path.join(os.getcwd(), "iso2god-x86_64-windows.exe")
        self.xextool_path = os.path.join(os.getcwd(), "XexTool.exe")

        self.xdvdfs_found = os.path.exists(self.xdvdfs_path)
        self.iso2god_found = os.path.exists(self.iso2god_path)
        self.xextool_found = os.path.exists(self.xextool_path)

        # Update status bar
        self._update_tools_status()

        # If all tools are found, no need for dialog
        if self.xdvdfs_found and self.iso2god_found and self.xextool_found:
            return

        # Set up file system watchers
        self._setup_tools_watchers()

        # Show download dialog
        self._show_tools_download_dialog()

    def _update_tools_status(self):
        """Update status bar with tools status"""
        xdvdfs_status = "✔️" if self.xdvdfs_found else "❌"
        iso2god_status = "✔️" if self.iso2god_found else "❌"
        xextool_status = "✔️" if self.xextool_found else "❌"

        # Update download button
        if self.xdvdfs_found:
            xdvdfs_button = self.findChild(QPushButton, "xdvdfs_download_button")
            if xdvdfs_button:
                xdvdfs_button.setEnabled(False)
                xdvdfs_button.setText("✔️ Downloaded")
        if self.iso2god_found:
            iso2god_button = self.findChild(QPushButton, "iso2god_download_button")
            if iso2god_button:
                iso2god_button.setEnabled(False)
                iso2god_button.setText("✔️ Downloaded")
        if self.xextool_found:
            xextool_button = self.findChild(QPushButton, "xextool_download_button")
            if xextool_button:
                xextool_button.setEnabled(False)
                xextool_button.setText("✔️ Downloaded")

        # If all tools are now found, close the dialog and update status bar
        if self.xdvdfs_found and self.iso2god_found and self.xextool_found:
            if hasattr(self, "tools_dialog") and self.tools_dialog:
                self.status_manager.show_message("✔️ Required tools are ready for use")
                close_button = self.tools_dialog.findChild(QPushButton, "Close")
                if close_button:
                    close_button.setText("Restarting...")
                    close_button.setEnabled(False)
                QTimer.singleShot(2000, self._on_tools_added)
            return

        status_text = f"xdvdfs: {xdvdfs_status} | iso2god: {iso2god_status} | xextool: {xextool_status}"
        self.status_manager.show_message(status_text)

    def _on_tools_added(self):
        """Handle the event when all required tools are added"""
        # Close the dialog if open after a short delay
        self.tools_dialog.accept
        delattr(self, "tools_dialog")
        # Clear the scan cache to force rescan
        self._clear_cache_for_directory()
        # Restart the application
        SystemUtils.restart_app(self)

    def _show_tools_download_dialog(self):
        """Show dialog with download links for missing tools"""
        dialog = QDialog(self)
        dialog.setWindowTitle("Required Tools Missing")
        dialog.setModal(True)

        layout = QVBoxLayout(dialog)

        label = QLabel("The following tools are required but not found:")
        layout.addWidget(label)

        # xdvdfs download
        if not self.xdvdfs_found:
            api_url = "https://api.github.com/repos/antangelo/xdvdfs/releases/latest"
            try:
                response = requests.get(api_url, timeout=5)
                response.raise_for_status()
                release_info = response.json()
                assets = release_info.get("assets", [])
                download_url = None
                for asset in assets:
                    if (
                        asset.get("name", "").endswith(".zip")
                        and "windows" in asset.get("name", "").lower()
                    ):
                        download_url = asset.get("browser_download_url")
                        break
                if not download_url:
                    download_url = "https://github.com/antangelo/xdvdfs/releases/download/v0.8.3/xdvdfs-windows-1cc850bf1b3487fad7ec7c9eed01d83e8fc75ba4.zip"

                xdvdfs_layout = QHBoxLayout()
                xdvdfs_label = QLabel("xdvdfs.exe:")
                xdvdfs_button = QPushButton("Download")
                xdvdfs_button.setObjectName("xdvdfs_download_button")
                xdvdfs_button.clicked.connect(
                    lambda: QDesktopServices.openUrl(QUrl(download_url))
                )
                xdvdfs_layout.addWidget(xdvdfs_label)
                xdvdfs_layout.addWidget(xdvdfs_button)
                layout.addLayout(xdvdfs_layout)
            except requests.RequestException as e:
                print(f"Error fetching xdvdfs download URL: {e}")

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
            "• xdvdfs and XexTool will be extracted from the ZIP automatically"
        )
        instructions.setWordWrap(True)
        layout.addWidget(instructions)

        close_button = QPushButton("Close")
        close_button.setObjectName("Close")
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

                # Handle xdvdfs ZIP
                # Sample file name to check against: xdvdfs-windows-1cc850bf1b3487fad7ec7c9eed01d83e8fc75ba4.zip
                if (
                    filename.startswith("xdvdfs-windows-")
                    and filename.endswith(".zip")
                    and not self.xdvdfs_found
                ):
                    if is_downloads:
                        # Move ZIP to current directory
                        dest_path = os.path.join(os.getcwd(), filename)
                        shutil.move(file_path, dest_path)
                        self._extract_xdvdfs_zip(dest_path)
                    else:
                        # Already in current directory, extract it
                        self._extract_xdvdfs_zip(file_path)

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

    def _extract_xdvdfs_zip(self, zip_path):
        """Extract xdvdfs.exe from the ZIP file"""
        try:
            extracted = False
            with zipfile.ZipFile(zip_path, "r") as zip_ref:
                # Look for the exe file in the ZIP, it is under the `artifacts` subdirectory, ensure we only extract that file into the current directory
                for zip_info in zip_ref.infolist():
                    if zip_info.filename == "xdvdfs.exe":
                        zip_info.filename = os.path.basename(zip_info.filename)
                        zip_ref.extract(zip_info, os.getcwd())
                        extracted = True
                        break

            if extracted:
                self.xdvdfs_found = True
                self._update_tools_status()

                os.remove(zip_path)

        except Exception as e:
            print(f"Error extracting xdvdfs: {e}")

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
                    "media_id": getattr(game, "media_id", None),
                    "is_extracted_iso": getattr(game, "is_extracted_iso", False),
                    "dlc_count": getattr(game, "dlc_count", 0),
                    "file_hash": getattr(game, "file_hash", None),
                }
                cache_data["games"].append(game_data)

            with open(cache_file, "w", encoding="utf-8") as f:
                json.dump(cache_data, f, indent=2)

        except Exception as e:
            print(f"Error saving scan cache: {e}")

    def _get_cache_data(self) -> Optional[dict]:
        """Load cache data without populating the UI (for hash checking during scan)"""
        if not self.current_directory:
            return None

        cache_file = self._get_cache_file_path()
        if not cache_file or not cache_file.exists():
            return None

        try:
            with open(cache_file, "r", encoding="utf-8") as f:
                cache_data = json.load(f)
            return cache_data
        except Exception as e:
            print(f"Error loading cache data: {e}")
            return None

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
            cached_games = []

            for game_data in cache_data["games"]:
                game_info = GameInfo(
                    title_id=game_data["title_id"],
                    name=game_data["name"],
                    folder_path=game_data["folder_path"],
                    size_bytes=game_data["size_bytes"],
                    size_formatted=game_data["size_formatted"],
                    is_extracted_iso=game_data.get("is_extracted_iso", False),
                    dlc_count=game_data.get("dlc_count", 0),
                    file_hash=game_data.get("file_hash"),
                )
                game_info.transferred = game_data.get("transferred", False)
                game_info.last_modified = game_data.get("last_modified", 0)
                game_info.media_id = game_data.get("media_id")  # Handle media_id field

                cached_games.append(game_info)

            # Use TableManager to populate the table consistently
            self.games = cached_games

            if self.table_manager:
                self.table_manager.refresh_games(self.games)

            if self.game_manager:
                self.game_manager.games = self.games

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
                try:
                    ftp_manager = get_ftp_manager()
                    ftp_client = ftp_manager.get_connection()
                    if ftp_client and ftp_client.is_connected():
                        is_available = ftp_client.directory_exists(
                            self.current_target_directory
                        )
                        if not is_available:
                            self.status_manager.show_message(
                                "FTP target directory not accessible"
                            )
                    else:
                        self.status_manager.show_message("FTP connection not available")
                except Exception as e:
                    self.status_manager.show_message(f"FTP check failed: {e}")
        else:
            self.status_manager.show_message(f"FTP connection failed: {message}")
            # Optionally switch to USB mode or show warning
            QMessageBox.warning(
                self,
                "FTP Connection Failed",
                f"Cannot connect to FTP server on startup:\n{message}\n\n"
                "FTP operations will not be available until connection is restored.",
            )

    def _on_batch_dlc_import_progress(
        self, current: int, total: int, current_file: str = ""
    ):
        """Update batch DLC import progress dialog."""
        self.dlc_import_progress_dialog.update_progress(
            current, f"Importing: {current_file} ({current}/{total})"
        )

    def _on_batch_dlc_import_finished(self):
        """Handle batch DLC import completion."""
        if hasattr(self, "dlc_import_progress_dialog"):
            self.dlc_import_progress_dialog.close()
            del self.dlc_import_progress_dialog
        if hasattr(self, "dlc_batch_worker"):
            self.dlc_batch_worker.quit()
            self.dlc_batch_worker.wait()
            del self.dlc_batch_worker
        self.table_manager.refresh_games(self.games)
        self._save_scan_cache()
        self.status_manager.show_message("Batch DLC import complete.")

    def _on_batch_dlc_import_cancel(self):
        """Handle batch DLC import cancellation."""
        self.dlc_batch_worker.cancel()
        self.status_manager.show_message("Batch DLC import cancelled.")

    def dragEnterEvent(self, event):
        """Handle drag enter event for DLC files"""
        # Only accept files or folders in Xbox 360 or XBLA mode
        if self.current_platform not in ("xbox360", "xbla"):
            event.ignore()
            return
        if event.mimeData().hasUrls():
            urls = event.mimeData().urls()
            if any(
                url.toLocalFile()
                and (
                    os.path.isfile(url.toLocalFile())
                    or os.path.isdir(url.toLocalFile())
                )
                for url in urls
            ):
                event.acceptProposedAction()
            else:
                event.ignore()
        else:
            event.ignore()

    def dropEvent(self, event):
        if self.current_platform not in ("xbox360", "xbla"):
            event.ignore()
            return
        if event.mimeData().hasUrls():

            def collect_files(path):
                files = []
                if os.path.isfile(path):
                    files.append(path)
                elif os.path.isdir(path):
                    for root, _, filenames in os.walk(path):
                        for fname in filenames:
                            files.append(os.path.join(root, fname))
                return files

            all_files = []
            for url in event.mimeData().urls():
                local_path = url.toLocalFile()
                if not local_path:
                    continue
                all_files.extend(collect_files(local_path))

            dlc_files = [
                f
                for f in all_files
                if os.path.isfile(f)
                and len(os.path.basename(f)) == 42
                and all(c in "0123456789ABCDEFabcdef" for c in os.path.basename(f))
                and not os.path.splitext(f)[1]
            ]
            if len(dlc_files) > 1:
                self.dlc_import_progress_dialog = BatchDLCImportProgressDialog(
                    len(dlc_files), parent=self
                )
                self.dlc_batch_worker = BatchDLCImportWorker(dlc_files, parent=self)
                self.dlc_batch_worker.progress.connect(
                    self._on_batch_dlc_import_progress
                )
                self.dlc_batch_worker.finished.connect(
                    self._on_batch_dlc_import_finished
                )
                self.dlc_import_progress_dialog.cancel_requested.connect(
                    self._on_batch_dlc_import_cancel
                )
                self.dlc_import_progress_dialog.show()
                self.dlc_batch_worker.start()
                event.acceptProposedAction()
            elif len(dlc_files) == 1:
                file_path = dlc_files[0]
                result = self.dlc_utils.parse_file(file_path)
                if result:
                    display_name = result.get("display_name")
                    description = result.get("description")
                    title_id = result.get("title_id")
                    game_name = self.game_manager.get_game_name(title_id)
                    if not game_name:
                        QMessageBox.warning(
                            self,
                            "DLC Game Not Found",
                            f"Cannot find game for Title ID: {title_id}\n"
                            "Please ensure the game is in your library before adding DLC.",
                        )
                        event.ignore()
                        return
                    target_dir = os.path.join(
                        self.directory_manager.dlc_directory, title_id
                    )
                    os.makedirs(target_dir, exist_ok=True)
                    target_path = os.path.join(target_dir, os.path.basename(file_path))
                    if not os.path.exists(target_path):
                        try:
                            with (
                                open(file_path, "rb") as src,
                                open(target_path, "wb") as dst,
                            ):
                                dst.write(src.read())
                        except Exception as e:
                            QMessageBox.warning(
                                self, "DLC Save Error", f"Failed to save DLC: {e}"
                            )
                    dlc_size = os.path.getsize(file_path)
                    dlc_file = os.path.basename(file_path)
                    result2 = self.dlc_utils.add_dlc_to_index(
                        title_id=title_id,
                        display_name=display_name,
                        description=description,
                        game_name=game_name,
                        size=dlc_size,
                        file=dlc_file,
                    )
                    if result2:
                        self.game_manager.increment_dlc_count(title_id)
                        self._save_scan_cache()
                        if self.table_manager:
                            self.table_manager.refresh_games(self.games)
                    dialog = DLCInfoDialog(
                        title_id=title_id or "",
                        display_name=display_name or "",
                        description=description or "",
                        game_name=game_name or "",
                        parent=self,
                    )
                    dialog.display_name.setReadOnly(True)
                    dialog.game_name.setReadOnly(True)
                    dialog.title_id.setReadOnly(True)
                    dialog.exec()
                    event.acceptProposedAction()
                else:
                    QMessageBox.warning(
                        self,
                        "DLC Parse Error",
                        f"Failed to parse DLC file: {os.path.basename(file_path)}",
                    )
                    event.ignore()
            else:
                event.ignore()
        else:
            event.ignore()
            self.table_manager.refresh_games(self.games)
        self._save_scan_cache()
        self.status_manager.show_message("Batch DLC import complete.")


class ClickableFirstColumnTableWidget(QTableWidget):
    """Custom table widget that makes the entire first column clickable for checkboxes"""

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            item = self.itemAt(event.position().toPoint())
            if item:
                row = item.row()
                column = item.column()

                # If clicked in the first column, toggle the checkbox
                if column == 0:
                    checkbox_item = self.item(row, 0)
                    if checkbox_item:
                        current_state = checkbox_item.checkState()
                        new_state = (
                            Qt.CheckState.Unchecked
                            if current_state == Qt.CheckState.Checked
                            else Qt.CheckState.Checked
                        )
                        checkbox_item.setCheckState(new_state)
                        return  # Don't call super() to prevent default selection behavior

        super().mousePressEvent(event)
