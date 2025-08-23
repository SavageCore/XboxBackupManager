import os
import tempfile
import zipfile
from pathlib import Path
from typing import Optional

from PyQt6.QtCore import QThread, pyqtSignal


class ZipExtractorWorker(QThread):
    """Worker thread for extracting ZIP files with progress reporting"""

    # Signals
    progress = pyqtSignal(int)  # Progress percentage (0-100)
    extraction_complete = pyqtSignal(str)  # Extracted file path
    extraction_error = pyqtSignal(str)  # Error message
    file_extracted = pyqtSignal(str)  # Individual file extracted

    def __init__(self, zip_path: str, extract_to: Optional[str] = None):
        super().__init__()
        self.zip_path = zip_path
        self.extract_to = extract_to or str(
            Path(tempfile.gettempdir()) / "xbbm_zip_extract"
        )
        print(f"ZIP extraction will be done to: {self.extract_to}")
        self.should_stop = False

    def run(self):
        """Extract the ZIP file with progress reporting"""
        try:
            # Ensure extraction directory exists
            os.makedirs(self.extract_to, exist_ok=True)

            with zipfile.ZipFile(self.zip_path, "r") as zip_ref:
                file_list = zip_ref.infolist()
                total_files = len(file_list)

                if total_files == 0:
                    self.extraction_error.emit("ZIP file is empty")
                    return

                extracted_files = []

                for i, file_info in enumerate(file_list):
                    if self.should_stop:
                        break

                    try:
                        # Extract individual file
                        zip_ref.extract(file_info, self.extract_to)
                        extracted_path = os.path.join(
                            self.extract_to, file_info.filename
                        )
                        extracted_files.append(extracted_path)

                        # Emit signals
                        self.file_extracted.emit(file_info.filename)

                        # Calculate and emit progress
                        progress = int(((i + 1) / total_files) * 100)
                        self.progress.emit(progress)

                    except Exception as e:
                        self.extraction_error.emit(
                            f"Failed to extract {file_info.filename}: {str(e)}"
                        )
                        return

                if not self.should_stop:
                    # Look for ISO files in extracted content
                    iso_files = []
                    for root, dirs, files in os.walk(self.extract_to):
                        for file in files:
                            if file.lower().endswith(".iso"):
                                iso_files.append(os.path.join(root, file))

                    if iso_files:
                        # Return the first ISO file found
                        self.extraction_complete.emit(iso_files[0])
                    else:
                        # No ISO found, return the extraction directory
                        self.extraction_complete.emit(self.extract_to)

        except zipfile.BadZipFile:
            self.extraction_error.emit("Invalid or corrupted ZIP file")
        except PermissionError:
            self.extraction_error.emit(
                "Permission denied - cannot extract to target directory"
            )
        except Exception as e:
            self.extraction_error.emit(f"Extraction failed: {str(e)}")

    def stop(self):
        """Stop the extraction process"""
        self.should_stop = True
