#!/usr/bin/env python3
"""
Development file watcher for Xbox Backup Manager
Automatically restarts the application when Python files change
"""

import os
import sys
import time
import subprocess
import signal
from pathlib import Path

# Try to import watchdog, fall back to polling if not available
try:
    from watchdog.observers import Observer
    from watchdog.events import FileSystemEventHandler

    WATCHDOG_AVAILABLE = True
except ImportError:
    WATCHDOG_AVAILABLE = False
    print("⚠️  Watchdog not installed. Using polling method.")
    print("   Install with: pip install watchdog")


class AppReloader:
    """Handles reloading the application when files change"""

    def __init__(self, main_script="main.py", watch_patterns=None):
        self.main_script = main_script
        self.watch_patterns = watch_patterns or [".py"]
        self.process = None
        self.watch_dir = Path.cwd()

        # Files to ignore
        self.ignore_patterns = [
            "__pycache__",
            ".pyc",
            ".git",
            ".vscode",
            "build",
            "dist",
            ".venv",
            "venv",
            "env",
            ".pytest_cache",
            ".coverage",
            "*.log",
            "dev_watcher.py",  # Don't watch this file
            "view_palette_colors.py",
            "palette_viewer_gui.py",
        ]

    def should_watch_file(self, file_path):
        """Check if file should trigger a reload"""
        path_str = str(file_path)

        # Ignore certain patterns
        for pattern in self.ignore_patterns:
            if pattern in path_str:
                return False

        # Only watch files with specified extensions
        return any(path_str.endswith(ext) for ext in self.watch_patterns)

    def start_app(self):
        """Start the main application"""
        print(f"🚀 Starting {self.main_script}...")

        # Kill existing process if running
        if self.process:
            self.kill_app()

        # Get Python executable
        python_exe = sys.executable

        # Start new process
        try:
            self.process = subprocess.Popen(
                [python_exe, self.main_script],
                cwd=self.watch_dir,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                universal_newlines=True,
                bufsize=1,
            )
            print(f"✅ Started with PID: {self.process.pid}")
            return True
        except Exception as e:
            print(f"❌ Failed to start: {e}")
            return False

    def kill_app(self):
        """Kill the running application"""
        if self.process:
            try:
                if sys.platform == "win32":
                    # On Windows, use taskkill to kill the process tree
                    subprocess.run(
                        ["taskkill", "/F", "/T", "/PID", str(self.process.pid)],
                        check=False,
                        capture_output=True,
                    )
                else:
                    # On Unix systems
                    self.process.terminate()
                    try:
                        self.process.wait(timeout=3)
                    except subprocess.TimeoutExpired:
                        self.process.kill()
                        self.process.wait()

                print("🛑 Application stopped")
            except Exception as e:
                print(f"⚠️  Error stopping app: {e}")
            finally:
                self.process = None

    def restart_app(self, reason="File changed"):
        """Restart the application"""
        print(f"🔄 {reason}, restarting...")
        self.start_app()


class FileChangeHandler(FileSystemEventHandler):
    """Handles file system events using watchdog"""

    def __init__(self, reloader):
        self.reloader = reloader
        self.last_restart = 0
        self.debounce_delay = 1.0  # Seconds to wait before restart

    def on_modified(self, event):
        if event.is_directory:
            return

        if not self.reloader.should_watch_file(event.src_path):
            return

        # Debounce rapid file changes
        current_time = time.time()
        if current_time - self.last_restart < self.debounce_delay:
            return

        self.last_restart = current_time
        file_name = os.path.basename(event.src_path)
        self.reloader.restart_app(f"File '{file_name}' changed")


def watch_with_watchdog(reloader):
    """Watch files using the watchdog library"""
    event_handler = FileChangeHandler(reloader)
    observer = Observer()
    observer.schedule(event_handler, str(reloader.watch_dir), recursive=True)

    print(f"👀 Watching {reloader.watch_dir} for changes...")
    print("   Press Ctrl+C to stop")

    observer.start()

    try:
        while True:
            time.sleep(1)
            # Check if app is still running
            if reloader.process and reloader.process.poll() is not None:
                print("❌ Application exited")
                break
    except KeyboardInterrupt:
        print("\n🛑 Stopping watcher...")
    finally:
        observer.stop()
        observer.join()


def watch_with_polling(reloader):
    """Watch files using simple polling (fallback method)"""
    print(f"👀 Polling {reloader.watch_dir} for changes...")
    print("   Press Ctrl+C to stop")

    file_times = {}

    def scan_files():
        """Scan for file changes"""
        for file_path in reloader.watch_dir.rglob("*"):
            if file_path.is_file() and reloader.should_watch_file(file_path):
                try:
                    mtime = file_path.stat().st_mtime
                    if file_path in file_times:
                        if mtime > file_times[file_path]:
                            file_times[file_path] = mtime
                            return file_path
                    else:
                        file_times[file_path] = mtime
                except OSError:
                    pass
        return None

    # Initial scan
    scan_files()

    try:
        while True:
            time.sleep(1)

            # Check if app is still running
            if reloader.process and reloader.process.poll() is not None:
                print("❌ Application exited")
                break

            # Check for file changes
            changed_file = scan_files()
            if changed_file:
                reloader.restart_app(f"File '{changed_file.name}' changed")
                time.sleep(2)  # Give time for restart

    except KeyboardInterrupt:
        print("\n🛑 Stopping watcher...")


def main():
    """Main entry point"""
    reloader = AppReloader()

    # Handle Ctrl+C gracefully
    def signal_handler(sig, frame):
        print("\n🛑 Shutting down...")
        reloader.kill_app()
        sys.exit(0)

    signal.signal(signal.SIGINT, signal_handler)

    # Start the application initially
    if not reloader.start_app():
        print("❌ Failed to start application")
        return 1

    # Start watching for changes
    try:
        if WATCHDOG_AVAILABLE:
            watch_with_watchdog(reloader)
        else:
            watch_with_polling(reloader)
    finally:
        reloader.kill_app()

    return 0


if __name__ == "__main__":
    sys.exit(main())
