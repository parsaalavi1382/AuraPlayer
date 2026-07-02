"""
On first launch with no folders added yet, every tab will show its
"no music folder selected" empty state -- that's correct, not a bug.
Open Settings (⚙ in the top-right) and add the bundled test_music/
folder (or your own real music folder) to see the views populate.
"""

import os
import sys

from PyQt6.QtWidgets import QApplication

from core.library_store import LibraryStore
from ui.main_window import MainWindow
from ui.theme import build_stylesheet

CACHE_PATH = os.path.join(os.path.dirname(__file__), "library_cache.json")


def main():
    app = QApplication(sys.argv)

    store = LibraryStore(CACHE_PATH)
    # Apply the user's saved theme on startup (not just the hardcoded
    # default) -- store must be constructed first so settings.theme is
    # actually loaded from disk before we style the app.
    app.setStyleSheet(build_stylesheet(store.cache.settings.theme))

    window = MainWindow(store)
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
