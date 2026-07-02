"""
Automatic sync mechanism for AuraPlayer.
Tracks file changes (additions, deletions, and updates) using a local metadata file (.music-sync.json).
"""

from __future__ import annotations

import json
import os
import time
from typing import Callable, Optional

from core.library_store import LibraryStore
from core.metadata_reader import read_track_metadata

SYNC_METADATA_FILENAME = ".music-sync.json"
ProgressCallback = Callable[[int, int, str], None]


class SyncManager:
    """Manages tracking file modifications and syncing changes to the library store."""

    def __init__(self, store: LibraryStore, base_dir: str):
        self.store = store
        self.sync_file_path = os.path.join(base_dir, SYNC_METADATA_FILENAME)
        self.metadata = self._load_metadata()

    def _load_metadata(self) -> dict:
        """Load sync metadata from .music-sync.json or return a fresh state if missing."""
        if not os.path.exists(self.sync_file_path):
            return {"folders": {}, "change_log": {"pending": []}}
        try:
            with open(self.sync_file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                # Ensure structure is sound
                if "folders" not in data:
                    data["folders"] = {}
                if "change_log" not in data:
                    data["change_log"] = {"pending": []}
                return data
        except Exception:
            return {"folders": {}, "change_log": {"pending": []}}

    def save_metadata(self) -> None:
        """Atomic-like write of the sync metadata to prevent corruption on crash."""
        tmp_path = self.sync_file_path + ".tmp"
        try:
            with open(tmp_path, "w", encoding="utf-8") as f:
                json.dump(self.metadata, f, indent=2, ensure_ascii=False)
            os.replace(tmp_path, self.sync_file_path)
        except Exception:
            # Fall back to direct write if atomic replacement fails on Windows
            try:
                with open(self.sync_file_path, "w", encoding="utf-8") as f:
                    json.dump(self.metadata, f, indent=2, ensure_ascii=False)
                if os.path.exists(tmp_path):
                    os.remove(tmp_path)
            except Exception:
                if os.path.exists(tmp_path):
                    os.remove(tmp_path)

    def check_folder_changes(self, folder: str) -> bool:
        """
        Scans a folder, compares with metadata, and populates change_log["pending"].
        Returns True if any changes (adds, deletes, or edits) were found.
        If the folder is missing, returns False.
        """
        if not os.path.isdir(folder):
            return False

        from core.scanner import find_audio_files
        current_files = find_audio_files(folder)

        folder_cache = self.metadata["folders"].setdefault(
            folder, {"files": {}, "last_scanned": 0.0}
        )
        cached_files = folder_cache.get("files", {})

        current_file_set = set(current_files)
        cached_file_set = set(cached_files.keys())

        # Detect additions
        adds = list(current_file_set - cached_file_set)

        # Detect deletions
        deletes = list(cached_file_set - current_file_set)

        # Detect edits (modified files)
        edits = []
        for filepath in (current_file_set & cached_file_set):
            try:
                mtime = os.path.getmtime(filepath)
                size = os.path.getsize(filepath)
            except OSError:
                continue

            cached_info = cached_files[filepath]
            if cached_info.get("mtime") != mtime or cached_info.get("size") != size:
                edits.append(filepath)

        # Merge them into pending change log
        pending = self.metadata.setdefault("change_log", {}).setdefault("pending", [])

        # Avoid duplicate pending entries
        existing_pending_paths = {item["path"] for item in pending}

        for path in adds:
            if path not in existing_pending_paths:
                pending.append({"action": "add", "path": path, "folder": folder})
        for path in deletes:
            if path not in existing_pending_paths:
                pending.append({"action": "delete", "path": path, "folder": folder})
        for path in edits:
            if path not in existing_pending_paths:
                pending.append({"action": "edit", "path": path, "folder": folder})

        has_changes = len(adds) > 0 or len(deletes) > 0 or len(edits) > 0
        self.save_metadata()
        return has_changes

    def process_pending_changes(self, progress_callback: Optional[ProgressCallback] = None) -> dict:
        """
        Processes pending changes one by one. Updates the metadata in .music-sync.json
        and the track cache, saving both after each change to prevent data loss.
        """
        pending = self.metadata.get("change_log", {}).get("pending", [])
        total = len(pending)
        if total == 0:
            return {"added": 0, "deleted": 0, "edited": 0}

        added_cnt = 0
        deleted_cnt = 0
        edited_cnt = 0

        # Create a copy of the list to iterate through safely
        pending_list = list(pending)

        for idx, item in enumerate(pending_list, start=1):
            action = item["action"]
            path = item["path"]
            folder = item["folder"]

            if progress_callback:
                progress_callback(idx, total, os.path.basename(path))

            # Apply change to LibraryStore/LibraryCache
            if action in ("add", "edit"):
                if os.path.exists(path):
                    try:
                        track = read_track_metadata(
                            path,
                            source_folder=folder,
                            artist_separators=self.store.cache.settings.active_separators(),
                        )
                        # Ensure file_missing is False
                        track.file_missing = False

                        if action == "add":
                            self.store.add_tracks([track])
                            added_cnt += 1
                        else:
                            self.store.update_track(track)
                            edited_cnt += 1

                        # Update metadata files record
                        folder_cache = self.metadata["folders"].setdefault(
                            folder, {"files": {}, "last_scanned": 0.0}
                        )
                        folder_cache["files"][path] = {
                            "mtime": os.path.getmtime(path),
                            "size": os.path.getsize(path),
                        }
                    except Exception as e:
                        print(f"Sync error reading {path}: {e}")
                else:
                    # File disappeared between detection and sync
                    self.store.remove_track(path)
                    folder_cache = self.metadata["folders"].setdefault(
                        folder, {"files": {}, "last_scanned": 0.0}
                    )
                    folder_cache["files"].pop(path, None)
                    deleted_cnt += 1

            elif action == "delete":
                self.store.remove_track(path)
                folder_cache = self.metadata["folders"].setdefault(
                    folder, {"files": {}, "last_scanned": 0.0}
                )
                folder_cache["files"].pop(path, None)
                deleted_cnt += 1

            # Remove this item from the pending changes in metadata and save immediately
            if item in pending:
                pending.remove(item)

            self.save_metadata()
            self.store.save()

        # Update last_scanned timestamps for folders that were processed
        unique_folders = {item["folder"] for item in pending_list}
        for folder in unique_folders:
            if folder in self.metadata["folders"]:
                self.metadata["folders"][folder]["last_scanned"] = time.time()
        self.save_metadata()

        return {"added": added_cnt, "deleted": deleted_cnt, "edited": edited_cnt}
