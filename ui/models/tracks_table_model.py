"""
Qt table model backing the Tracks view (and reused, with a different
column set, by the Album page's track list in a later step).

Why a QAbstractTableModel instead of building widgets per row:
QTableView with a model only ever materializes the rows currently
visible on screen (plus a small buffer). A library of 50,000 tracks
costs the same to display as one of 50 -- Qt recycles row widgets as
you scroll. Building one QWidget per track row, by contrast, means
constructing tens of thousands of widgets up front, which is the
single most common reason naive PyQt music-library apps freeze on
startup. This is the "design for any library size" requirement from
the brief, made concrete.
"""

from __future__ import annotations

from PyQt6.QtCore import Qt, QAbstractTableModel, QModelIndex

from core.models import Track

COL_TITLE = 0
COL_ARTISTS = 1
COL_ALBUM = 2
COL_GENRE = 3
COL_DURATION = 4
COLUMN_HEADERS = ["Title", "Artist(s)", "Album", "Genre", "Duration"]


def format_duration(seconds: float) -> str:
    if seconds <= 0:
        return "--:--"
    m, s = divmod(int(seconds), 60)
    return f"{m}:{s:02d}"


class TracksTableModel(QAbstractTableModel):
    """
    Sorting note: we keep our own `_tracks` list in the order we want
    displayed, and re-sort it in place on sort_by_*() calls, rather than
    using Qt's QSortFilterProxyModel. For this model's size and access
    pattern a direct re-sort is simpler to reason about and just as fast
    in practice; a proxy model becomes worth it later if we need
    simultaneous independent sort+filter (e.g. search) layered on top --
    which Step 9 will likely introduce.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._tracks: list[Track] = []
        self._currently_playing_path: str | None = None
        # Theme-aware -- MainWindow updates this via set_danger_color()
        # whenever the active theme changes, so missing-file rows always
        # use the current theme's danger color instead of one baked in
        # at import time.
        self._danger_color = "#E05C5C"

    def set_danger_color(self, hex_color: str) -> None:
        if hex_color == self._danger_color:
            return
        self._danger_color = hex_color
        # Repaint any currently-missing rows so the new color shows
        # immediately, without a full model reset.
        for row, t in enumerate(self._tracks):
            if t.file_missing:
                self.dataChanged.emit(
                    self.index(row, 0), self.index(row, self.columnCount() - 1)
                )

    # ---------- Qt model interface ----------

    def rowCount(self, parent=QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self._tracks)

    def columnCount(self, parent=QModelIndex()) -> int:
        return 0 if parent.isValid() else len(COLUMN_HEADERS)

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):
        if orientation == Qt.Orientation.Horizontal and role == Qt.ItemDataRole.DisplayRole:
            return COLUMN_HEADERS[section]
        return None

    def data(self, index: QModelIndex, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None
        track = self._tracks[index.row()]
        col = index.column()

        if role == Qt.ItemDataRole.DisplayRole:
            if col == COL_TITLE:
                return track.title
            if col == COL_ARTISTS:
                return ", ".join(track.artists)
            if col == COL_ALBUM:
                return track.album
            if col == COL_GENRE:
                return track.genre or "—"
            if col == COL_DURATION:
                return format_duration(track.duration)

        if role == Qt.ItemDataRole.UserRole:
            # Used by delegates/click-handlers to get the full Track object
            # without re-deriving it from displayed strings.
            return track

        if role == Qt.ItemDataRole.ForegroundRole and track.file_missing:
            from PyQt6.QtGui import QColor
            return QColor(self._danger_color)

        return None

    # ---------- Data loading / refresh ----------

    def set_tracks(self, tracks: list[Track]) -> None:
        """Full reset -- used on initial load and major library changes."""
        self.beginResetModel()
        self._tracks = list(tracks)
        self.endResetModel()

    def upsert_tracks(self, tracks: list[Track]) -> None:
        """Incremental add/update -- avoids a full reset (and the
        scroll-position jump that comes with it) for routine additions
        such as a folder scan finding a few new files.
        """
        path_to_row = {t.path: i for i, t in enumerate(self._tracks)}
        new_tracks = []
        for t in tracks:
            if t.path in path_to_row:
                row = path_to_row[t.path]
                self._tracks[row] = t
                self.dataChanged.emit(
                    self.index(row, 0), self.index(row, self.columnCount() - 1)
                )
            else:
                new_tracks.append(t)

        if new_tracks:
            start = len(self._tracks)
            self.beginInsertRows(QModelIndex(), start, start + len(new_tracks) - 1)
            self._tracks.extend(new_tracks)
            self.endInsertRows()

    def remove_track_by_path(self, path: str) -> None:
        for row, t in enumerate(self._tracks):
            if t.path == path:
                self.beginRemoveRows(QModelIndex(), row, row)
                del self._tracks[row]
                self.endRemoveRows()
                return

    def track_at(self, row: int) -> Track | None:
        if 0 <= row < len(self._tracks):
            return self._tracks[row]
        return None

    def set_currently_playing(self, path: str | None) -> None:
        """Updates which row shows the now-playing visualiser. Only the
        old and new rows are repainted, not the whole table.
        """
        old_path = self._currently_playing_path
        self._currently_playing_path = path
        for row, t in enumerate(self._tracks):
            if t.path in (old_path, path):
                self.dataChanged.emit(self.index(row, 0), self.index(row, 0))

    def is_playing_row(self, row: int) -> bool:
        t = self.track_at(row)
        return bool(t and t.path == self._currently_playing_path)

    # ---------- Sorting (default: Title A-Z, per spec) ----------

    def sort_alphabetical(self, column: int = COL_TITLE) -> None:
        self.layoutAboutToBeChanged.emit()
        key_fn = {
            COL_TITLE: lambda t: (t.title or "").lower(),
            COL_ARTISTS: lambda t: ", ".join(t.artists).lower(),
            COL_ALBUM: lambda t: (t.album or "").lower(),
            COL_GENRE: lambda t: (t.genre or "").lower(),
            COL_DURATION: lambda t: t.duration or 0,
        }[column]
        self._tracks.sort(key=key_fn)
        self.layoutChanged.emit()
