"""
Scans user-selected music folders for supported audio files and
populates the LibraryCache with their metadata.

Designed to be driven from a background thread later (Step 2/3 UI):
`progress_callback(current_index, total_count, current_filename)` is
called after each file so a UI can show a progress bar without this
module knowing anything about Qt.
"""

from __future__ import annotations

import os
from typing import Callable, Optional

from core.library_cache import LibraryCache
from core.metadata_reader import read_track_metadata
from core.models import SUPPORTED_EXTENSIONS

ProgressCallback = Callable[[int, int, str], None]


def find_audio_files(folder: str) -> list[str]:
    """Recursively find all supported audio files under a folder."""
    results = []
    for root, _dirs, files in os.walk(folder):
        for fname in files:
            ext = os.path.splitext(fname)[1].lower()
            if ext in SUPPORTED_EXTENSIONS:
                results.append(os.path.join(root, fname))
    return results


def scan_folders(
    cache: LibraryCache,
    folders: list[str],
    progress_callback: Optional[ProgressCallback] = None,
) -> dict:
    """
    Scan all given folders, add new tracks to the cache, skip files
    already present (dedup by path, per spec), and flag tracks whose
    file has disappeared since the last scan.

    Returns a summary dict: {"added": int, "skipped": int, "missing": list[str]}
    """
    all_files: list[str] = []
    folder_of: dict[str, str] = {}

    for folder in folders:
        if not os.path.isdir(folder):
            continue
        found = find_audio_files(folder)
        all_files.extend(found)
        for f in found:
            folder_of[f] = folder

    total = len(all_files)
    added = 0
    skipped = 0

    for idx, filepath in enumerate(all_files, start=1):
        if progress_callback:
            progress_callback(idx, total, os.path.basename(filepath))

        if cache.has_track(filepath):
            skipped += 1
            continue

        track = read_track_metadata(
            filepath,
            source_folder=folder_of[filepath],
            artist_separators=cache.settings.active_separators(),
        )
        cache.upsert_track(track)
        added += 1

    # Only check "missing" status for tracks belonging to folders we just
    # scanned -- a track from a folder the user hasn't added back yet
    # shouldn't be falsely flagged missing.
    scanned_folder_set = set(f for f in folders if os.path.isdir(f))
    existing_paths = set(all_files)
    missing = []
    for path, track in cache.tracks.items():
        if track.source_folder in scanned_folder_set and path not in existing_paths:
            if not track.file_missing:
                track.file_missing = True
                missing.append(path)
        elif path in existing_paths and track.file_missing:
            track.file_missing = False

    return {"added": added, "skipped": skipped, "missing": missing, "total_found": total}
