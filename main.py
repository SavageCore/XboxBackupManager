#!/usr/bin/env python3
"""
Xbox Backup Manager - Cross Platform GUI
Similar to Wii Backup Manager but for Xbox 360/OG Xbox games
"""

import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List
import subprocess
import platform
import urllib.request
import urllib.error

import darkdetect  # type: ignore
import qdarkstyle  # type: ignore
from qdarkstyle.dark.palette import DarkPalette  # type: ignore
from qdarkstyle.light.palette import LightPalette  # type: ignore
from PyQt6.QtCore import (
    QSettings,
    Qt,
    QThread,
    pyqtSignal,
    QFileSystemWatcher,
    QTimer,
    QSize,
)
from PyQt6.QtGui import QAction, QIcon, QActionGroup, QPixmap
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QApplication,
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
    QStyledItemDelegate,
)


@dataclass
class GameInfo:
    """Data class to hold game information"""

    title_id: str
    name: str
    size_bytes: int
    folder_path: str

    @property
    def size_formatted(self) -> str:
        """Return formatted file size"""
        size = float(self.size_bytes)  # Use a copy as float, don't modify the original
        for unit in ["B", "KB", "MB", "GB", "TB"]:
            if size < 1024.0:
                return f"{size:.1f} {unit}"
            size /= 1024.0
        return f"{size:.1f} PB"


class DirectoryScanner(QThread):
    """Thread to scan directory for Xbox games"""

    progress = pyqtSignal(int, int)  # current, total
    game_found = pyqtSignal(GameInfo)
    finished = pyqtSignal()
    error = pyqtSignal(str)

    def __init__(self, directory: str, title_database: Dict[str, str]):
        super().__init__()
        self.directory = directory
        self.title_database = title_database

    def run(self):
        try:
            path = Path(self.directory)
            if not path.exists():
                self.error.emit("Directory does not exist")
                return

            # Get all subdirectories (assumed to be Title IDs)
            # Skip Cache
            subdirs = [d for d in path.iterdir() if d.is_dir() and d.name != "Cache"]
            total_dirs = len(subdirs)

            for i, subdir in enumerate(subdirs):
                title_id = subdir.name.upper()

                # Calculate directory size
                size = self.calculate_directory_size(subdir)

                # Get game name from database or use title ID
                game_name = self.title_database.get(title_id, f"Unknown ({title_id})")
                # game_name = f"Unknown ({title_id})"

                game_info = GameInfo(
                    title_id=title_id,
                    name=game_name,
                    size_bytes=size,
                    folder_path=str(subdir),
                )

                self.game_found.emit(game_info)
                self.progress.emit(i + 1, total_dirs)

            self.finished.emit()

        except Exception as e:
            self.error.emit(str(e))

    def calculate_directory_size(self, directory: Path) -> int:
        """Calculate total size of directory in bytes"""
        total_size = 0
        try:
            for file_path in directory.rglob("*"):
                if file_path.is_file():
                    total_size += file_path.stat().st_size
        except (OSError, PermissionError):
            pass  # Skip files we can't access
        return total_size


class IconDownloader(QThread):
    """Thread to download game icons"""

    icon_downloaded = pyqtSignal(str, QPixmap)  # title_id, pixmap
    download_failed = pyqtSignal(str)  # title_id

    def __init__(self, title_ids: List[str]):
        super().__init__()
        self.title_ids = title_ids
        self.cache_dir = Path("cache/icons")
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def run(self):
        for title_id in self.title_ids:
            try:
                pixmap = self.get_or_download_icon(title_id)
                if pixmap:
                    self.icon_downloaded.emit(title_id, pixmap)
                else:
                    self.download_failed.emit(title_id)
            except Exception:
                self.download_failed.emit(title_id)

    def get_or_download_icon(self, title_id: str) -> QPixmap:
        """Get icon from cache or download it"""
        cache_file = self.cache_dir / f"{title_id}.png"

        # Check if cached version exists
        if cache_file.exists():
            pixmap = QPixmap(str(cache_file))
            if not pixmap.isNull():
                return pixmap

        # Download from Xbox Unity
        try:
            url = (
                f"https://xboxunity.net/Resources/Lib/Icon.php?tid={title_id}&custom=1"
            )
            urllib.request.urlretrieve(url, str(cache_file))

            # Load and return the downloaded image
            pixmap = QPixmap(str(cache_file))
            if not pixmap.isNull():
                return pixmap
        except (urllib.error.URLError, urllib.error.HTTPError, Exception):
            pass

        return QPixmap()  # Return empty pixmap on failure


