import os
import subprocess
import sys
from datetime import datetime, timedelta

import requests
import semver

from constants import APP_PATH, REPO, VERSION
from utils.settings_manager import SettingsManager


def check_for_update():
    url = f"https://api.github.com/repos/{REPO}/releases/latest"
    response = requests.get(url)
    if response.status_code == 200:
        latest_release = response.json()
        return (
            latest_release["tag_name"],
            latest_release["assets"][1]["browser_download_url"],
        )
    return None, None


def download_update(download_url, output_path):
    response = requests.get(download_url, stream=True)
    with open(output_path, "wb") as f:
        for chunk in response.iter_content(chunk_size=8192):
            if chunk:
                f.write(chunk)


def auto_update():
    updater_path = os.path.join(APP_PATH, "updater.exe")
    settings_manager = SettingsManager()

    if not os.path.exists(updater_path):
        download_update(
            "https://github.com/SavageCore/XboxBackupManager/releases/latest/download/updater.exe",
            updater_path,
        )

    last_update_check = settings_manager.settings.value("last_update_check")
    if last_update_check:
        last_update_check = datetime.fromisoformat(last_update_check)
        time_since_last_check = datetime.now() - last_update_check
        if time_since_last_check < timedelta(hours=1):
            return

    latest_version, download_url = check_for_update()
    if latest_version is None:
        return
    latest_version = latest_version[1:]

    if semver.compare(VERSION, latest_version) == -1:
        # Download the latest updater
        download_update(
            "https://github.com/SavageCore/XboxBackupManager/releases/latest/download/updater.exe",
            updater_path,
        )

        temp_path = os.path.join(APP_PATH, "update_temp.exe")
        download_update(download_url, temp_path)

        settings_manager.settings.setValue(
            "last_update_check", datetime.now().isoformat()
        )

        subprocess.Popen([updater_path, temp_path])
        sys.exit(0)

    settings_manager.settings.setValue("last_update_check", datetime.now().isoformat())
