import json
from typing import Dict

from PyQt6.QtCore import QObject, pyqtSignal


class TitleDatabaseLoader(QObject):
    """Handles loading and managing the Xbox title database"""

    database_loaded = pyqtSignal(dict)
    database_error = pyqtSignal(str)

    def __init__(self):
        super().__init__()
        self.title_database: Dict[str, str] = {}

    def load_database(self, file_path: str = "title_ids.json"):
        """Load the Xbox title database from file"""
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                database_list = json.load(f)
                # Convert list format to dict format
                database = {item["TitleID"]: item["Title"] for item in database_list}
                self.title_database = database
                self.database_loaded.emit(database)
        except Exception as e:
            self.database_error.emit(str(e))

    def get_game_name(self, title_id: str) -> str:
        """Get game name from database or return unknown format"""
        return self.title_database.get(title_id, f"Unknown ({title_id})")
