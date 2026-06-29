"""
Artists tab: Artist Name | Number of Tracks, per spec.
Clicking an artist navigates to that Artist Page (built in Step 5).
"""

from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QTableView, QStackedWidget, QHeaderView, QAbstractItemView,
)

from core.library_store import LibraryStore
from ui.models.library_group_models import ArtistsListModel
from ui.widgets.empty_state import EmptyStateWidget
from PyQt6.QtCore import QAbstractTableModel, QModelIndex


class _ArtistsTableModel(QAbstractTableModel):
    """Thin table wrapper around ArtistsListModel data so we can show
    two columns (Name, Track Count) in a QTableView, matching the spec's
    table layout rather than a plain list.
    """

    def __init__(self, base_model: ArtistsListModel, parent=None):
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
        return 0 if parent.isValid() else 2

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):
        if orientation == Qt.Orientation.Horizontal and role == Qt.ItemDataRole.DisplayRole:
            return ["Artist Name", "Tracks"][section]
        return None

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None
        artist = self.base_model.artist_at(index.row())
        if artist is None:
            return None
        if role == Qt.ItemDataRole.DisplayRole:
            return artist.name if index.column() == 0 else str(artist.track_count)
        if role == Qt.ItemDataRole.UserRole:
            return artist
        return None


class ArtistsView(QWidget):
    artist_selected = pyqtSignal(str)  # artist name

    def __init__(self, store: LibraryStore, parent=None):
        super().__init__(parent)
        self.store = store

        outer = QVBoxLayout(self)
        outer.setContentsMargins(16, 12, 16, 0)

        self.stack = QStackedWidget()
        outer.addWidget(self.stack)

        self.empty_widget = EmptyStateWidget(
            title="No artists yet.",
            subtitle="Add a music folder in Settings to see artists here.",
        )
        self.stack.addWidget(self.empty_widget)

        self.base_model = ArtistsListModel(self)
        self.table_model = _ArtistsTableModel(self.base_model, self)

        self.table = QTableView()
        self.table.setModel(self.table_model)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        self.table.setShowGrid(False)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
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
        artist = self.base_model.artist_at(index.row())
        if artist:
            self.artist_selected.emit(artist.name)
