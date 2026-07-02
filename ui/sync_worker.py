"""
Runs sync operations on a background QThread to keep the UI perfectly responsive.
Handles resuming pending changes first, then scanning and applying new changes.
"""

from __future__ import annotations

from PyQt6.QtCore import QThread, pyqtSignal
from core.sync_manager import SyncManager


class SyncWorker(QThread):
    progress = pyqtSignal(int, int, str)       # current, total, filename
    finished_sync = pyqtSignal(dict)           # summary dict of {added, deleted, edited}

    def __init__(self, sync_manager: SyncManager, folders: list[str], parent=None):
        super().__init__(parent)
        self.sync_manager = sync_manager
        self.folders = folders

    def run(self) -> None:
        def on_progress(current, total, filename):
            self.progress.emit(current, total, filename)

        # 1. Resume any pre-existing pending changes (interrupted from previous runs)
        initial_summary = self.sync_manager.process_pending_changes(progress_callback=on_progress)

        # 2. Check for new changes in each folder to populate the change_log["pending"]
        for folder in self.folders:
            self.sync_manager.check_folder_changes(folder)

        # 3. Process new changes
        final_summary = self.sync_manager.process_pending_changes(progress_callback=on_progress)

        # 4. Combine summaries
        summary = {
            "added": initial_summary["added"] + final_summary["added"],
            "deleted": initial_summary["deleted"] + final_summary["deleted"],
            "edited": initial_summary["edited"] + final_summary["edited"],
        }
        self.finished_sync.emit(summary)
