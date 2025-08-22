import os
import subprocess
import sys
from datetime import datetime, timedelta

import requests
import semver

from constants import APP_PATH, REPO, VERSION
from utils.settings_manager import SettingsManager


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
    response = requests.get(url)
    if response.status_code == 200:
        latest_release = response.json()
        latest_version = latest_release["tag_name"][1:]

        if semver.compare(VERSION, latest_version) == -1:
            return (
                True,
                latest_release["assets"][1]["browser_download_url"],
            )

    return False, None


def download_update(download_url, output_path):
    response = requests.get(download_url, stream=True)
    with open(output_path, "wb") as f:
        for chunk in response.iter_content(chunk_size=8192):
            if chunk:
                f.write(chunk)


def update(download_url: str):
    updater_path = os.path.join(APP_PATH, "updater.exe")

    # Download the latest updater
    download_update(
        "https://github.com/SavageCore/XboxBackupManager/releases/latest/download/updater.exe",
        updater_path,
    )

    temp_path = os.path.join(APP_PATH, "update_temp.exe")
    download_update(download_url, temp_path)

    subprocess.Popen([updater_path, temp_path])
    sys.exit(0)
