import os
import shutil
import sys
import time
import subprocess
import psutil

exe_name = "XboxBackupManager-win64.exe"


def is_process_running(exe_name):
    for proc in psutil.process_iter(["name"]):
        if proc.info["name"] == exe_name:
            return True
    return False


def replace_and_restart(temp_exe):
    # Wait for the main application to exit
    while is_process_running(exe_name):
        time.sleep(0.5)

    # Ensure the new file is renamed to the proper executable name
    new_exe_path = os.path.join(os.path.dirname(temp_exe), exe_name)
    print(new_exe_path)

    # Replace the old executable with the new one
    os.remove(exe_name)
    shutil.move(temp_exe, new_exe_path)

    # Restart the application
    subprocess.Popen([new_exe_path], cwd=os.path.dirname(new_exe_path))
    sys.exit(0)


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: updater.exe <temp_exe>")
        sys.exit(1)

    temp_exe = sys.argv[1]

    replace_and_restart(temp_exe)
