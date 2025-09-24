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
        # Group log lines by game name
        log_by_game = {}
        for file_path in self.dlc_files:
            if not os.path.isfile(file_path):
                continue
            base = os.path.basename(file_path)
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
                        log_by_game.setdefault("Unknown Game", []).append(
                            f"Game not found for Title ID {title_id} (file: {base})"
                        )
                        continue
                    target_dir = os.path.join(
                        self.parent.directory_manager.dlc_directory, title_id
                    )
                    os.makedirs(target_dir, exist_ok=True)
                    target_path = os.path.join(target_dir, base)
                    file_existed = os.path.exists(target_path)
                    if not file_existed:
                        try:
                            with open(file_path, "rb") as src, open(
                                target_path, "wb"
                            ) as dst:
                                dst.write(src.read())
                        except Exception as e:
                            log_by_game.setdefault(game_name, []).append(
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
                        if file_existed:
                            log_by_game.setdefault(game_name, []).append(
                                f"DLC for {game_name} (file: {base}) already exists in index. Skipped."
                            )
                        else:
                            log_by_game.setdefault(game_name, []).append(
                                f"Added DLC for {game_name} (file: {base})"
                            )
                    else:
                        if file_existed:
                            log_by_game.setdefault(game_name, []).append(
                                f"DLC for {game_name} (file: {base}) already exists in index. Skipped."
                            )
                        else:
                            log_by_game.setdefault(game_name, []).append(
                                f"Could not add DLC for {game_name} (file: {base}) - index update failed"
                            )
                else:
                    log_by_game.setdefault("Unknown Game", []).append(
                        f"Failed to parse DLC file: {base}"
                    )
        # Consolidate 'Game not found' entries and move to end
        unknown_game_lines = (
            log_by_game.pop("Unknown Game", []) if "Unknown Game" in log_by_game else []
        )
        consolidated_not_found = []
        title_ids = set()
        for line in unknown_game_lines:
            if line.startswith("Game not found for Title ID"):
                # Extract title ID
                parts = line.split()
                try:
                    idx = parts.index("ID") + 1
                    title_id = parts[idx]
                    title_ids.add(title_id)
                except Exception:
                    pass
            else:
                consolidated_not_found.append(line)
        if title_ids:
            consolidated_not_found.insert(
                0,
                f"DLCs were not imported for the following Title IDs: {', '.join(sorted(title_ids))}",
            )
            consolidated_not_found.insert(
                1,
                "As these games are not in your library, please add them first and then re-run the DLC import.",
            )
        log_path = os.path.join(os.getcwd(), "batch_dlc_import_log.txt")
        with open(log_path, "w", encoding="utf-8") as logf:
            logf.write(
                f"\nBatch DLC Import {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
            )
            # Sort games alphabetically for log output
            for game in sorted(log_by_game.keys()):
                for line in log_by_game[game]:
                    logf.write(line + "\n")
                logf.write("\n")  # Carriage return between games
            # Write consolidated unknown game lines last
            if consolidated_not_found:
                for line in consolidated_not_found:
                    logf.write(line + "\n")
                logf.write("\n")
        self.finished.emit()
