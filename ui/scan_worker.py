"""
Runs scan_folders() on a background QThread so the UI never freezes
while scanning, with progress signals wired to a progress dialog.

This is the threading requirement from the brief made concrete: without
this, scanning a few thousand files would lock up the entire UI (no
window dragging, no button clicks, nothing) for however long the scan
takes.
"""

from __future__ import annotations

from PyQt6.QtCore import QThread, pyqtSignal

from core.library_cache import LibraryCache
from core.scanner import scan_folders


class ScanWorker(QThread):
    progress = pyqtSignal(int, int, str)   # current, total, filename
    finished_scan = pyqtSignal(dict)        # summary dict

    def __init__(self, cache: LibraryCache, folders: list[str], parent=None):
        super().__init__(parent)
        self.cache = cache
        self.folders = folders

    def run(self) -> None:
        def on_progress(current, total, filename):
            self.progress.emit(current, total, filename)

        summary = scan_folders(self.cache, self.folders, progress_callback=on_progress)
        self.cache.save()
        self.finished_scan.emit(summary)
