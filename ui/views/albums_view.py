"""
Albums tab: Album Cover | Album Name | Artists | Duration | Year, per spec.
Clicking an album navigates to that Album Page (built in Step 5).

Album cover thumbnails are deferred to Step 5 alongside the Album Page,
since both need the same embedded-art loading path -- building it twice
(once here in a simplified form, once properly later) would mean
throwing away work. The column is reserved in the layout so the table
shape won't need to change later.
"""

from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal, QAbstractTableModel, QModelIndex
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QTableView, QStackedWidget, QHeaderView, QAbstractItemView,
)

from core.library_store import LibraryStore
from ui.models.library_group_models import AlbumsListModel
from ui.models.tracks_table_model import format_duration
from ui.widgets.empty_state import EmptyStateWidget


class _AlbumsTableModel(QAbstractTableModel):
    COLUMNS = ["Album Name", "Artists", "Duration", "Year"]

    def __init__(self, base_model: AlbumsListModel, parent=None):
        super().__init__(parent)
        self.base_model = base_model
        self.base_model.modelReset.connect(self._on_reset)
        self.base_model.layoutChanged.connect(self._on_reset)

    def _on_reset(self):
        self.beginResetModel()
        self.endResetModel()

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else self.base_model.rowCount()

    def columnCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self.COLUMNS)

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):
        if orientation == Qt.Orientation.Horizontal and role == Qt.ItemDataRole.DisplayRole:
            return self.COLUMNS[section]
        return None

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None
        album = self.base_model.album_at(index.row())
        if album is None:
            return None
        if role == Qt.ItemDataRole.DisplayRole:
            col = index.column()
            if col == 0:
                return album.album_name
            if col == 1:
                return ", ".join(album.album_artists)
            if col == 2:
                return format_duration(album.total_duration)
            if col == 3:
                return album.year or "—"
        if role == Qt.ItemDataRole.UserRole:
            return album
        return None


class AlbumsView(QWidget):
    album_selected = pyqtSignal(str)  # album_key

    def __init__(self, store: LibraryStore, parent=None):
        super().__init__(parent)
        self.store = store

        outer = QVBoxLayout(self)
        outer.setContentsMargins(16, 12, 16, 0)

        self.stack = QStackedWidget()
        outer.addWidget(self.stack)

        self.empty_widget = EmptyStateWidget(
            title="No albums yet.",
            subtitle="Add a music folder in Settings to see albums here.",
        )
        self.stack.addWidget(self.empty_widget)

        self.base_model = AlbumsListModel(self)
        self.table_model = _AlbumsTableModel(self.base_model, self)

        self.table = QTableView()
        self.table.setModel(self.table_model)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        self.table.setShowGrid(False)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        self.table.doubleClicked.connect(self._on_double_clicked)
        self.stack.addWidget(self.table)

        self.store.tracks_added.connect(self._on_tracks_changed)
        self.store.track_removed.connect(self._on_tracks_changed)
        self.store.track_updated.connect(self._on_tracks_changed)

        self.refresh()

    def refresh(self) -> None:
        tracks = self.store.all_tracks()
        if not tracks:
            self.stack.setCurrentWidget(self.empty_widget)
            return
        self.stack.setCurrentWidget(self.table)
        self.base_model.set_tracks(tracks)
        self.base_model.sort_alphabetical()

    def _on_tracks_changed(self, *_args) -> None:
        self.refresh()

    def _on_double_clicked(self, index) -> None:
        album = self.base_model.album_at(index.row())
        if album:
            self.album_selected.emit(album.album_key)