class IconDelegate(QStyledItemDelegate):
    """Custom delegate to properly display and center icons"""

    def __init__(self, parent=None):
        super().__init__(parent)

    def paint(self, painter, option, index):
        """Custom paint method to center icons"""
        if index.column() == 0:  # Icon column
            # Draw background if selected
            from PyQt6.QtWidgets import QStyle
            from PyQt6.QtGui import QPen

            if option.state & QStyle.StateFlag.State_Selected:
                painter.fillRect(option.rect, option.palette.highlight())
            else:
                # Draw alternating row colors if enabled
                if index.row() % 2 == 1:
                    painter.fillRect(option.rect, option.palette.alternateBase())
                else:
                    painter.fillRect(option.rect, option.palette.base())

            # Get the pixmap from the item's icon
            icon = index.data(Qt.ItemDataRole.DecorationRole)
            if isinstance(icon, QIcon) and not icon.isNull():
                # Get 64x64 pixmap for better quality
                pixmap = icon.pixmap(64, 64)
                if not pixmap.isNull():
                    # Calculate centered position
                    rect = option.rect
                    pixmap_rect = pixmap.rect()

                    # Center the pixmap in the cell
                    x = rect.x() + (rect.width() - pixmap_rect.width()) // 2
                    y = rect.y() + (rect.height() - pixmap_rect.height()) // 2

                    # Draw the pixmap
                    painter.drawPixmap(x, y, pixmap)

            # Draw bottom border to match other columns
            pen = QPen(
                option.palette.color(
                    option.palette.ColorGroup.Active, option.palette.ColorRole.Mid
                )
            )
            pen.setWidth(1)
            painter.setPen(pen)
            painter.drawLine(
                option.rect.bottomLeft().x(),
                option.rect.bottomLeft().y(),
                option.rect.bottomRight().x(),
                option.rect.bottomRight().y(),
            )

            return

        # For non-icon columns, use default painting
        super().paint(painter, option, index)

    def sizeHint(self, option, index):
        """Return size hint for items"""
        if index.column() == 0:  # Icon column
            return QSize(80, 72)  # Match larger row height for icons
        return super().sizeHint(option, index)


