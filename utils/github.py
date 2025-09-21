import hashlib
import logging
import os
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path

import requests
import semver

from constants import APP_PATH, REPO, VERSION
from utils.settings_manager import SettingsManager

# Set up logging
logger = logging.getLogger(__name__)


def check_for_update():
    settings_manager = SettingsManager()
    last_update_check = settings_manager.settings.value("last_update_check")

    if last_update_check:
        last_update_check = datetime.fromisoformat(last_update_check)
        time_since_last_check = datetime.now() - last_update_check
        if time_since_last_check < timedelta(hours=1):
            return False, None

    settings_manager.settings.setValue("last_update_check", datetime.now().isoformat())

    url = f"https://api.github.com/repos/{REPO}/releases/latest"
    try:
        response = requests.get(
            url, timeout=10, headers={"User-Agent": f"XboxBackupManager/{VERSION}"}
        )
        response.raise_for_status()

        if response.status_code == 200:
            latest_release = response.json()
            latest_version = latest_release["tag_name"].lstrip(
                "v"
            )  # Handle both v1.0.0 and 1.0.0

            if semver.compare(VERSION, latest_version) == -1:
                # Find the MAIN APPLICATION asset (not the updater)
                main_app_url = None

                logger.info("Available assets in release:")
                for i, asset in enumerate(latest_release["assets"]):
                    logger.info(f"  [{i}] {asset['name']} - {asset['size']:,} bytes")

                # Look for the main application executable
                for asset in latest_release["assets"]:
                    asset_name = asset["name"].lower()
                    # Must contain "xbox" and "exe", but NOT "updater"
                    if (
                        "xbox" in asset_name
                        and asset_name.endswith(".exe")
                        and "updater" not in asset_name
                    ):
                        main_app_url = asset["browser_download_url"]
                        logger.info(f"Selected main app asset: {asset['name']}")
                        break

                if main_app_url:
                    return True, main_app_url
                else:
                    logger.error("Could not find main application in release assets")
                    return False, None

        return False, None

    except Exception as e:
        logger.error(f"Error checking for updates: {e}")
        return False, None


def download_update(download_url, output_path):
    """Download update with validation and error handling"""
    try:
        logger.info(f"Downloading update from: {download_url}")

        response = requests.get(
            download_url,
            stream=True,
            timeout=30,
            headers={"User-Agent": f"XboxBackupManager/{VERSION}"},
        )
        response.raise_for_status()

        # Get file size for validation
        total_size = int(response.headers.get("content-length", 0))

        # Download to temporary file first
        temp_path = output_path + ".tmp"
        downloaded_size = 0
        hash_sha256 = hashlib.sha256()

        with open(temp_path, "wb") as f:
            for chunk in response.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)
                    hash_sha256.update(chunk)
                    downloaded_size += len(chunk)

        # Validate download
        if total_size > 0 and downloaded_size != total_size:
            os.remove(temp_path)
            raise Exception(
                f"Download incomplete: {downloaded_size}/{total_size} bytes"
            )

        if downloaded_size < 1024:  # Basic size check
            os.remove(temp_path)
            raise Exception("Downloaded file appears to be too small")

        # Move to final location
        if os.path.exists(output_path):
            os.remove(output_path)
        os.rename(temp_path, output_path)

        logger.info(f"Download completed: {downloaded_size:,} bytes")

    except Exception as e:
        # Clean up on error
        for path in [temp_path, output_path + ".tmp"]:
            if os.path.exists(path):
                try:
                    os.remove(path)
                except Exception:
                    pass
        raise Exception(f"Failed to download update: {e}")


def update(download_url: str):
    """Improved update function with enhanced security and validation"""
    try:
        app_path = Path(APP_PATH)

        # Use descriptive names for updater and temp files
        updater_name = "XboxBackupManager-Updater.exe"
        temp_app_name = "XboxBackupManager-update-temp.exe"

        updater_path = app_path / updater_name
        temp_app_path = app_path / temp_app_name

        # Download URL for the updater (use descriptive name)
        updater_url = (
            f"https://github.com/{REPO}/releases/latest/download/{updater_name}"
        )

        logger.info("Starting Xbox Backup Manager update process")

        # Step 1: Download the latest updater
        logger.info("Downloading updater...")
        try:
            download_update(updater_url, str(updater_path))
        except Exception as e:
            logger.error(f"Failed to download updater: {e}")
            raise Exception(f"Could not download updater: {e}")

        # Step 2: Validate updater exists and is executable
        if not updater_path.exists():
            raise Exception("Updater download failed - file not found")

        if not os.access(updater_path, os.X_OK):
            logger.warning("Updater file permissions may be incorrect")

        # Step 3: Download the application update
        logger.info("Downloading application update...")
        try:
            download_update(download_url, str(temp_app_path))
        except Exception as e:
            logger.error(f"Failed to download application update: {e}")
            # Clean up updater on failure
            if updater_path.exists():
                updater_path.unlink()
            raise Exception(f"Could not download application update: {e}")

        # Step 4: Validate the downloaded application
        if not temp_app_path.exists():
            raise Exception("Application update download failed - file not found")

        # Step 5: Prepare environment for updater
        env = os.environ.copy()
        env.update(
            {
                "XBOX_BACKUP_UPDATE_SESSION": "1",
                "XBOX_BACKUP_VERSION": VERSION,
                "XBOX_BACKUP_PARENT_PID": str(os.getpid()),
            }
        )

        # Step 6: Launch updater with proper arguments and environment
        updater_args = [str(updater_path), str(temp_app_path)]

        logger.info(f"Launching updater: {' '.join(updater_args)}")

        # Use Popen with explicit, safe configuration
        process = subprocess.Popen(
            updater_args,
            cwd=str(app_path),
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            stdin=subprocess.DEVNULL,
            # Windows-specific flags for legitimate process creation
            creationflags=(
                subprocess.CREATE_NO_WINDOW | subprocess.CREATE_NEW_PROCESS_GROUP
                if os.name == "nt"
                else 0
            ),
        )

        # Step 7: Brief verification that updater started successfully
        import time

        time.sleep(1)

        if process.poll() is not None:
            raise Exception("Updater process failed to start or exited immediately")

        logger.info(f"Updater launched successfully (PID: {process.pid})")

        # Step 8: Save update state for verification after restart
        settings_manager = SettingsManager()
        settings_manager.settings.setValue("update_initiated", True)
        settings_manager.settings.setValue("updater_pid", process.pid)
        settings_manager.settings.setValue(
            "update_timestamp", datetime.now().isoformat()
        )

        logger.info("Update process initiated successfully. Application will now exit.")

        # Exit current application to allow updater to work
        sys.exit(0)

    except Exception as e:
        logger.error(f"Update process failed: {e}")

        # Clean up any downloaded files on error
        cleanup_files = [
            app_path / updater_name,
            app_path / temp_app_name,
            app_path / (updater_name + ".tmp"),
            app_path / (temp_app_name + ".tmp"),
        ]

        for file_path in cleanup_files:
            if file_path.exists():
                try:
                    file_path.unlink()
                    logger.debug(f"Cleaned up: {file_path}")
                except Exception as cleanup_error:
                    logger.warning(f"Could not clean up {file_path}: {cleanup_error}")

        # Re-raise the original error
        raise Exception(f"Update failed: {e}")
