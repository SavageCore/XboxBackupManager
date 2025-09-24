from PyQt6.QtCore import QThread, pyqtSignal
import os
import datetime


class BatchDLCImportWorker(QThread):
    progress = pyqtSignal(str)
    finished = pyqtSignal()

    def __init__(self, dlc_files, parent=None):
        super().__init__(parent)
        self.dlc_files = dlc_files
        self.parent = parent
        self.log_lines = []

    def run(self):
        for file_path in self.dlc_files:
            if not os.path.isfile(file_path):
                continue
            base = os.path.basename(file_path)
            # Only accept files that look like DLC (32 hex chars, no extension)
            if (
                len(base) == 42
                and all(c in "0123456789ABCDEFabcdef" for c in base)
                and not os.path.splitext(base)[1]
            ):
                result = self.parent.dlc_utils.parse_file(file_path)
                if result:
                    display_name = result.get("display_name")
                    description = result.get("description")
                    title_id = result.get("title_id")
                    game_name = self.parent.game_manager.get_game_name(title_id)
                    if not game_name:
                        self.log_lines.append(
                            f"Game not found for Title ID {title_id} (file: {base})"
                        )
                        continue
                    # Save DLC file
                    target_dir = os.path.join(
                        self.parent.directory_manager.dlc_directory, title_id
                    )
                    os.makedirs(target_dir, exist_ok=True)
                    target_path = os.path.join(target_dir, base)
                    if not os.path.exists(target_path):
                        try:
                            with open(file_path, "rb") as src, open(
                                target_path, "wb"
                            ) as dst:
                                dst.write(src.read())
                        except Exception as e:
                            self.log_lines.append(
                                f"Could not add DLC for {game_name} (file: {base}): {e}"
                            )
                            continue
                    dlc_size = os.path.getsize(file_path)
                    dlc_file = os.path.basename(file_path)
                    result2 = self.parent.dlc_utils.add_dlc_to_index(
                        title_id=title_id,
                        display_name=display_name,
                        description=description,
                        game_name=game_name,
                        size=dlc_size,
                        file=dlc_file,
                    )
                    if result2:
                        self.parent.game_manager.increment_dlc_count(title_id)
                        self.parent._save_scan_cache()
                        self.log_lines.append(
                            f"Added DLC for {game_name} (file: {base})"
                        )
                    else:
                        self.log_lines.append(
                            f"Could not add DLC for {game_name} (file: {base}) - index update failed"
                        )
                else:
                    self.log_lines.append(f"Failed to parse DLC file: {base}")
        # Save log
        log_path = os.path.join(os.getcwd(), "batch_dlc_import_log.txt")
        with open(log_path, "a", encoding="utf-8") as logf:
            logf.write(
                f"\nBatch DLC Import {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
            )
            for line in self.log_lines:
                logf.write(line + "\n")
        self.finished.emit()