class XboxBackupManager(QMainWindow):
    """Main application window"""

    def __init__(self):
        super().__init__()
        self.settings = QSettings("XboxBackupManager", "XboxBackupManager")
        self.title_database: Dict[str, str] = {}
        self.games: List[GameInfo] = []
        self.current_directory = ""
        self.dark_mode_override = (
            None  # None = auto, True = force dark, False = force light
        )
        self.current_platform = "xbox360"  # Default platform
        self.show_icons = False  # Show game icons

        # Platform directories
        self.platform_directories = {"xbox360": "", "xbla": ""}

        # Icon cache
        self.icon_cache: Dict[str, QPixmap] = {}

        # File system watcher for detecting changes
        self.file_watcher = QFileSystemWatcher()
        self.file_watcher.directoryChanged.connect(self.on_directory_changed)

        # Timer to debounce file system events
        self.scan_timer = QTimer()
        self.scan_timer.setSingleShot(True)
        self.scan_timer.timeout.connect(self.delayed_scan)
        self.scan_delay = 2000  # 2 seconds delay

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

        # Remove all margins and spacing from main layout
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # Top section - Directory selection
        top_layout = QHBoxLayout()
        top_layout.setContentsMargins(10, 10, 10, 10)  # Add margins only to top section
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

        # Create a widget to contain the top layout with margins
        top_widget = QWidget()
        top_widget.setLayout(top_layout)

        main_layout.addWidget(top_widget)

        # Games table - no margins, should be full width
        self.games_table = QTableWidget()
        self.games_table.setContentsMargins(0, 0, 0, 0)
        main_layout.addWidget(self.games_table)

        # Progress bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        self.progress_bar.setMaximumHeight(20)
        self.progress_bar.setContentsMargins(
            10, 0, 10, 10
        )  # Add side margins to progress bar
        main_layout.addWidget(self.progress_bar)

        # Status bar - use the built-in status bar for full width
        self.status_bar = self.statusBar()
        self.status_bar.showMessage("Ready - Load title database first")

    def create_menu_bar(self):
        """Create the application menu bar"""
        menubar = self.menuBar()

        # File menu
        file_menu = menubar.addMenu("&File")

        # Browse Directory action
        browse_action = QAction("&Browse Directory...", self)
        browse_action.setShortcut("Ctrl+O")
        browse_action.triggered.connect(self.browse_directory)
        file_menu.addAction(browse_action)

        file_menu.addSeparator()

        # Exit action
        exit_action = QAction("E&xit", self)
        exit_action.setShortcut("Ctrl+Q")
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)

        # Platform menu
        platform_menu = menubar.addMenu("&Platform")

        # Create action group for mutual exclusivity
        self.platform_action_group = QActionGroup(self)

        # Xbox 360 action
        self.xbox360_action = QAction("&Xbox 360", self)
        self.xbox360_action.setCheckable(True)
        self.xbox360_action.setChecked(True)
        self.xbox360_action.triggered.connect(lambda: self.switch_platform("xbox360"))
        self.platform_action_group.addAction(self.xbox360_action)
        platform_menu.addAction(self.xbox360_action)

        # XBLA action
        self.xbla_action = QAction("Xbox &Live Arcade", self)
        self.xbla_action.setCheckable(True)
        self.xbla_action.triggered.connect(lambda: self.switch_platform("xbla"))
        self.platform_action_group.addAction(self.xbla_action)
        platform_menu.addAction(self.xbla_action)

        # View menu
        view_menu = menubar.addMenu("&View")

        # Show Icons action
        self.show_icons_action = QAction("Show &Icons", self)
        self.show_icons_action.setCheckable(True)
        self.show_icons_action.setChecked(False)
        self.show_icons_action.triggered.connect(self.toggle_icons)
        view_menu.addAction(self.show_icons_action)

        view_menu.addSeparator()

        # Theme submenu
        theme_menu = view_menu.addMenu("&Theme")

        # Create theme action group for mutual exclusivity
        self.theme_action_group = QActionGroup(self)

        # Auto theme action
        self.auto_theme_action = QAction("&Auto", self)
        self.auto_theme_action.setCheckable(True)
        self.auto_theme_action.setChecked(True)
        self.auto_theme_action.triggered.connect(lambda: self.set_theme_override(None))
        self.theme_action_group.addAction(self.auto_theme_action)
        theme_menu.addAction(self.auto_theme_action)

        # Light theme action
        self.light_theme_action = QAction("&Light", self)
        self.light_theme_action.setCheckable(True)
        self.light_theme_action.triggered.connect(
            lambda: self.set_theme_override(False)
        )
        self.theme_action_group.addAction(self.light_theme_action)
        theme_menu.addAction(self.light_theme_action)

        # Dark theme action
        self.dark_theme_action = QAction("&Dark", self)
        self.dark_theme_action.setCheckable(True)
        self.dark_theme_action.triggered.connect(lambda: self.set_theme_override(True))
        self.theme_action_group.addAction(self.dark_theme_action)
        theme_menu.addAction(self.dark_theme_action)

        # Help menu
        help_menu = menubar.addMenu("&Help")

        # About action
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
        platform_names = {
            "xbox360": "Xbox 360",
            "xbla": "Xbox Live Arcade",
        }
        self.platform_label.setText(platform_names[platform])

        # Recreate table with appropriate columns for new platform
        self.setup_table()

        # Load directory for new platform
        if self.platform_directories[platform]:
            self.current_directory = self.platform_directories[platform]
            self.directory_label.setText(self.current_directory)
            self.scan_button.setEnabled(True)
            self.start_watching_directory()
            # Auto-scan when switching platforms
            self.scan_directory()
        else:
            self.current_directory = ""
            self.directory_label.setText("No directory selected")
            self.scan_button.setEnabled(False)
            # Clear the table
            self.games.clear()
            self.games_table.setRowCount(0)

        # Save platform selection
        self.settings.setValue("current_platform", platform)
        self.status_bar.showMessage(f"Switched to {platform_names[platform]}")

    def set_theme_override(self, override_value):
        """Set theme override and apply theme"""
        self.dark_mode_override = override_value
        self.apply_theme()
        self.settings.setValue("dark_mode_override", self.dark_mode_override)

    def show_about(self):
        """Show about dialog"""
        QMessageBox.about(
            self,
            "About Xbox 360 Backup Manager",
            "Xbox 360 Backup Manager v0.0.0\n\n"
            "A cross-platform GUI for managing Xbox 360 game backups.\n"
            "Similar to Wii Backup Manager but for Xbox 360/XBLA.\n\n"
            "Supports automatic scanning, file system watching, and game organization.",
        )

    def get_light_theme(self) -> str:
        """Return light theme stylesheet"""
        return qdarkstyle.load_stylesheet(palette=LightPalette)

    def get_dark_theme(self) -> str:
        """Return dark theme stylesheet"""
        return qdarkstyle.load_stylesheet(palette=DarkPalette)

    def should_use_dark_mode(self) -> bool:
        """Determine if dark mode should be used"""
        if self.dark_mode_override is not None:
            return self.dark_mode_override
        return darkdetect.isDark()

    def apply_theme(self):
        """Apply the current theme"""
        if self.should_use_dark_mode():
            stylesheet = self.get_dark_theme()
        else:
            stylesheet = self.get_light_theme()

        # Apply specific button styling that works with both themes
        button_styling = """
        QPushButton#browse_button, QPushButton#scan_button {
            padding: 8px 16px !important;
            font-size: 14px !important;
            min-height: 20px !important;
        }
        QProgressBar {
            border: none;
        }
        QProgressBar::chunk {
            border-radius: 0px !important;
        }
        """
        self.setStyleSheet(stylesheet + button_styling)

        # Update theme menu checkmarks
        self.update_theme_menu_state()

    def update_theme_menu_state(self):
        """Update theme menu state based on current override"""
        if self.dark_mode_override is None:
            self.auto_theme_action.setChecked(True)
        elif self.dark_mode_override:
            self.dark_theme_action.setChecked(True)
        else:
            self.light_theme_action.setChecked(True)

    def load_settings(self):
        """Load settings from persistent storage"""
        # Restore window geometry
        geometry = self.settings.value("geometry")
        if geometry:
            self.restoreGeometry(geometry)
        else:
            self.setGeometry(100, 100, 1000, 600)

        # Restore window state (maximized, etc.)
        window_state = self.settings.value("windowState")
        if window_state:
            self.restoreState(window_state)

        # Restore theme override preference
        dark_mode_setting = self.settings.value("dark_mode_override")
        if dark_mode_setting == "true":
            self.dark_mode_override = True
        elif dark_mode_setting == "false":
            self.dark_mode_override = False
        else:
            self.dark_mode_override = None

        # Restore show icons preference
        self.show_icons = self.settings.value("show_icons", False, type=bool)
        self.show_icons_action.setChecked(self.show_icons)

        # Restore current platform
        self.current_platform = self.settings.value("current_platform", "xbox360")

        # Update platform menu state
        platform_actions = {
            "xbox360": self.xbox360_action,
            "xbla": self.xbla_action,
        }
        if self.current_platform in platform_actions:
            platform_actions[self.current_platform].setChecked(True)

        # Restore platform directories
        for plat in ["xbox360", "xbla"]:
            directory = self.settings.value(f"{plat}_directory", "")
            if directory and os.path.exists(directory):
                self.platform_directories[plat] = directory

        # Set current directory based on current platform
        if self.platform_directories[self.current_platform]:
            self.current_directory = self.platform_directories[self.current_platform]
            self.directory_label.setText(self.current_directory)

        # Update platform label
        platform_names = {
            "xbox360": "Xbox 360",
            "xbla": "Xbox Live Arcade",
        }
        self.platform_label.setText(platform_names[self.current_platform])

        # NOW setup the table with the correct platform
        self.setup_table()

        # Load cached icons after setting up the table
        self.load_cached_icons()

        # Restore table column widths (adjusted for platform-specific column count and icons)
        header = self.games_table.horizontalHeader()
        show_dlcs = self.current_platform in ["xbla"]

        if self.show_icons:
            column_count = 6 if show_dlcs else 5
        else:
            column_count = 5 if show_dlcs else 4

        for i in range(column_count):
            width = self.settings.value(
                f"{self.current_platform}_icons_{self.show_icons}_column_{i}_width"
            )
            if width:
                header.resizeSection(i, int(width))

        # Restore sort column and order
        sort_column = self.settings.value("sort_column", 2 if self.show_icons else 1)
        sort_order = self.settings.value(
            "sort_order", Qt.SortOrder.AscendingOrder.value
        )
        if sort_column is not None:
            self.games_table.sortItems(int(sort_column), Qt.SortOrder(int(sort_order)))

        # Apply theme after loading preferences
        self.apply_theme()

    def load_cached_icons(self):
        """Load any cached icons from disk"""
        if not self.show_icons:
            return

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
        # Save window geometry and state
        self.settings.setValue("geometry", self.saveGeometry())
        self.settings.setValue("windowState", self.saveState())

        # Save current platform
        self.settings.setValue("current_platform", self.current_platform)

        # Save show icons preference
        self.settings.setValue("show_icons", self.show_icons)

        # Save current directory for current platform
        if self.current_directory:
            self.platform_directories[self.current_platform] = self.current_directory

        # Save all platform directories
        for plat, directory in self.platform_directories.items():
            if directory:
                self.settings.setValue(f"{plat}_directory", directory)

        # Save theme override preference
        if self.dark_mode_override is None:
            self.settings.setValue("dark_mode_override", "auto")
        else:
            self.settings.setValue(
                "dark_mode_override", str(self.dark_mode_override).lower()
            )

        # Save table column widths (platform-specific and icon-mode specific)
        header = self.games_table.horizontalHeader()
        show_dlcs = self.current_platform in ["xbla"]

        if self.show_icons:
            column_count = 6 if show_dlcs else 5
        else:
            column_count = 5 if show_dlcs else 4

        for i in range(column_count):
            self.settings.setValue(
                f"{self.current_platform}_icons_{self.show_icons}_column_{i}_width",
                header.sectionSize(i),
            )

        # Save sort column and order
        sort_column = self.games_table.horizontalHeader().sortIndicatorSection()
        sort_order = self.games_table.horizontalHeader().sortIndicatorOrder()
        self.settings.setValue("sort_column", sort_column)
        self.settings.setValue("sort_order", sort_order.value)

    def browse_directory(self):
        """Open directory selection dialog"""
        # Use saved directory for current platform as starting point
        start_dir = (
            self.current_directory
            if self.current_directory
            else os.path.expanduser("~")
        )

        platform_names = {
            "xbox360": "Xbox 360",
            "xbla": "Xbox Live Arcade",
        }

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
        """Load the Xbox 360 title database"""
        self.status_bar.showMessage("Loading title database...")

        # Load from local file, db/Xbox360TitleIDs.json
        try:
            with open("db/Xbox360TitleIDs.json", "r", encoding="utf-8") as f:
                database_list = json.load(f)
                # Convert list format to dict format
                database = {item["TitleID"]: item["Title"] for item in database_list}
                self.on_database_loaded(database)
        except Exception as e:
            self.on_database_error(str(e))

    def on_database_loaded(self, database: Dict[str, str]):
        """Handle successful database loading"""
        self.title_database = database
        count = len(database)
        self.status_bar.showMessage(
            f"Title database loaded - {count:,} titles available"
        )

        # Enable UI elements
        self.browse_button.setEnabled(True)
        if self.current_directory:
            self.scan_button.setEnabled(True)
            # Start file system watching
            self.start_watching_directory()
            # Auto-scan on startup if directory is set
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
            self.status_bar.showMessage(
                f"Watching directory for changes: {self.current_directory}"
            )

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
        self.scanner = DirectoryScanner(self.current_directory, self.title_database)
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

        # Set row height based on icon display
        if self.show_icons:
            self.games_table.setRowHeight(row, 72)
        else:
            self.games_table.setRowHeight(row, 32)

        # Determine if we should show DLCs column based on platform
        show_dlcs = self.current_platform in ["xbla"]

        # Create items with UserRole data to maintain sorting integrity
        col_index = 0

        # Add icon column if showing icons
        if self.show_icons:
            icon_item = QTableWidgetItem()
            icon_item.setFlags(
                icon_item.flags() & ~Qt.ItemFlag.ItemIsEditable
            )  # Make non-editable

            # Add icon if we have it cached
            if game_info.title_id in self.icon_cache:
                pixmap = self.icon_cache[game_info.title_id]
                # Create a QIcon from the pixmap at full size (64x64)
                icon = QIcon(pixmap)
                icon_item.setIcon(icon)

            self.games_table.setItem(row, col_index, icon_item)
            col_index += 1

        # Create all items with proper data
        title_id_item = QTableWidgetItem(game_info.title_id)
        title_id_item.setData(Qt.ItemDataRole.UserRole, game_info.title_id)

        name_item = QTableWidgetItem(game_info.name)
        name_item.setData(Qt.ItemDataRole.UserRole, game_info.name)

        size_item = QTableWidgetItem(game_info.size_formatted)
        size_item.setData(Qt.ItemDataRole.UserRole, game_info.size_bytes)

        path_item = QTableWidgetItem(game_info.folder_path)
        path_item.setData(Qt.ItemDataRole.UserRole, game_info.folder_path)

        # Add Title ID to current column
        self.games_table.setItem(row, col_index, title_id_item)
        col_index += 1

        # Add Game Name to current column
        self.games_table.setItem(row, col_index, name_item)
        col_index += 1

        # Add Size to current column
        self.games_table.setItem(row, col_index, size_item)
        col_index += 1

        # Add DLCs column if needed for this platform
        if show_dlcs:
            # Calculate DLCs only for XBLA
            dlc_folder = Path(game_info.folder_path) / "00000002"
            if dlc_folder.exists() and dlc_folder.is_dir():
                dlcs_count = len([f for f in dlc_folder.iterdir() if f.is_file()])
            else:
                dlcs_count = 0

            dlc_item = QTableWidgetItem(str(dlcs_count))
            dlc_item.setData(Qt.ItemDataRole.UserRole, dlcs_count)
            self.games_table.setItem(row, col_index, dlc_item)
            col_index += 1

        # Add Folder Path to current column (always last)
        self.games_table.setItem(row, col_index, path_item)

        # Update status
        self.status_bar.showMessage(f"Found {len(self.games)} games...")

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

        # Apply the previous sort order, or default to Game Name if this is the first scan
        if hasattr(self, "current_sort_column") and hasattr(self, "current_sort_order"):
            self.games_table.sortItems(
                self.current_sort_column, self.current_sort_order
            )
        else:
            # Default sort for first scan
            self.games_table.sortItems(1, Qt.SortOrder.AscendingOrder)

        self.status_bar.showMessage(
            f"Scan complete - {game_count:,} games found ({size_formatted:.1f} {unit}) - Watching for changes"
        )

        # Download icons if showing icons
        if self.show_icons and game_count > 0:
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

        # Update the table row for this title ID if showing icons
        if self.show_icons:
            title_id_column = 1  # Title ID is in column 1 when icons are shown

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
        # Create a placeholder icon or just leave empty
        pass

    def on_icon_download_finished(self):
        """Handle completion of icon download batch"""
        self.status_bar.showMessage("Icon downloads completed")

    def setup_table(self):
        """Setup the games table widget"""
        # Determine if we should show DLCs column based on platform
        show_dlcs = self.current_platform in ["xbla"]

        if self.show_icons:
            if show_dlcs:
                self.games_table.setColumnCount(6)
                headers = [
                    "Icon",
                    "Title ID",
                    "Game Name",
                    "Size",
                    "DLCs",
                    "Folder Path",
                ]
            else:
                self.games_table.setColumnCount(5)
                headers = ["Icon", "Title ID", "Game Name", "Size", "Folder Path"]
        else:
            if show_dlcs:
                self.games_table.setColumnCount(5)
                headers = ["Title ID", "Game Name", "Size", "DLCs", "Folder Path"]
            else:
                self.games_table.setColumnCount(4)
                headers = ["Title ID", "Game Name", "Size", "Folder Path"]

        self.games_table.setHorizontalHeaderLabels(headers)

        # Set up custom icon delegate for proper icon rendering
        if self.show_icons:
            icon_delegate = IconDelegate()
            self.games_table.setItemDelegateForColumn(0, icon_delegate)

        # Set column widths
        header = self.games_table.horizontalHeader()

        if self.show_icons:
            # Icon column - fixed width
            header.setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
            header.resizeSection(0, 80)  # Fixed width for icons

            # Other columns
            header.setSectionResizeMode(
                1, QHeaderView.ResizeMode.Interactive
            )  # Title ID
            header.setSectionResizeMode(
                2, QHeaderView.ResizeMode.Interactive
            )  # Game Name
            header.setSectionResizeMode(3, QHeaderView.ResizeMode.Interactive)  # Size

            if show_dlcs:
                header.setSectionResizeMode(
                    4, QHeaderView.ResizeMode.Interactive
                )  # DLCs
                header.setSectionResizeMode(
                    5, QHeaderView.ResizeMode.Stretch
                )  # Folder Path
            else:
                header.setSectionResizeMode(
                    4, QHeaderView.ResizeMode.Stretch
                )  # Folder Path
        else:
            # No icons - original layout
            header.setSectionResizeMode(
                0, QHeaderView.ResizeMode.Interactive
            )  # Title ID
            header.setSectionResizeMode(
                1, QHeaderView.ResizeMode.Interactive
            )  # Game Name
            header.setSectionResizeMode(2, QHeaderView.ResizeMode.Interactive)  # Size

            if show_dlcs:
                header.setSectionResizeMode(
                    3, QHeaderView.ResizeMode.Interactive
                )  # DLCs
                header.setSectionResizeMode(
                    4, QHeaderView.ResizeMode.Stretch
                )  # Folder Path
            else:
                header.setSectionResizeMode(
                    3, QHeaderView.ResizeMode.Stretch
                )  # Folder Path

        # Set minimum column widths
        header.setMinimumSectionSize(80)

        # Set initial column widths
        if self.show_icons:
            header.resizeSection(1, 100)  # Title ID
            header.resizeSection(2, 300)  # Game Name
            header.resizeSection(3, 100)  # Size
            if show_dlcs:
                header.resizeSection(4, 60)  # DLCs
        else:
            header.resizeSection(0, 100)  # Title ID
            header.resizeSection(1, 300)  # Game Name
            header.resizeSection(2, 100)  # Size
            if show_dlcs:
                header.resizeSection(3, 60)  # DLCs

        # Table settings
        self.games_table.setAlternatingRowColors(True)
        self.games_table.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows
        )
        self.games_table.setSortingEnabled(True)

        # Remove outer border but keep row separators
        self.games_table.setFrameStyle(0)  # Remove outer frame/border
        self.games_table.setShowGrid(False)  # Remove grid lines

        # Configure row headers - completely hide them to remove left padding
        vertical_header = self.games_table.verticalHeader()
        vertical_header.setVisible(False)  # Hide completely to remove left padding
        vertical_header.setDefaultSectionSize(0)  # Set to 0 width

        # Remove any viewport margins
        self.games_table.setContentsMargins(0, 0, 0, 0)

        # Enable horizontal lines between rows only and fix header styling
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

        # Use larger row height for icons, smaller for text-only
        if self.show_icons:
            self.games_table.verticalHeader().setDefaultSectionSize(72)
        else:
            self.games_table.verticalHeader().setDefaultSectionSize(32)

        # Enable row selection via clicking anywhere on the row
        self.games_table.setSelectionMode(
            QAbstractItemView.SelectionMode.MultiSelection
        )
        self.games_table.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows
        )

        # Ensure header is visible with proper styling and stretches to full width
        header.setVisible(True)
        header.setHighlightSections(False)
        header.setStretchLastSection(True)  # This ensures the table fills full width
        header.setContentsMargins(0, 0, 0, 0)  # Remove header margins

        # Enable context menu and connect to custom handler
        self.games_table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.games_table.customContextMenuRequested.connect(self.show_context_menu)

        # Set default sort to Game Name (column 1 or 2 depending on icons)
        name_column = 2 if self.show_icons else 1
        self.games_table.sortItems(name_column, Qt.SortOrder.AscendingOrder)

    def toggle_select_all(self):
        """Toggle select all/deselect all for checkboxes - placeholder for future checkbox functionality"""
        # This will be implemented when checkboxes are added
        pass

    def toggle_icons(self):
        """Toggle icon display in the table"""
        self.show_icons = self.show_icons_action.isChecked()
        self.settings.setValue("show_icons", self.show_icons)

        # Refresh the table to show/hide icons
        self.setup_table()

        # Re-add all games to update the display
        if self.games:
            # Store current games list
            current_games = self.games.copy()

            # Clear table and games list
            self.games.clear()
            self.games_table.setRowCount(0)

            # Disable sorting during bulk insertion
            self.games_table.setSortingEnabled(False)

            # Re-add all games
            for game in current_games:
                self.add_game(game)

            # Re-enable sorting
            self.games_table.setSortingEnabled(True)

            # Download icons if showing icons and not already cached
            if self.show_icons:
                self.download_missing_icons()

    def show_context_menu(self, position):
        """Show context menu when right-clicking on table"""
        item = self.games_table.itemAt(position)
        if item is None:
            return

        row = item.row()

        # Determine folder path column based on platform and icon display
        show_dlcs = self.current_platform in ["xbla"]
        col_offset = 1 if self.show_icons else 0

        if show_dlcs:
            folder_path_column = 4 + col_offset
        else:
            folder_path_column = 3 + col_offset

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
            lambda: self.open_folder_in_explorer(folder_path)
        )

        # Show the menu at the cursor position
        menu.exec(self.games_table.mapToGlobal(position))

    def open_folder_in_explorer(self, folder_path: str):
        """Open the folder in the system file explorer"""
        if not os.path.exists(folder_path):
            QMessageBox.warning(
                self, "Folder Not Found", f"The folder does not exist:\n{folder_path}"
            )
            return

        try:
            system_name = platform.system()
            if system_name == "Windows":
                # Windows Explorer
                subprocess.run(["explorer", folder_path])
            elif system_name == "Darwin":  # macOS
                # Finder
                subprocess.run(["open", folder_path])
            elif system_name == "Linux":
                # Try common Linux file managers
                file_managers = ["xdg-open", "nautilus", "dolphin", "thunar", "pcmanfm"]
                opened = False
                for manager in file_managers:
                    try:
                        subprocess.run(
                            [manager, folder_path], capture_output=True, timeout=5
                        )
                        opened = True
                        break
                    except (subprocess.TimeoutExpired, FileNotFoundError):
                        continue
                    except subprocess.CalledProcessError:
                        opened = True
                        break

                if not opened:
                    QMessageBox.warning(
                        self,
                        "File Manager Not Found",
                        "Could not find a suitable file manager to open the folder.",
                    )
            else:
                QMessageBox.warning(
                    self,
                    "Unsupported Platform",
                    f"Opening folders is not supported on {system_name}",
                )
        except Exception as e:
            if "exit status" not in str(e).lower():
                QMessageBox.warning(
                    self, "Unexpected Error", f"An unexpected error occurred:\n{e}"
                )

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


def main():
    """Main application entry point"""
    app = QApplication(sys.argv)
    app.setApplicationName("Xbox Backup Manager")
    app.setApplicationVersion("1.0")

    # Set application icon if available
    try:
        app.setWindowIcon(QIcon("icon.ico"))
    except Exception:
        pass

    window = XboxBackupManager()
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
