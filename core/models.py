"""
Data models for the music library.

These are plain dataclasses that mirror the JSON cache structure exactly.
Keeping them as dataclasses (rather than raw dicts) gives us type safety
and autocomplete everywhere else in the app, while to_dict()/from_dict()
keep serialization trivial and explicit.
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Optional


# Supported audio formats. Extending this list is the only change needed
# to support a new format at the scanning level (writing support depends
# on mutagen's per-format capabilities, handled in metadata_writer.py).
SUPPORTED_EXTENSIONS = {".mp3", ".flac", ".m4a", ".wav", ".ogg"}


@dataclass
class Track:
    """A single audio file and its metadata."""

    path: str                      # Absolute file path. Used as unique ID.
    title: str = "Unknown Title"
    artists: list[str] = field(default_factory=lambda: ["Unknown Artist"])
    album: str = "Unknown Album"
    album_artists: list[str] = field(default_factory=lambda: ["Unknown Artist"])
    year: str = ""
    genre: str = ""
    duration: float = 0.0          # seconds
    disc_number: int = 0           # 0 = untagged, sorts first per spec
    track_number: Optional[int] = None  # None = show blank/dash in UI
    has_embedded_art: bool = False
    source_folder: str = ""        # which added folder this came from
    file_missing: bool = False     # set at scan/refresh time if path vanished
    lyrics_source: Optional[str] = None  # "lrc" | "embedded" | "manual" | None

    def to_dict(self) -> dict:
        return asdict(self)

    @staticmethod
    def from_dict(d: dict) -> "Track":
        # Filter unknown keys defensively so old cache files don't crash
        # on load if we add fields in later steps.
        known = {f for f in Track.__dataclass_fields__}
        return Track(**{k: v for k, v in d.items() if k in known})

    @property
    def album_key(self) -> str:
        """Group key for albums: album name + primary album artist.

        Using album name alone would merge unrelated 'Greatest Hits'
        albums from different artists into one. Album artist is the
        first entry in album_artists (or artists, if album_artists
        wasn't tagged).
        """
        primary_artist = (self.album_artists or self.artists or ["Unknown Artist"])[0]
        return f"{self.album}::{primary_artist}"


@dataclass
class Playlist:
    """A user-created ordered collection of track paths."""

    id: str
    name: str
    cover_path: Optional[str] = None   # user-selected image, not from a track
    track_paths: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)

    @staticmethod
    def from_dict(d: dict) -> "Playlist":
        known = {f for f in Playlist.__dataclass_fields__}
        return Playlist(**{k: v for k, v in d.items() if k in known})


@dataclass
class PlayerState:
    """Persisted playback state, restored on app restart.

    Invariant: `queue` must never contain the same track path twice.
    "Play Next" and "Add to Queue" both enforce this by moving an
    already-queued track to its new position instead of inserting a
    second copy -- see PlaybackEngine.play_next() / add_to_queue().
    """

    current_track_path: Optional[str] = None
    position_seconds: float = 0.0
    queue: list[str] = field(default_factory=list)
    queue_index: int = -1
    repeat_mode: str = "off"       # "off" | "all" | "one"
    shuffle: bool = False
    volume: float = 0.7
    # QAudioDevice.id() as a string (it's a QByteArray natively) -- empty
    # string means "use the system default output", since device IDs
    # aren't guaranteed stable across reboots/driver changes and we'd
    # rather silently fall back to default than fail to play audio.
    output_device_id: str = ""

    def to_dict(self) -> dict:
        return asdict(self)

    @staticmethod
    def from_dict(d: dict) -> "PlayerState":
        known = {f for f in PlayerState.__dataclass_fields__}
        return PlayerState(**{k: v for k, v in d.items() if k in known})


@dataclass
class Settings:
    """User-configurable settings.

    artist_separators holds every separator the user knows about (default
    five plus any custom ones they've added), in display order.
    disabled_separators holds the subset that's currently unchecked --
    kept as its own list (rather than just deleting from
    artist_separators) so unchecking a separator doesn't make the user
    retype it later if they re-check it.
    """

    music_folders: list[str] = field(default_factory=list)
    artist_separators: list[str] = field(
        default_factory=lambda: [",", "&", "/", "feat.", ";"]
    )
    disabled_separators: list[str] = field(default_factory=list)
    theme: str = "dark"
    column_widths: dict[str, list[int]] = field(default_factory=dict)

    def active_separators(self) -> list[str]:
        """The separators actually used for splitting -- all known
        separators minus the disabled ones. This is what the scanner/
        metadata reader should call, never `artist_separators` directly.
        """
        return [s for s in self.artist_separators if s not in self.disabled_separators]

    def to_dict(self) -> dict:
        return asdict(self)

    @staticmethod
    def from_dict(d: dict) -> "Settings":
        known = {f for f in Settings.__dataclass_fields__}
        return Settings(**{k: v for k, v in d.items() if k in known})
