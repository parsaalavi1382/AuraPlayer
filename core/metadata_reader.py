"""
Reads metadata from audio files into our normalized Track model.

Different formats expose tags under different key schemes in mutagen:
  - MP3 (ID3):      TIT2, TPE1, TALB, TPE2, TDRC, TCON, TPOS, TRCK, APIC
  - FLAC/OGG:       Vorbis comments - lowercase keys: title, artist, album,
                    albumartist, date, genre, discnumber, tracknumber
  - M4A (MP4 atoms): \xa9nam, \xa9ART, \xa9alb, aART, \xa9day, \xa9gen,
                    disk, trkn

Rather than branch on file extension everywhere, we use mutagen.File()
to auto-detect the format, then pull tags through EasyID3-style or
native interfaces depending on what's available. mutagen.File(easy=True)
unifies MP3/FLAC/OGG under common lowercase keys, but MP4 needs its own
handling since "easy" mode doesn't fully normalize disc/track numbers
or album art there.
"""

from __future__ import annotations

import os
from typing import Optional

from mutagen import File as MutagenFile
from mutagen.mp4 import MP4

from core.models import Track
from utils.artist_parser import split_artists


def _first_or_default(value, default):
    """Mutagen 'easy' tags return lists like ['Artist Name']. Unwrap safely."""
    if not value:
        return default
    if isinstance(value, (list, tuple)):
        return value[0] if value else default
    return value


def _artist_list_or_default(value, default):
    """
    Artist-type tags (artist, albumartist) must NOT be collapsed to their
    first entry. Windows taggers commonly write multiple artists as
    separate list entries (e.g. ['Travis Scott', 'Future', '2 Chainz'])
    rather than one joined string -- collapsing to value[0] silently
    drops every artist after the first. Returns the full list (or the
    single string) unchanged, so split_artists() can handle both shapes.
    """
    if not value:
        return default
    if isinstance(value, (list, tuple)):
        return list(value) if value else default
    return value


def _parse_disc_or_track_number(raw: Optional[str]) -> tuple[int, Optional[int]]:
    """
    Disc/track numbers are often stored as 'N' or 'N/Total' (e.g. '2/12').
    Returns (number, total) as ints, with number defaulting per spec
    (caller decides default: 0 for disc, None for track).
    """
    if not raw:
        return None, None
    raw = str(raw)
    if "/" in raw:
        num_part, total_part = raw.split("/", 1)
    else:
        num_part, total_part = raw, None
    try:
        num = int(num_part.strip())
    except (ValueError, TypeError):
        num = None
    try:
        total = int(total_part.strip()) if total_part else None
    except (ValueError, TypeError):
        total = None
    return num, total


def _read_mp4_tags(filepath: str) -> dict:
    """MP4/M4A needs its own path: 'easy' mode mutagen doesn't expose
    disc/track numbers or album-art presence consistently for this format.
    """
    audio = MP4(filepath)
    tags = audio.tags or {}

    title = _first_or_default(tags.get("\xa9nam"), None)
    artist_raw = _artist_list_or_default(tags.get("\xa9ART"), None)
    album = _first_or_default(tags.get("\xa9alb"), None)
    album_artist_raw = _artist_list_or_default(tags.get("aART"), None)
    year = _first_or_default(tags.get("\xa9day"), "")
    genre = _first_or_default(tags.get("\xa9gen"), "")

    # disk/trkn are stored as a list of (number, total) tuples in MP4
    disc_number = 0
    track_number = None
    if "disk" in tags and tags["disk"]:
        disc_number = tags["disk"][0][0] or 0
    if "trkn" in tags and tags["trkn"]:
        track_number = tags["trkn"][0][0] or None

    has_art = bool(tags.get("covr"))

    return {
        "title": title,
        "artist_raw": artist_raw,
        "album": album,
        "album_artist_raw": album_artist_raw,
        "year": str(year) if year else "",
        "genre": genre,
        "disc_number": disc_number,
        "track_number": track_number,
        "has_embedded_art": has_art,
        "duration": audio.info.length if audio.info else 0.0,
    }


