#!/usr/bin/env python3
"""
File Processing Progress Dialog - Unified dialog for ISO extraction and GOD creation
"""

import errno
import gc
import os
import shutil
import tempfile
import threading
import time
import zipfile

from PyQt6.QtCore import QProcess, Qt, QThread, QTimer, pyqtSignal
from PyQt6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
)

from utils.system_utils import SystemUtils


def _is_file_in_use(filepath):
    """Check if a file is currently in use by trying to rename it"""
    if not os.path.exists(filepath):
        return False

    try:
        # Try to rename the file to itself - this will fail if it's in use
        os.rename(filepath, filepath)
        return False
    except OSError as e:
        # Error codes that indicate the file is in use
        if e.errno in (errno.EACCES, errno.EBUSY):
            return True
        # On Windows, errno might be different
        if hasattr(e, "winerror") and e.winerror == 32:  # ERROR_SHARING_VIOLATION
            return True
        return False


def _wait_for_file_release(filepath, max_wait_seconds=30, check_interval=0.5):
    """Wait for a file to be released, checking periodically"""
    if not os.path.exists(filepath):
        return True

    waited = 0
    while waited < max_wait_seconds:
        if not _is_file_in_use(filepath):
            return True
        time.sleep(check_interval)
        waited += check_interval

    return False  # Timeout reached


def _wait_for_directory_release(directory, max_wait_seconds=30, check_interval=0.5):
    """Wait for all files in a directory to be released"""
    if not os.path.exists(directory):
        return True

    waited = 0
    while waited < max_wait_seconds:
        files_in_use = []

        try:
            for root, dirs, files in os.walk(directory):
                for file in files:
                    filepath = os.path.join(root, file)
                    if _is_file_in_use(filepath):
                        files_in_use.append(filepath)

            if not files_in_use:
                return True

        except OSError:
            # Directory might be in use itself
            pass

        time.sleep(check_interval)
        waited += check_interval

    return False  # Timeout reached


class CleanupWorker(QThread):
    """Background thread for cleaning up temporary files without blocking UI"""

    cleanup_finished = pyqtSignal(bool)  # Success/failure result

    def __init__(self, temp_dir, temp_files, output_path=None, is_cancelled=False):
        super().__init__()
        self.temp_dir = temp_dir
        self.temp_files = (
            temp_files.copy()
        )  # Make a copy to avoid modification during cleanup
        self.output_path = output_path
        self.is_cancelled = is_cancelled

    def run(self):
        """Run cleanup in background thread"""
        try:
            # Move garbage collection to background thread too
            gc.collect()

            # If processing was cancelled, remove the partially processed directory
            if (
                self.is_cancelled
                and self.output_path
                and os.path.exists(self.output_path)
            ):
                try:
                    shutil.rmtree(self.output_path, ignore_errors=True)
                except Exception:
                    pass  # Silent cleanup

            # Always clean up temporary directory from ZIP extraction (contains temp ISO)
            if self.temp_dir and os.path.exists(self.temp_dir):
                # First, wait for any files in the directory to be released
                if _wait_for_directory_release(self.temp_dir, max_wait_seconds=30):
                    try:
                        shutil.rmtree(self.temp_dir)
                    except Exception:
                        pass  # Silent cleanup
                else:
                    # Try forced removal with ignore_errors as fallback
                    try:
                        shutil.rmtree(self.temp_dir, ignore_errors=True)
                    except Exception:
                        pass  # Silent cleanup

            # Clean up any other tracked temporary files
            for temp_file in self.temp_files:
                try:
                    if os.path.isfile(temp_file) and os.path.exists(temp_file):
                        # Wait for individual file to be released
                        if _wait_for_file_release(temp_file, max_wait_seconds=10):
                            os.remove(temp_file)
                    elif os.path.isdir(temp_file) and os.path.exists(temp_file):
                        if _wait_for_directory_release(temp_file, max_wait_seconds=10):
                            shutil.rmtree(temp_file)
                        else:
                            shutil.rmtree(temp_file, ignore_errors=True)
                except Exception:
                    pass  # Silent cleanup

            self.cleanup_finished.emit(True)

        except Exception:
            self.cleanup_finished.emit(False)


