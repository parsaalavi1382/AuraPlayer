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
import shutil

from PyQt6.QtCore import QObject, pyqtSignal

from core.library_cache import LibraryCache
from core.models import Track, Playlist
from utils.paths import get_writable_data_path


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
        self._playlist_sort_states = {}

    def get_playlist_sort_state(self, playlist_id: str) -> tuple[int, bool]:
        return self._playlist_sort_states.get(playlist_id, (-1, True))

    def set_playlist_sort_state(self, playlist_id: str, col: int, ascending: bool) -> None:
        self._playlist_sort_states[playlist_id] = (col, ascending)

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

    # ---------- Playlist APIs ----------

    def get_playlist(self, playlist_id: str) -> Playlist | None:
        return self.cache.playlists.get(playlist_id)

    def get_playlist_tracks(self, playlist_id: str) -> list[Track]:
        if playlist_id == "smart_recently_added":
            tracks = list(self.all_tracks())
            def get_mtime(t):
                try:
                    return os.path.getmtime(t.path)
                except Exception:
                    return 0.0
            tracks.sort(key=get_mtime, reverse=True)
            return tracks
        elif playlist_id == "smart_favorites":
            pl = self.cache.playlists.get("smart_favorites")
            if not pl:
                pl = Playlist(id="smart_favorites", name="Favorites")
                self.cache.playlists["smart_favorites"] = pl
                self.cache.save()
            tracks = []
            for p in pl.track_paths:
                t = self.get_track(p)
                if t:
                    tracks.append(t)
            return tracks
        elif playlist_id == "smart_recently_played":
            tracks = [t for t in self.all_tracks() if t.last_played is not None]
            tracks.sort(key=lambda t: t.last_played, reverse=True)
            return tracks
        elif playlist_id == "smart_most_played":
            tracks = [t for t in self.all_tracks() if t.play_count > 0]
            tracks.sort(key=lambda t: t.play_count, reverse=True)
            return tracks
        else:
            pl = self.cache.playlists.get(playlist_id)
            if not pl:
                return []
            tracks = []
            for p in pl.track_paths:
                t = self.get_track(p)
                if t:
                    tracks.append(t)
            return tracks

    def create_playlist(self, name: str) -> str:
        import uuid
        pl_id = str(uuid.uuid4())
        pl = Playlist(id=pl_id, name=name)
        self.cache.playlists[pl_id] = pl
        self.cache.save()
        self.playlists_changed.emit(pl_id)
        return pl_id

    def add_tracks_to_playlist(self, playlist_id: str, track_paths: list[str], at_index: int | None = None) -> None:
        pl = self.cache.playlists.get(playlist_id)
        if not pl:
            if playlist_id == "smart_favorites":
                pl = Playlist(id="smart_favorites", name="Favorites")
                self.cache.playlists["smart_favorites"] = pl
            else:
                return
        
        duplicates = []
        to_add = []
        for path in track_paths:
            if path in pl.track_paths:
                track = self.get_track(path)
                name = track.title if track else os.path.basename(path)
                duplicates.append(name)
            else:
                to_add.append(path)
                
        if duplicates:
            from PyQt6.QtWidgets import QMessageBox
            if len(duplicates) == 1:
                QMessageBox.warning(
                    None,
                    "Duplicate Song",
                    f"The song \"{duplicates[0]}\" is already in this playlist."
                )
            else:
                dup_list = "\n".join(f"• {name}" for name in duplicates)
                QMessageBox.warning(
                    None,
                    "Duplicate Songs",
                    f"The following songs are already in this playlist and won't be added again:\n\n{dup_list}"
                )
                
        if not to_add:
            return
            
        if at_index is None or at_index < 0:
            for path in to_add:
                pl.track_paths.append(path)
        else:
            idx = max(0, min(at_index, len(pl.track_paths)))
            for path in reversed(to_add):
                pl.track_paths.insert(idx, path)
        self.cache.save()
        self.playlists_changed.emit(playlist_id)

    def remove_track_from_playlist(self, playlist_id: str, track_path: str) -> None:
        pl = self.cache.playlists.get(playlist_id)
        if not pl:
            return
        if track_path in pl.track_paths:
            pl.track_paths.remove(track_path)
            self.cache.save()
            self.playlists_changed.emit(playlist_id)

    def remove_track_from_playlist_by_index(self, playlist_id: str, index: int) -> None:
        pl = self.cache.playlists.get(playlist_id)
        if not pl:
            return
        if 0 <= index < len(pl.track_paths):
            pl.track_paths.pop(index)
            self.cache.save()
            self.playlists_changed.emit(playlist_id)

    def reorder_playlist(self, playlist_id: str, from_row: int, to_row: int) -> None:
        pl = self.cache.playlists.get(playlist_id)
        if not pl:
            return
        if not (0 <= from_row < len(pl.track_paths)):
            return
        
        path = pl.track_paths.pop(from_row)
        if to_row > from_row:
            to_row -= 1
            
        to_row = max(0, min(to_row, len(pl.track_paths)))
        pl.track_paths.insert(to_row, path)
        self.cache.save()
        self.playlists_changed.emit(playlist_id)

    def set_playlist_track_paths(self, playlist_id: str, paths: list[str]) -> None:
        pl = self.cache.playlists.get(playlist_id)
        if not pl:
            return
        pl.track_paths = list(paths)
        self.cache.save()
        self.playlists_changed.emit(playlist_id)

    def rename_playlist(self, playlist_id: str, new_name: str) -> None:
        pl = self.cache.playlists.get(playlist_id)
        if not pl or playlist_id.startswith("smart_"):
            return
        pl.name = new_name
        self.cache.save()
        self.playlists_changed.emit(playlist_id)

    def delete_playlist(self, playlist_id: str) -> None:
        if playlist_id.startswith("smart_"):
            return
        self.cache.playlists.pop(playlist_id, None)
        self.cache.save()
        self.playlists_changed.emit(playlist_id)

    def set_playlist_cover(self, playlist_id: str, cover_path: str | None) -> None:
        pl = self.cache.playlists.get(playlist_id)
        if not pl or playlist_id.startswith("smart_"):
            return
        
        target_dir = get_writable_data_path("playlist_covers")
        
        # Clean up existing custom cover files for this playlist to avoid stale image files
        if os.path.exists(target_dir):
            try:
                for f in os.listdir(target_dir):
                    if f.startswith(f"cover_{playlist_id}"):
                        try:
                            os.remove(os.path.join(target_dir, f))
                        except Exception:
                            pass
            except Exception:
                pass

        if cover_path:
            try:
                os.makedirs(target_dir, exist_ok=True)
                ext = os.path.splitext(cover_path)[1]
                target_filename = f"cover_{playlist_id}{ext}"
                target_path = os.path.join(target_dir, target_filename)
                
                # Copy the selected image into the app data directory
                if os.path.abspath(cover_path) != os.path.abspath(target_path):
                    shutil.copy2(cover_path, target_path)
                
                pl.cover_path = target_path
            except Exception:
                # Fallback to absolute cover_path if copying failed
                pl.cover_path = cover_path
        else:
            pl.cover_path = None
            
        self.cache.save()
        self.playlists_changed.emit(playlist_id)

    def update_playlist_cover(self, playlist_id: str, cover_path: str) -> None:
        self.set_playlist_cover(playlist_id, cover_path)

    def is_track_favorited(self, track_path: str) -> bool:
        pl = self.cache.playlists.get("smart_favorites")
        if not pl:
            return False
        return track_path in pl.track_paths

    def is_favorite(self, track_path: str) -> bool:
        return self.is_track_favorited(track_path)

    def toggle_favorite(self, track_path: str) -> None:
        fav = self.is_track_favorited(track_path)
        self.set_track_favorited(track_path, not fav)

    def set_track_favorited(self, track_path: str, favorited: bool) -> None:
        pl = self.cache.playlists.get("smart_favorites")
        if not pl:
            pl = Playlist(id="smart_favorites", name="Favorites")
            self.cache.playlists["smart_favorites"] = pl
        
        if favorited:
            if track_path not in pl.track_paths:
                pl.track_paths.append(track_path)
                self.cache.save()
                self.playlists_changed.emit("smart_favorites")
        else:
            if track_path in pl.track_paths:
                pl.track_paths.remove(track_path)
                self.cache.save()
                self.playlists_changed.emit("smart_favorites")
