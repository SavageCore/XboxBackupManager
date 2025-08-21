import os
import sys


class ResourcePath:
    @staticmethod
    def get_resource_path(relative_path):
        """Get the absolute path to a resource, works for dev and PyInstaller."""
        if hasattr(sys, "_MEIPASS"):
            # Running in a PyInstaller bundle
            return os.path.join(sys._MEIPASS, relative_path)
        return os.path.join(os.path.abspath("."), relative_path)
