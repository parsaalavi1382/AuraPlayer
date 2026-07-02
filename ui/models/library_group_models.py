"""
Models backing the Albums and Artists tabs.

Both are derived views over the same track list -- an "album" or
"artist" isn't a row in the JSON cache, it's a grouping computed from
tracks. We recompute the grouping whenever tracks change (add/remove/
edit) rather than maintaining a separate denormalized cache of albums/
artists; at any realistic library size this recompute is fast (a single
pass over all tracks), and it guarantees the grouping can never drift
out of sync with the underlying track data -- which a hand-maintained
duplicate would risk every time a track's album or artist field changes.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from PyQt6.QtCore import Qt, QAbstractListModel, QModelIndex

from core.models import Track


@dataclass
class AlbumGroup:
    album_key: str
    album_name: str
    album_artists: list[str]
    year: str
    tracks: list[Track] = field(default_factory=list)

    @property
    def total_duration(self) -> float:
        return sum(t.duration for t in self.tracks)

    @property
    def genres(self) -> list[str]:
        seen = set()
        res = []
        for t in self.tracks:
            if t.genre:
                for g in t.genre.split(","):
                    g_strip = g.strip()
                    if g_strip and g_strip.lower() not in seen:
                        seen.add(g_strip.lower())
                        res.append(g_strip)
        return res

    @property
    def has_art(self) -> bool:
        return any(t.has_embedded_art for t in self.tracks)


@dataclass
class ArtistGroup:
    name: str
    tracks: list[Track] = field(default_factory=list)  # tracks where this artist is a contributor

    @property
    def track_count(self) -> int:
        return len(self.tracks)


def build_album_groups(tracks: list[Track]) -> list[AlbumGroup]:
    groups: dict[str, AlbumGroup] = {}
    for t in tracks:
        key = t.album_key
        if key not in groups:
            groups[key] = AlbumGroup(
                album_key=key,
                album_name=t.album,
                album_artists=t.album_artists,
                year=t.year,
            )
        groups[key].tracks.append(t)
    return list(groups.values())


def build_artist_groups(tracks: list[Track]) -> list[ArtistGroup]:
    """An artist's track count includes every track they contributed to
    (matches the Artist Page spec: main tracks + "Appears On" features
    both count toward this artist's presence in the library).
    """
    groups: dict[str, ArtistGroup] = {}
    for t in tracks:
        for artist_name in t.artists:
            if artist_name not in groups:
                groups[artist_name] = ArtistGroup(name=artist_name)
            groups[artist_name].tracks.append(t)
    return list(groups.values())


class AlbumsListModel(QAbstractListModel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._albums: list[AlbumGroup] = []

    def rowCount(self, parent=QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self._albums)

    def data(self, index: QModelIndex, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None
        album = self._albums[index.row()]
        if role == Qt.ItemDataRole.DisplayRole:
            return album.album_name
        if role == Qt.ItemDataRole.UserRole:
            return album
        return None

    def set_tracks(self, tracks: list[Track]) -> None:
        self.beginResetModel()
        self._albums = build_album_groups(tracks)
        self.endResetModel()

    def album_at(self, row: int) -> AlbumGroup | None:
        if 0 <= row < len(self._albums):
            return self._albums[row]
        return None

    def sort_alphabetical(self) -> None:
        self.layoutAboutToBeChanged.emit()
        self._albums.sort(key=lambda a: a.album_name.lower())
        self.layoutChanged.emit()


class ArtistsListModel(QAbstractListModel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._artists: list[ArtistGroup] = []

    def rowCount(self, parent=QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self._artists)

    def data(self, index: QModelIndex, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None
        artist = self._artists[index.row()]
        if role == Qt.ItemDataRole.DisplayRole:
            return artist.name
        if role == Qt.ItemDataRole.UserRole:
            return artist
        return None

    def set_tracks(self, tracks: list[Track]) -> None:
        self.beginResetModel()
        self._artists = build_artist_groups(tracks)
        self.endResetModel()

    def artist_at(self, row: int) -> ArtistGroup | None:
        if 0 <= row < len(self._artists):
            return self._artists[row]
        return None

    def sort_alphabetical(self) -> None:
        self.layoutAboutToBeChanged.emit()
        self._artists.sort(key=lambda a: a.name.lower())
        self.layoutChanged.emit()
