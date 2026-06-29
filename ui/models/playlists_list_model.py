"""
Minimal model for the Playlists tab in Step 2. Full playlist management
(create, add/remove tracks, drag-reorder, cover image) is Step 7 per the
roadmap -- this just lets the tab exist and show real (empty) state
rather than a dummy placeholder, wired to the same LibraryStore signals
everything else uses.
"""

from __future__ import annotations

from PyQt6.QtCore import Qt, QAbstractListModel, QModelIndex

from core.models import Playlist


class PlaylistsListModel(QAbstractListModel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._playlists: list[Playlist] = []

    def rowCount(self, parent=QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self._playlists)

    def data(self, index: QModelIndex, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None
        playlist = self._playlists[index.row()]
        if role == Qt.ItemDataRole.DisplayRole:
            return playlist.name
        if role == Qt.ItemDataRole.UserRole:
            return playlist
        return None

    def set_playlists(self, playlists: list[Playlist]) -> None:
        self.beginResetModel()
        self._playlists = list(playlists)
        self.endResetModel()

    def playlist_at(self, row: int) -> Playlist | None:
        if 0 <= row < len(self._playlists):
            return self._playlists[row]
        return None

    def sort_alphabetical(self) -> None:
        self.layoutAboutToBeChanged.emit()
        self._playlists.sort(key=lambda p: p.name.lower())
        self.layoutChanged.emit()
