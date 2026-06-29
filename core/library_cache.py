"""
Handles loading and saving the library cache to a JSON file on disk.

Writes are atomic: we write to a temp file in the same directory, then
os.replace() it onto the real cache path. os.replace is atomic on both
POSIX and Windows, so a crash or power loss mid-write can never leave
behind a half-written, corrupted cache.json that fails to load on next
launch.
"""

from __future__ import annotations

import json
import os
import tempfile
from typing import Any

from core.models import Track, Playlist, PlayerState, Settings

CACHE_FILENAME = "library_cache.json"
CACHE_VERSION = 1


class LibraryCache:
    """In-memory representation of the full library, persisted to JSON."""

    def __init__(self, cache_path: str):
        self.cache_path = cache_path
        self.tracks: dict[str, Track] = {}        # keyed by file path
        self.playlists: dict[str, Playlist] = {}   # keyed by playlist id
        self.player_state = PlayerState()
        self.settings = Settings()

    # ---------- Loading ----------

    def load(self) -> None:
        """Load from disk if the cache file exists; otherwise start empty.

        A missing or unparseable cache file is not an error condition for
        a first run -- we just start fresh. We never raise here, since a
        corrupted cache must not block the app from starting at all.
        """
        if not os.path.exists(self.cache_path):
            return

        try:
            with open(self.cache_path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (json.JSONDecodeError, OSError):
            # Corrupt cache file: start fresh rather than crash.
            return

        self.tracks = {
            t["path"]: Track.from_dict(t) for t in data.get("tracks", [])
        }
        self.playlists = {
            p["id"]: Playlist.from_dict(p) for p in data.get("playlists", [])
        }
        if "player_state" in data:
            self.player_state = PlayerState.from_dict(data["player_state"])
        if "settings" in data:
            self.settings = Settings.from_dict(data["settings"])

    # ---------- Saving ----------

    def save(self) -> None:
        """Serialize the full cache and write it atomically."""
        data: dict[str, Any] = {
            "version": CACHE_VERSION,
            "tracks": [t.to_dict() for t in self.tracks.values()],
            "playlists": [p.to_dict() for p in self.playlists.values()],
            "player_state": self.player_state.to_dict(),
            "settings": self.settings.to_dict(),
        }

        cache_dir = os.path.dirname(self.cache_path) or "."
        os.makedirs(cache_dir, exist_ok=True)

        # Write to a temp file in the same directory (so os.replace stays
        # on the same filesystem/volume -- required for atomicity), then
        # swap it into place.
        fd, tmp_path = tempfile.mkstemp(dir=cache_dir, suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            os.replace(tmp_path, self.cache_path)
        except Exception:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
            raise

    # ---------- Convenience mutators (used by scanner now, by LibraryStore later) ----------

    def upsert_track(self, track: Track) -> None:
        self.tracks[track.path] = track

    def has_track(self, path: str) -> bool:
        return path in self.tracks

    def remove_track(self, path: str) -> None:
        self.tracks.pop(path, None)

    def mark_missing_tracks(self, existing_paths: set[str]) -> list[str]:
        """Flag tracks whose file no longer exists on disk. Returns paths
        newly marked missing (useful for UI notification later).
        """
        newly_missing = []
        for path, track in self.tracks.items():
            should_be_missing = path not in existing_paths
            if should_be_missing and not track.file_missing:
                track.file_missing = True
                newly_missing.append(path)
            elif not should_be_missing and track.file_missing:
                track.file_missing = False
        return newly_missing
