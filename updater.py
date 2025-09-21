#!/usr/bin/env python3
"""
Xbox Backup Manager Updater
Safely replaces the main application executable with an updated version.
"""

import logging
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

import psutil

# Configuration constants
EXE_NAME = "XboxBackupManager.exe"
MAX_WAIT_TIME = 30  # Maximum seconds to wait for process to exit
PROCESS_CHECK_INTERVAL = 0.5  # Seconds between process checks
UPDATE_MARKER_FILE = ".update_in_progress"

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[logging.FileHandler("updater.log"), logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)


class UpdaterError(Exception):
    """Custom exception for updater-specific errors"""

    pass


class XboxBackupManagerUpdater:
    """Safe updater for Xbox Backup Manager application"""

    def __init__(self, temp_exe_path: str):
        self.temp_exe_path = Path(temp_exe_path).resolve()
        self.target_exe_path = Path(EXE_NAME).resolve()
        self.backup_exe_path = Path(f"{EXE_NAME}.backup").resolve()
        self.update_marker = Path(UPDATE_MARKER_FILE)

        logger.info("Updater initialized:")
        logger.info(f"  Temp executable: {self.temp_exe_path}")
        logger.info(f"  Target executable: {self.target_exe_path}")

    def validate_inputs(self):
        """Validate that all required files exist and are valid"""
        # Check if temp executable exists and is a file
        if not self.temp_exe_path.exists():
            raise UpdaterError(f"Temporary executable not found: {self.temp_exe_path}")

        if not self.temp_exe_path.is_file():
            raise UpdaterError(f"Temporary path is not a file: {self.temp_exe_path}")

        # Check if temp executable has reasonable size (not empty, not too large)
        file_size = self.temp_exe_path.stat().st_size
        if file_size < 1024:  # Less than 1KB
            raise UpdaterError("Temporary executable appears to be too small")

        if file_size > 500 * 1024 * 1024:  # More than 500MB
            raise UpdaterError("Temporary executable appears to be too large")

        # Check if temp executable is actually executable
        if not os.access(self.temp_exe_path, os.X_OK):
            raise UpdaterError("Temporary file is not executable")

        logger.info(f"Validation passed. Temp file size: {file_size:,} bytes")

    def is_target_process_running(self) -> bool:
        """Check if the target application is currently running"""
        try:
            for proc in psutil.process_iter(["name", "exe"]):
                proc_info = proc.info
                if proc_info["name"] == EXE_NAME:
                    logger.debug(f"Found running process: {proc_info['name']}")
                    return True
        except (psutil.NoSuchProcess, psutil.AccessDenied) as e:
            # Process disappeared or access denied - not critical
            logger.debug(f"Process check warning: {e}")

        return False

    def wait_for_process_exit(self):
        """Wait for the target application to exit, with timeout"""
        logger.info(f"Waiting for {EXE_NAME} to exit...")
        start_time = time.time()

        while self.is_target_process_running():
            elapsed = time.time() - start_time
            if elapsed > MAX_WAIT_TIME:
                raise UpdaterError(
                    f"Timeout waiting for {EXE_NAME} to exit after {MAX_WAIT_TIME}s"
                )

            logger.debug(f"Still waiting... ({elapsed:.1f}s)")
            time.sleep(PROCESS_CHECK_INTERVAL)

        logger.info("Target application has exited")
        # Give a moment for file handles to be released
        time.sleep(1)

    def create_backup(self):
        """Create a backup of the current executable"""
        if self.target_exe_path.exists():
            try:
                # Remove old backup if it exists
                if self.backup_exe_path.exists():
                    self.backup_exe_path.unlink()

                # Create new backup
                shutil.copy2(self.target_exe_path, self.backup_exe_path)
                logger.info(f"Created backup: {self.backup_exe_path}")
            except Exception as e:
                logger.warning(f"Failed to create backup: {e}")

    def replace_executable(self):
        """Replace the target executable with the new version"""
        try:
            # Remove the old executable
            if self.target_exe_path.exists():
                self.target_exe_path.unlink()
                logger.info(f"Removed old executable: {self.target_exe_path}")

            # Move new executable into place
            shutil.move(str(self.temp_exe_path), str(self.target_exe_path))
            logger.info(f"Moved new executable to: {self.target_exe_path}")

            # Verify the new file exists and is executable
            if not self.target_exe_path.exists():
                raise UpdaterError("New executable was not created successfully")

            if not os.access(self.target_exe_path, os.X_OK):
                raise UpdaterError("New executable is not executable")

        except Exception as e:
            # Try to restore from backup if something went wrong
            self.restore_from_backup()
            raise UpdaterError(f"Failed to replace executable: {e}")

    def restore_from_backup(self):
        """Restore the executable from backup if update failed"""
        if self.backup_exe_path.exists() and not self.target_exe_path.exists():
            try:
                shutil.move(str(self.backup_exe_path), str(self.target_exe_path))
                logger.info("Restored executable from backup")
            except Exception as e:
                logger.error(f"Failed to restore from backup: {e}")

    def launch_application(self):
        """Launch the updated application"""
        try:
            # Get the directory containing the executable
            work_dir = self.target_exe_path.parent

            # Prepare launch arguments
            launch_args = [str(self.target_exe_path)]

            # Add environment variable to indicate this was launched by updater
            env = os.environ.copy()
            env["XBOX_BACKUP_UPDATED"] = "1"
            env["XBOX_BACKUP_UPDATER_PID"] = str(os.getpid())

            logger.info(f"Launching application: {self.target_exe_path}")

            # Launch the application
            process = subprocess.Popen(
                launch_args,
                cwd=str(work_dir),
                env=env,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                stdin=subprocess.DEVNULL,
                # Windows-specific: don't create new console window
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
            )

            # Wait briefly to ensure successful launch
            time.sleep(2)

            # Check if process is still running
            if process.poll() is not None:
                raise UpdaterError("Launched application exited immediately")

            logger.info(f"Successfully launched application (PID: {process.pid})")
            return process.pid

        except Exception as e:
            raise UpdaterError(f"Failed to launch application: {e}")

    def cleanup(self):
        """Clean up temporary files and markers"""
        try:
            # Remove backup file if update was successful
            if self.backup_exe_path.exists():
                self.backup_exe_path.unlink()
                logger.info("Cleaned up backup file")

            # Remove update marker
            if self.update_marker.exists():
                self.update_marker.unlink()
                logger.info("Removed update marker")

        except Exception as e:
            logger.warning(f"Cleanup warning: {e}")

    def perform_update(self):
        """Perform the complete update process"""
        try:
            # Create update marker
            self.update_marker.touch()

            logger.info("Starting Xbox Backup Manager update process")

            # Step 1: Validate inputs
            self.validate_inputs()

            # Step 2: Wait for application to exit
            self.wait_for_process_exit()

            # Step 3: Create backup
            self.create_backup()

            # Step 4: Replace executable
            self.replace_executable()

            # Step 5: Launch updated application
            self.launch_application()

            # Step 6: Cleanup
            self.cleanup()

            logger.info("Update completed successfully")
            return True

        except UpdaterError as e:
            logger.error(f"Update failed: {e}")
            return False
        except Exception as e:
            logger.error(f"Unexpected error during update: {e}")
            return False


def main():
    """Main updater entry point"""
    logger.info("Xbox Backup Manager Updater starting")

    # Validate command line arguments
    if len(sys.argv) != 2:
        logger.error("Usage: updater.exe <temp_executable_path>")
        print("Usage: updater.exe <temp_executable_path>")
        sys.exit(1)

    temp_exe_path = sys.argv[1]

    try:
        # Create and run updater
        updater = XboxBackupManagerUpdater(temp_exe_path)
        success = updater.perform_update()

        if success:
            logger.info("Update process completed successfully")
            sys.exit(0)
        else:
            logger.error("Update process failed")
            sys.exit(1)

    except Exception as e:
        logger.error(f"Fatal error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
