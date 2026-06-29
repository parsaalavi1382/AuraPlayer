"""
LibraryStore: the single source of truth for the in-memory library,
wrapping LibraryCache with Qt signals so every view can react to changes
live, without polling or full-app restarts.

This is the "Observer" half of the architecture promised in the original
plan: any code that mutates the library (scanner, metadata editor,
playlist manager, library-folder management) goes through this class,
and every view subscribes to its signals to refresh only what changed.

Qt signals are used as our event bus -- not a custom pub/sub system --
because that's idiomatic PyQt6 and integrates directly with widgets'
slot mechanism (thread-safe queued connections when the emitting code
runs on a background thread, e.g. the scanner).
"""

from __future__ import annotations

import os

from PyQt6.QtCore import QObject, pyqtSignal

from core.library_cache import LibraryCache
from core.models import Track, Playlist


class LibraryStore(QObject):
    # Emitted when one or more tracks are added (e.g. after a folder scan).
    # Argument: list of track paths added.
    tracks_added = pyqtSignal(list)

    # Emitted when a single track's metadata changes (edit, missing-flag
    # toggle). Argument: the track path that changed.
    track_updated = pyqtSignal(str)

    # Emitted when a track is removed from the library entirely.
    track_removed = pyqtSignal(str)

    # Emitted when the set of tracks marked "file missing" changes.
    # Argument: list of paths newly marked missing.
    tracks_missing = pyqtSignal(list)

    # Emitted on any change to the playlists collection (add/remove/
    # rename/reorder). Argument: playlist id (or "" for a bulk change).
    playlists_changed = pyqtSignal(str)

    # Emitted when a scan starts/progresses/finishes, for progress UI.
    scan_progress = pyqtSignal(int, int, str)   # current, total, filename
    scan_finished = pyqtSignal(dict)            # summary dict from scanner

    def __init__(self, cache_path: str, parent=None):
        super().__init__(parent)
        self.cache = LibraryCache(cache_path)
        self.cache.load()

    # ---------- Read helpers (views call these, never touch cache directly) ----------

    def all_tracks(self) -> list[Track]:
        return list(self.cache.tracks.values())

    def get_track(self, path: str) -> Track | None:
        return self.cache.tracks.get(path)

    def all_playlists(self) -> list[Playlist]:
        return list(self.cache.playlists.values())

    # ---------- Mutators (always go through here, then emit + persist) ----------

    def add_tracks(self, tracks: list[Track]) -> None:
        if not tracks:
            return
        for t in tracks:
            self.cache.upsert_track(t)
        self.cache.save()
        self.tracks_added.emit([t.path for t in tracks])

    def update_track(self, track: Track) -> None:
        self.cache.upsert_track(track)
        self.cache.save()
        self.track_updated.emit(track.path)

    def remove_track(self, path: str) -> None:
        self.cache.remove_track(path)
        self.cache.save()
        self.track_removed.emit(path)

    def mark_missing(self, paths: list[str]) -> None:
        if not paths:
            return
        for p in paths:
            t = self.cache.tracks.get(p)
            if t:
                t.file_missing = True
        self.cache.save()
        self.tracks_missing.emit(paths)

    def remove_folder(self, folder: str) -> list[str]:
        """Remove all tracks sourced from `folder` and forget the folder
        itself. Returns the list of removed track paths. Does not touch
        files on disk -- this only affects the library, never the
        filesystem, per the agreed default-folder-removal behavior.
        """
        to_remove = [
            p for p, t in self.cache.tracks.items() if t.source_folder == folder
        ]
        for p in to_remove:
            self.cache.remove_track(p)
        if folder in self.cache.settings.music_folders:
            self.cache.settings.music_folders.remove(folder)
        self.cache.save()
        for p in to_remove:
            self.track_removed.emit(p)
        return to_remove

    def save(self) -> None:
        """Explicit save hook for state that doesn't go through a mutator
        above (e.g. player state updates from the playback engine in a
        later step).
        """
        self.cache.save()
