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

Album art extraction (get_album_art) is a SEPARATE read path from
read_track_metadata() -- the scan path only needs has_embedded_art (a
bool) for speed across a whole library, while the Player Screen needs
the actual decoded image for exactly one track at a time. Keeping these
separate means a full-library scan never has to decode and discard
artwork bytes for thousands of files it isn't displaying.
"""

from __future__ import annotations

import os
from typing import Optional

from mutagen import File as MutagenFile
from mutagen.mp4 import MP4
from mutagen.id3 import ID3
from mutagen.flac import FLAC
from mutagen.oggvorbis import OggVorbis

from PyQt6.QtGui import QPixmap, QPainter, QPainterPath
from PyQt6.QtCore import Qt, QRectF

from core.models import Track
from utils.artist_parser import split_artists

# Player Screen album art is rendered at a fixed max size -- larger
# embedded art (some files ship 3000x3000 covers) is downscaled once
# here rather than asking every call site to remember to do it, and
# rounded corners are applied globally so every place that calls
# get_album_art() gets consistent visual treatment for free.
MAX_ARTWORK_SIZE = 300
ARTWORK_CORNER_RADIUS = 12


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


# ============================================================
# Album art extraction (Step 4 -- Player Screen)
# ============================================================

def _extract_raw_art_bytes(filepath: str) -> Optional[bytes]:
    """Per-format raw image byte extraction. Returns None if the file
    has no embedded art, is unreadable, or the format isn't one we
    extract art from (e.g. WAV practically never carries embedded art
    in the wild, so it's not specially handled -- MutagenFile's generic
    path below will simply find nothing for it, which is correct).
    """
    ext = os.path.splitext(filepath)[1].lower()

    try:
        if ext == ".mp3":
            tags = ID3(filepath)
            for key in tags.keys():
                if key.startswith("APIC"):
                    return tags[key].data
            return None

        if ext == ".flac":
            audio = FLAC(filepath)
            if audio.pictures:
                return audio.pictures[0].data
            return None

        if ext == ".m4a":
            audio = MP4(filepath)
            covr = (audio.tags or {}).get("covr")
            if covr:
                return bytes(covr[0])
            return None

        if ext == ".ogg":
            audio = OggVorbis(filepath)
            pics = audio.get("metadata_block_picture")
            if not pics:
                return None
            import base64
            from mutagen.flac import Picture
            picture = Picture(base64.b64decode(pics[0]))
            return picture.data

    except Exception:
        # Corrupt/partial art data should never crash the Player Screen --
        # just behave as if there's no art for this track.
        return None

    return None


_raw_album_art_cache: dict[str, Optional[QPixmap]] = {}
_album_art_cache: dict[str, Optional[QPixmap]] = {}
_album_key_art_cache: dict[str, Optional[QPixmap]] = {}


def get_raw_album_art(filepath: str) -> Optional[QPixmap]:
    """Extracts and decodes the 100% original full-resolution QPixmap
    from the audio file's embedded artwork bytes without any quality loss.
    """
    if filepath in _raw_album_art_cache:
        return _raw_album_art_cache[filepath]

    raw_bytes = _extract_raw_art_bytes(filepath)
    if not raw_bytes:
        _raw_album_art_cache[filepath] = None
        return None

    source = QPixmap()
    if not source.loadFromData(raw_bytes):
        _raw_album_art_cache[filepath] = None
        return None

    _raw_album_art_cache[filepath] = source
    return source


def render_artwork(
    source: QPixmap,
    target_size: int,
    dpr: float = 1.0,
    corner_radius: float = 0.0,
    is_circle: bool = False,
) -> QPixmap:
    """Renders a raw QPixmap at exact target size scaled by the device pixel ratio (dpr),
    using smooth transformation and antialiased clip paths for pin-sharp High-DPI display.
    """
    if not source or source.isNull():
        return source

    render_size = max(16, int(target_size * max(1.0, dpr)))

    # Center-crop & scale from 100% original full resolution smoothly
    scaled = source.scaled(
        render_size,
        render_size,
        Qt.AspectRatioMode.KeepAspectRatioByExpanding,
        Qt.TransformationMode.SmoothTransformation,
    )

    if scaled.width() != render_size or scaled.height() != render_size:
        x = max(0, (scaled.width() - render_size) // 2)
        y = max(0, (scaled.height() - render_size) // 2)
        scaled = scaled.copy(x, y, render_size, render_size)

    output = QPixmap(render_size, render_size)
    output.fill(Qt.GlobalColor.transparent)

    painter = QPainter(output)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)

    path = QPainterPath()
    if is_circle:
        path.addEllipse(QRectF(0, 0, render_size, render_size))
    elif corner_radius > 0:
        scaled_radius = corner_radius * (render_size / max(1, target_size))
        path.addRoundedRect(
            QRectF(0, 0, render_size, render_size),
            scaled_radius,
            scaled_radius,
        )
    else:
        path.addRect(QRectF(0, 0, render_size, render_size))

    painter.setClipPath(path)
    painter.drawPixmap(0, 0, scaled)
    painter.end()

    return output


def get_album_art(
    filepath: str,
    target_size: int = 400,
    dpr: float = 1.0,
    corner_radius: float = 12.0,
) -> Optional[QPixmap]:
    """Returns a high-resolution, High-DPI rendered QPixmap of the track's embedded
    album art, scaled smoothly from original full resolution.
    """
    cache_key = f"{filepath}_{target_size}_{dpr}_{corner_radius}"
    if cache_key in _album_art_cache:
        return _album_art_cache[cache_key]

    raw_source = get_raw_album_art(filepath)
    if not raw_source or raw_source.isNull():
        _album_art_cache[cache_key] = None
        return None

    rendered = render_artwork(
        raw_source,
        target_size=target_size,
        dpr=dpr,
        corner_radius=corner_radius,
    )
    _album_art_cache[cache_key] = rendered
    return rendered


def clear_album_art_cache(filepath: Optional[str] = None, album_key: Optional[str] = None) -> None:
    """Clear cached pixmaps when metadata/cover art is modified."""
    if filepath:
        if filepath in _raw_album_art_cache:
            del _raw_album_art_cache[filepath]
        keys_to_del = [k for k in _album_art_cache.keys() if k.startswith(filepath)]
        for k in keys_to_del:
            del _album_art_cache[k]
    if album_key and album_key in _album_key_art_cache:
        del _album_key_art_cache[album_key]
    if not filepath and not album_key:
        _raw_album_art_cache.clear()
        _album_art_cache.clear()
        _album_key_art_cache.clear()


def get_track_album_art(
    track: Optional[Track],
    store: Optional[object] = None,
    target_size: int = 400,
    dpr: float = 1.0,
    corner_radius: float = 12.0,
) -> Optional[QPixmap]:
    """
    Returns the album art QPixmap for a track.
    If tracks belong to the same album, they share the exact same album cover
    (prioritizing the cover art from the first song in that album that has art).
    """
    if not track:
        return None

    album_key = getattr(track, "album_key", None)

    # Direct extraction for this track
    direct_art = get_album_art(track.path, target_size=target_size, dpr=dpr, corner_radius=corner_radius)
    if direct_art is not None:
        return direct_art

    # If this track has no embedded art, look up other tracks in the same album (prioritizing first track with art)
    if store and album_key:
        album_obj = store.get_album_by_key(album_key)
        if album_obj and hasattr(album_obj, "tracks"):
            for t in album_obj.tracks:
                if t.path == track.path:
                    continue
                art = get_album_art(t.path, target_size=target_size, dpr=dpr, corner_radius=corner_radius)
                if art is not None:
                    return art

    return None