class ClickableLabel(QLabel):
    """A clickable label that opens directories in the file explorer"""

    def __init__(self, text: str, directory_path: str = ""):
        super().__init__(text)
        self.directory_path = directory_path
        self.setStyleSheet(
            """
            QLabel {
                color: #0066cc;
                text-decoration: underline;
            }
            QLabel:hover {
                color: #004499;
            }
        """
        )
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip(f"Click to open: {directory_path}")

    def mousePressEvent(self, event):
        """Handle mouse click to open directory"""
        if event.button() == Qt.MouseButton.LeftButton and self.directory_path:
            SystemUtils.open_directory(self.directory_path)
        super().mousePressEvent(event)

    def update_path(self, new_path: str):
        """Update the directory path and tooltip"""
        self.directory_path = new_path
        self.setToolTip(f"Click to open: {new_path}")


class FileProcessingDialog(QDialog):
    """Dialog for showing file processing progress with cancel option"""

    processing_complete = pyqtSignal(str)  # output_path
    processing_error = pyqtSignal(str)  # error_message
    zip_progress_message = pyqtSignal(str)  # progress message from ZIP extraction

    def __init__(
        self,
        parent=None,
        operation_type: str = "extract",
        input_path: str = "",
        output_path: str = "",
    ):
        super().__init__(parent)
        self.operation_type = operation_type  # "extract" or "create_god"
        self.original_path = input_path  # Original file (might be ZIP or ISO)
        self.input_path = (
            input_path  # Current input path (will change if extracting from ZIP)
        )
        self.output_path = output_path
        self.processing_process = None
        self.zip_extraction_process = None
        self.is_cancelled = False
        self.temp_files = []  # Track temporary files for cleanup
        self.temp_iso_path = None  # Track temp ISO from ZIP extraction
        self.is_batch_mode = False  # Track if we're in batch mode
        self.zip_extraction_thread = None  # Track ZIP extraction thread
        self.cancel_zip_extraction = False  # Flag to cancel ZIP extraction
        self.cleanup_worker = None  # Track cleanup worker thread

        self.dest_label = None

        # Set window title based on operation
        if operation_type == "extract":
            self.setWindowTitle("Extracting Files")
        elif operation_type == "create_god":
            self.setWindowTitle("Creating GOD File")
        else:
            self.setWindowTitle("Processing Files")

        self.setModal(True)
        self.setFixedSize(500, 300)

        # Connect the ZIP progress signal to update UI
        self.zip_progress_message.connect(self._on_zip_progress_message)

        self._setup_ui()

    def _setup_ui(self):
        """Set up the dialog UI"""
        layout = QVBoxLayout(self)

        # File info label
        if self.operation_type == "extract":
            self.file_label = QLabel(
                f"Extracting: {os.path.basename(self.original_path)}"
            )
        elif self.operation_type == "create_god":
            self.file_label = QLabel(
                f"Creating GOD from: {os.path.basename(self.original_path)}"
            )
        else:
            self.file_label = QLabel(
                f"Processing: {os.path.basename(self.original_path)}"
            )

        self.file_label.setWordWrap(True)
        layout.addWidget(self.file_label)

        # Destination label (clickable)
        if self.operation_type == "extract":
            dest_text = f"To: {self.output_path}"
        elif self.operation_type == "create_god":
            dest_text = f"Output directory: {self.output_path}"
        else:
            dest_text = f"Output: {self.output_path}"

        self.dest_label = ClickableLabel(dest_text, self.output_path)
        self.dest_label.setWordWrap(True)
        layout.addWidget(self.dest_label)

        # Progress bar (indeterminate for both operations)
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 0)  # Indeterminate progress
        layout.addWidget(self.progress_bar)

        # Status label
        if self.operation_type == "extract":
            self.status_label = QLabel("Preparing extraction...")
        elif self.operation_type == "create_god":
            self.status_label = QLabel("Preparing GOD creation...")
        else:
            self.status_label = QLabel("Preparing...")

        layout.addWidget(self.status_label)

        # Output text area (for debugging if needed)
        self.output_text = QTextEdit()
        self.output_text.setMaximumHeight(100)
        self.output_text.setVisible(False)  # Hidden by default
        layout.addWidget(self.output_text)

        # Buttons
        button_layout = QHBoxLayout()

        # Show details button
        self.details_button = QPushButton("Show Details")
        self.details_button.clicked.connect(self._toggle_details)
        button_layout.addWidget(self.details_button)

        button_layout.addStretch()

        # Cancel button
        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.clicked.connect(self._cancel_processing)
        button_layout.addWidget(self.cancel_button)

        layout.addLayout(button_layout)

    def reset_for_new_operation(
        self,
        operation_type: str,
        input_path: str,
        output_path: str,
        is_batch_mode: bool = False,
    ):
        """Reset the dialog for a new operation (for dialog reuse in batch)"""
        self.operation_type = operation_type
        self.original_path = input_path
        self.input_path = input_path
        self.output_path = output_path
        self.is_cancelled = False
        self.cancel_zip_extraction = False
        self.temp_files = []
        self.temp_iso_path = None
        self.processing_process = None
        self.zip_extraction_process = None
        self.zip_extraction_thread = None
        self.is_batch_mode = is_batch_mode  # Track if we're in batch mode

        # Update window title
        if operation_type == "extract":
            self.setWindowTitle("Extracting Files")
        elif operation_type == "create_god":
            self.setWindowTitle("Creating GOD File")
        else:
            self.setWindowTitle("Processing Files")

        # Update file label
        if hasattr(self, "file_label"):
            if operation_type == "extract":
                self.file_label.setText(f"Extracting: {os.path.basename(input_path)}")
            elif operation_type == "create_god":
                self.file_label.setText(
                    f"Creating GOD from: {os.path.basename(input_path)}"
                )
            else:
                self.file_label.setText(f"Processing: {os.path.basename(input_path)}")

        # Update destination label directly using the stored reference
        if hasattr(self, "dest_label"):
            if operation_type == "extract":
                dest_text = f"To: {output_path}"
            elif operation_type == "create_god":
                dest_text = f"Output directory: {output_path}"
            else:
                dest_text = f"Output: {output_path}"

            self.dest_label.setText(dest_text)
            # Update the clickable path for the ClickableLabel
            if hasattr(self.dest_label, "update_path"):
                self.dest_label.update_path(output_path)

        # Reset UI state
        if hasattr(self, "output_text"):
            self.output_text.clear()
            self.output_text.setVisible(False)
        if hasattr(self, "details_button"):
            self.details_button.setText("Show Details")
        if hasattr(self, "progress_bar"):
            self.progress_bar.setRange(0, 0)
            self.progress_bar.setValue(0)
        if hasattr(self, "status_label"):
            if operation_type == "extract":
                self.status_label.setText("Preparing extraction...")
            elif operation_type == "create_god":
                self.status_label.setText("Preparing GOD creation...")
            else:
                self.status_label.setText("Preparing...")
        if hasattr(self, "cancel_button"):
            self.cancel_button.setEnabled(True)
            self.cancel_button.setText("Cancel")
            # Reconnect cancel button to cancel function (it might have been connected to accept)
            self.cancel_button.clicked.disconnect()
            self.cancel_button.clicked.connect(self._cancel_processing)

    def start_processing(self):
        """Start the processing operation"""
        try:
            if self.operation_type == "extract":
                return self._start_extraction()
            elif self.operation_type == "create_god":
                return self._start_god_creation()
            else:
                self._show_error(f"Unknown operation type: {self.operation_type}")
                return False

        except Exception as e:
            self._show_error(f"Failed to start processing: {str(e)}")
            return False

    def _start_extraction(self):
        """Start the extraction process (handles both ZIP and ISO)"""
        # Check if we're dealing with a ZIP file first
        if self.original_path.lower().endswith(".zip"):
            self._start_zip_extraction()
        else:
            self._setup_iso_process()
            self._start_iso_extraction()
        return True

    def _start_god_creation(self):
        """Start the GOD creation process (handles both ZIP and ISO)"""
        # Check if we're dealing with a ZIP file first
        if self.original_path.lower().endswith(".zip"):
            self._start_zip_extraction_for_god()
        else:
            self._setup_god_process()
            self._start_god_process()
        return True

    def _start_zip_extraction(self):
        """Start ZIP extraction process for ISO extraction"""
        # Update UI to show ZIP extraction
        self.file_label.setText(
            f"Extracting ZIP: {os.path.basename(self.original_path)}"
        )
        self.status_label.setText("Extracting ZIP archive...")

        # Create a temporary directory for ZIP extraction
        self.temp_dir = tempfile.mkdtemp(prefix="xbbm_zip_extract_")
        self.temp_files.append(self.temp_dir)

        # Update destination label to show temp extraction directory
        self.dest_label.setText(f"Extracting to: {self.temp_dir}")
        if hasattr(self.dest_label, "update_path"):
            self.dest_label.update_path(self.temp_dir)

        # Extract ZIP using Python's built-in zipfile module
        self._extract_zip_builtin(self._on_zip_extraction_complete)

    def _start_zip_extraction_for_god(self):
        """Start ZIP extraction process for GOD creation"""
        # Update UI to show ZIP extraction instead of GOD creation
        self.file_label.setText(
            f"Extracting ZIP: {os.path.basename(self.original_path)}"
        )
        self.status_label.setText("Extracting ZIP archive...")

        # Create a temporary directory for ZIP extraction
        self.temp_dir = tempfile.mkdtemp(prefix="xbbm_zip_extract_")
        self.temp_files.append(self.temp_dir)

        # Update destination label to show temp extraction directory
        self.dest_label.setText(f"Extracting to: {self.temp_dir}")
        if hasattr(self.dest_label, "update_path"):
            self.dest_label.update_path(self.temp_dir)

        # Extract ZIP using Python's built-in zipfile module
        self._extract_zip_builtin(self._on_zip_extraction_complete_for_god)

    def _extract_zip_builtin(self, completion_callback):
        """Extract ZIP using Python's built-in zipfile module"""

        def extract_zip():
            zip_ref = None
            try:
                # Check for cancellation before starting
                if self.cancel_zip_extraction:
                    return

                # Emit simple progress messages
                self.zip_progress_message.emit("Extracting files...")

                zip_ref = zipfile.ZipFile(self.original_path, "r")
                file_list = zip_ref.infolist()
                total_files = len(file_list)

                for i, file_info in enumerate(file_list):
                    # Check for cancellation
                    if self.cancel_zip_extraction:
                        self.zip_progress_message.emit("Extraction cancelled")
                        break

                    # Extract each file
                    zip_ref.extract(file_info, self.temp_dir)
                    # Show simple progress - only occasionally to avoid spam
                    if i % 10 == 0 or i == total_files - 1:
                        progress_msg = f"Extracting file {i + 1}/{total_files}..."
                        self.zip_progress_message.emit(progress_msg)

                # Close the zip file explicitly before proceeding
                if zip_ref:
                    zip_ref.close()
                    zip_ref = None

                # Check for cancellation after extraction
                if self.cancel_zip_extraction:
                    return

                self.zip_progress_message.emit("Files extracted")

                # Find the ISO file in the extracted contents
                iso_files = []
                for root, dirs, files in os.walk(self.temp_dir):
                    # Check for cancellation during file search
                    if self.cancel_zip_extraction:
                        return
                    for file in files:
                        if file.lower().endswith(".iso"):
                            iso_files.append(os.path.join(root, file))

                if iso_files:
                    self.temp_iso_path = iso_files[0]  # Use the first ISO found
                    self.input_path = self.temp_iso_path

                    iso_name = os.path.basename(self.temp_iso_path)
                    self.zip_progress_message.emit(f"Found ISO: {iso_name}")

                    # Call the completion callback only if not cancelled
                    if not self.cancel_zip_extraction:
                        QTimer.singleShot(100, completion_callback)
                else:
                    if not self.cancel_zip_extraction:
                        self.zip_progress_message.emit("ERROR: No ISO file found")
                        QTimer.singleShot(
                            100,
                            lambda: self._show_error(
                                "No ISO file found in ZIP archive"
                            ),
                        )

            except Exception as ex:
                if not self.cancel_zip_extraction:
                    error_msg = f"Failed to extract ZIP: {str(ex)}"
                    print(f"ZIP extraction error: {error_msg}")
                    self.zip_progress_message.emit(f"ERROR: {error_msg}")
                    QTimer.singleShot(100, lambda: self._show_error(error_msg))
            finally:
                # Explicitly close the ZIP file to release handles
                if zip_ref:
                    try:
                        zip_ref.close()
                    except Exception:
                        pass

        # Start extraction in a separate thread
        self.zip_extraction_thread = threading.Thread(target=extract_zip)
        self.zip_extraction_thread.daemon = True
        self.zip_extraction_thread.start()

    def _on_zip_progress_message(self, message: str):
        """Handle ZIP progress messages from background thread"""
        self.output_text.append(message)

    def _on_zip_extraction_complete(self):
        """Handle ZIP extraction completion and start ISO extraction"""
        self.status_label.setText("ZIP extracted, starting ISO extraction...")

        # Update the file label to show the ISO filename instead of ZIP
        if hasattr(self, "temp_iso_path") and self.temp_iso_path:
            iso_filename = os.path.basename(self.temp_iso_path)
            self.file_label.setText(f"Extracting: {iso_filename}")

        # Update destination label back to final output path
        self.dest_label.setText(f"To: {self.output_path}")
        if hasattr(self.dest_label, "update_path"):
            self.dest_label.update_path(self.output_path)

        self._setup_iso_process()
        self._start_iso_extraction()

    def _on_zip_extraction_complete_for_god(self):
        """Handle ZIP extraction completion and start GOD creation"""
        self.status_label.setText("ZIP extracted, starting GOD creation...")

        # Update the file label to show the ISO filename instead of ZIP
        if hasattr(self, "temp_iso_path") and self.temp_iso_path:
            iso_filename = os.path.basename(self.temp_iso_path)
            self.file_label.setText(f"Creating GOD from: {iso_filename}")

        # Update destination label back to final output path
        self.dest_label.setText(f"Output directory: {self.output_path}")
        if hasattr(self.dest_label, "update_path"):
            self.dest_label.update_path(self.output_path)

        self._setup_god_process()
        self._start_god_process()

    def _setup_iso_process(self):
        """Set up the ISO extraction process"""
        self.processing_process = QProcess(self)
        self.processing_process.setProgram("xdvdfs.exe")
        self.processing_process.setArguments(
            ["unpack", self.input_path, self.output_path]
        )

        # Connect signals
        self.processing_process.readyReadStandardOutput.connect(self._on_output_ready)
        self.processing_process.readyReadStandardError.connect(self._on_error_ready)
        self.processing_process.finished.connect(self._on_processing_finished)
        self.processing_process.started.connect(self._on_processing_started)

    def _setup_god_process(self):
        """Set up the GOD creation process"""
        total_threads = str(os.cpu_count() or 2)
        self.processing_process = QProcess(self)
        self.processing_process.setProgram("iso2god-x86_64-windows.exe")
        self.processing_process.setArguments(
            ["--trim", "-j", total_threads, self.input_path, self.output_path]
        )

        # Connect signals
        self.processing_process.readyReadStandardOutput.connect(self._on_output_ready)
        self.processing_process.readyReadStandardError.connect(self._on_error_ready)
        self.processing_process.finished.connect(self._on_processing_finished)
        self.processing_process.started.connect(self._on_processing_started)

    def _start_iso_extraction(self):
        """Start the ISO extraction process"""
        try:
            # Ensure the output directory exists
            os.makedirs(self.output_path, exist_ok=True)

            # Add simple message to details
            self.output_text.append("Starting extraction...")
            self.dest_label.setText(f"To: {self.output_path}")

            # Start the process
            self.processing_process.start()

            if not self.processing_process.waitForStarted(5000):
                self._show_error(
                    "Failed to start xdvdfs.exe. Make sure it's in the application directory."
                )
                return False

            return True

        except Exception as e:
            self._show_error(f"Failed to start ISO extraction: {str(e)}")
            return False

    def _start_god_process(self):
        """Start the GOD creation process"""
        try:
            # Ensure the output directory exists
            os.makedirs(self.output_path, exist_ok=True)

            # Add simple message to details
            self.output_text.append("Starting GOD creation...")
            self.dest_label.setText(f"Output directory: {self.output_path}")

            # Start the process
            self.processing_process.start()

            if not self.processing_process.waitForStarted(5000):
                self._show_error(
                    "Failed to start iso2god-x86_64-windows.exe. Make sure it's in the application directory."
                )
                return False

            return True

        except Exception as e:
            self._show_error(f"Failed to start GOD creation: {str(e)}")
            return False

    def _on_processing_started(self):
        """Handle processing started"""
        if self.operation_type == "extract":
            self.status_label.setText("Extracting ISO files...")
        elif self.operation_type == "create_god":
            self.status_label.setText("Creating GOD file...")
        else:
            self.status_label.setText("Processing...")

    def _on_output_ready(self):
        """Handle standard output from processing"""
        if self.processing_process:
            data = self.processing_process.readAllStandardOutput()
            text = bytes(data).decode("utf-8", errors="ignore")
            self.output_text.append(text.strip())

    def _on_error_ready(self):
        """Handle error output from processing"""
        if self.processing_process:
            data = self.processing_process.readAllStandardError()
            text = bytes(data).decode("utf-8", errors="ignore")
            self.output_text.append(f"ERROR: {text.strip()}")

    def _on_processing_finished(self, exit_code, exit_status):
        """Handle processing completion"""
        self.progress_bar.setRange(0, 1)
        self.progress_bar.setValue(1)

        if self.is_cancelled:
            if self.operation_type == "extract":
                self.status_label.setText("Extraction cancelled")
            elif self.operation_type == "create_god":
                self.status_label.setText("GOD creation cancelled")
            else:
                self.status_label.setText("Processing cancelled")
            self._cleanup_temp_files()
            return

        if exit_code == 0 and exit_status == QProcess.ExitStatus.NormalExit:
            if self.operation_type == "extract":
                self.status_label.setText("Extraction completed successfully!")
                self.output_text.append("Extraction completed")
            elif self.operation_type == "create_god":
                self.status_label.setText("GOD file created successfully!")
                self.output_text.append("GOD creation completed")
            else:
                self.status_label.setText("Processing completed successfully!")
                self.output_text.append("Processing completed")

            # Clean up temp files immediately after successful completion
            self._cleanup_temp_files()

            if self.is_batch_mode:
                # In batch mode, emit success signal immediately and don't change button
                self.processing_complete.emit(self.output_path)
                # Don't change the dialog - it will be reused for the next file
            else:
                # In single file mode, show Close button and let user close manually
                self.cancel_button.setText("Close")

                # Connect close button to accept the dialog
                self.cancel_button.clicked.disconnect()  # Disconnect cancel function
                self.cancel_button.clicked.connect(self.accept)

                # Emit success signal after a short delay
                QTimer.singleShot(
                    500, lambda: self.processing_complete.emit(self.output_path)
                )
                # Don't auto-close - let user click Close button
        else:
            error_msg = f"Processing failed with exit code {exit_code}"
            if self.output_text.toPlainText():
                error_msg += f"\n\nDetails:\n{self.output_text.toPlainText()}"

            if self.operation_type == "extract":
                self.status_label.setText("Extraction failed!")
            elif self.operation_type == "create_god":
                self.status_label.setText("GOD creation failed!")
            else:
                self.status_label.setText("Processing failed!")

            # Clean up temp files immediately after error
            self._cleanup_temp_files()

            if self.is_batch_mode:
                # In batch mode, emit error signal immediately
                self.processing_error.emit(error_msg)
                # Don't change the dialog - it will be reused or closed by batch handler
            else:
                # In single file mode, show Close button
                self.cancel_button.setText("Close")

                # Connect close button to accept the dialog
                self.cancel_button.clicked.disconnect()  # Disconnect cancel function
                self.cancel_button.clicked.connect(self.accept)

                self.processing_error.emit(error_msg)

    def _cancel_processing(self):
        """Cancel the processing"""
        self.is_cancelled = True

        # Cancel ZIP extraction thread if running
        if (
            hasattr(self, "zip_extraction_thread")
            and self.zip_extraction_thread
            and self.zip_extraction_thread.is_alive()
        ):
            self.cancel_zip_extraction = True
            self.status_label.setText("Cancelling ZIP extraction...")
            self.cancel_button.setEnabled(False)

            # Wait a bit for the thread to notice the cancellation
            QTimer.singleShot(1000, self._force_cleanup_and_close)
            return

        # Cancel main process if running
        if (
            self.processing_process
            and self.processing_process.state() == QProcess.ProcessState.Running
        ):
            if self.operation_type == "extract":
                self.status_label.setText("Cancelling extraction...")
            elif self.operation_type == "create_god":
                self.status_label.setText("Cancelling GOD creation...")
            else:
                self.status_label.setText("Cancelling...")

            self.cancel_button.setEnabled(False)

            # Terminate the process
            self.processing_process.terminate()

            # If it doesn't terminate within 3 seconds, kill it
            if not self.processing_process.waitForFinished(3000):
                self.processing_process.kill()
                self.processing_process.waitForFinished(1000)

            self._cleanup_temp_files()
            self.reject()
        elif (
            self.zip_extraction_process
            and self.zip_extraction_process.state() == QProcess.ProcessState.Running
        ):
            self.status_label.setText("Cancelling ZIP extraction...")
            self.cancel_button.setEnabled(False)

            # Terminate the ZIP process
            self.zip_extraction_process.terminate()

            # If it doesn't terminate within 3 seconds, kill it
            if not self.zip_extraction_process.waitForFinished(3000):
                self.zip_extraction_process.kill()
                self.zip_extraction_process.waitForFinished(1000)

            self._cleanup_temp_files()
            self.reject()
        else:
            # No process running, just cleanup and close the dialog
            self._cleanup_temp_files()
            self.reject()

    def _force_cleanup_and_close(self):
        """Force cleanup and close after cancellation timeout"""
        # Wait for ZIP extraction thread to finish (but don't block UI)
        if hasattr(self, "zip_extraction_thread") and self.zip_extraction_thread:
            # Check if thread is still alive, but don't wait - let cleanup handle it
            if self.zip_extraction_thread.is_alive():
                pass  # Let cleanup handle the running thread

        # Start threaded cleanup (completely non-blocking)
        self._cleanup_temp_files()

        # Close immediately - cleanup will continue in background
        self.reject()

    def _cleanup_temp_files(self):
        """Clean up any temporary files created during processing (threaded)"""
        # If there's already a cleanup worker running, let it finish
        if self.cleanup_worker and self.cleanup_worker.isRunning():
            return

        # Just set the cancellation flag - everything else happens in background
        self.cancel_zip_extraction = True

        # Create and start cleanup worker immediately
        self.cleanup_worker = CleanupWorker(
            temp_dir=getattr(self, "temp_dir", None),
            temp_files=self.temp_files.copy(),  # Make a copy to avoid modification during cleanup
            output_path=self.output_path if self.is_cancelled else None,
            is_cancelled=self.is_cancelled,
        )

        # Connect signals
        self.cleanup_worker.cleanup_finished.connect(self._on_cleanup_finished)

        # Start the worker immediately
        self.cleanup_worker.start()

        # Clear the temp files list immediately on UI thread since we made a copy
        self.temp_files = []

    def _on_cleanup_finished(self, success):
        """Handle cleanup completion"""
        # Clean up the worker
        if self.cleanup_worker:
            self.cleanup_worker.deleteLater()
            self.cleanup_worker = None

    def _toggle_details(self):
        """Toggle the visibility of the details text area"""
        if self.output_text.isVisible():
            self.output_text.setVisible(False)
            self.details_button.setText("Show Details")
            self.setFixedSize(500, 300)
        else:
            self.output_text.setVisible(True)
            self.details_button.setText("Hide Details")
            self.setFixedSize(500, 450)

    def _show_error(self, message: str):
        """Show an error message and close the dialog"""
        self.status_label.setText("Error occurred")
        self.cancel_button.setText("Close")
        self.processing_error.emit(message)

    def closeEvent(self, event):
        """Handle dialog close event"""
        if (
            self.processing_process
            and self.processing_process.state() == QProcess.ProcessState.Running
        ):
            # Ask for confirmation if processing is still running
            operation_name = (
                "extraction" if self.operation_type == "extract" else "GOD creation"
            )
            reply = QMessageBox.question(
                self,
                f"Cancel {operation_name.title()}?",
                f"{operation_name.title()} is still in progress. Do you want to cancel it?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )

            if reply == QMessageBox.StandardButton.Yes:
                self._cancel_processing()
                event.accept()
            else:
                event.ignore()
        else:
            # Clean up temp files when dialog closes normally
            self._cleanup_temp_files()
            event.accept()


# Keep the old class name for backward compatibility
ISOExtractionDialog = FileProcessingDialog