def _read_easy_tags(filepath: str) -> dict:
    """Handles MP3 (ID3), FLAC, OGG via mutagen's unified 'easy' interface."""
    audio = MutagenFile(filepath, easy=True)
    if audio is None:
        raise ValueError(f"mutagen could not parse: {filepath}")

    tags = audio.tags or {}

    title = _first_or_default(tags.get("title"), None)
    artist_raw = _artist_list_or_default(tags.get("artist"), None)
    album = _first_or_default(tags.get("album"), None)
    album_artist_raw = _artist_list_or_default(tags.get("albumartist"), None)
    year = _first_or_default(tags.get("date"), "")
    genre = _first_or_default(tags.get("genre"), "")
    disc_raw = _first_or_default(tags.get("discnumber"), None)
    track_raw = _first_or_default(tags.get("tracknumber"), None)

    disc_number, _ = _parse_disc_or_track_number(disc_raw)
    track_number, _ = _parse_disc_or_track_number(track_raw)

    # Embedded art check needs the non-easy interface for MP3 (APIC frames
    # aren't exposed via easy=True), and FLAC exposes audio.pictures directly.
    has_art = False
    ext = os.path.splitext(filepath)[1].lower()
    if ext == ".mp3":
        raw_audio = MutagenFile(filepath)
        has_art = any(k.startswith("APIC") for k in (raw_audio.tags or {}).keys())
    elif ext == ".flac":
        has_art = bool(getattr(audio, "pictures", None))
    elif ext == ".ogg":
        pics = tags.get("metadata_block_picture")
        has_art = bool(pics)

    return {
        "title": title,
        "artist_raw": artist_raw,
        "album": album,
        "album_artist_raw": album_artist_raw,
        "year": str(year) if year else "",
        "genre": genre,
        "disc_number": disc_number if disc_number is not None else 0,
        "track_number": track_number,
        "has_embedded_art": has_art,
        "duration": audio.info.length if audio.info else 0.0,
    }


def read_track_metadata(
    filepath: str, source_folder: str, artist_separators: list[str]
) -> Track:
    """
    Read a single audio file and return a normalized Track.

    Falls back to filename (without extension) as the title, and
    'Unknown Artist'/'Unknown Album' when tags are absent, so every
    scanned file produces a usable, displayable Track even when
    completely untagged.
    """
    ext = os.path.splitext(filepath)[1].lower()
    filename_stem = os.path.splitext(os.path.basename(filepath))[0]

    try:
        if ext == ".m4a":
            raw = _read_mp4_tags(filepath)
        else:
            raw = _read_easy_tags(filepath)
    except Exception as e:
        # A single unreadable/corrupt file should never abort a whole scan.
        # Return a minimal Track flagged via title so the user can see
        # something went wrong, rather than silently dropping the file.
        return Track(
            path=filepath,
            title=f"{filename_stem} (unreadable metadata)",
            artists=["Unknown Artist"],
            album="Unknown Album",
            album_artists=["Unknown Artist"],
            source_folder=source_folder,
        )

    title = raw["title"] or filename_stem
    artists = split_artists(raw["artist_raw"], artist_separators) if raw["artist_raw"] else ["Unknown Artist"]
    album = raw["album"] or "Unknown Album"
    if raw["album_artist_raw"]:
        album_artists = split_artists(raw["album_artist_raw"], artist_separators)
    else:
        album_artists = artists

    return Track(
        path=filepath,
        title=title,
        artists=artists,
        album=album,
        album_artists=album_artists,
        year=raw["year"],
        genre=raw["genre"],
        duration=raw["duration"] or 0.0,
        disc_number=raw["disc_number"] or 0,
        track_number=raw["track_number"],
        has_embedded_art=raw["has_embedded_art"],
        source_folder=source_folder,
    )
