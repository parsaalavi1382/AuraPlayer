"""
Genres tab: Genre Name | Number of Tracks.
Clicking a genre navigates to that Genre Page (built in Step 5).
"""

from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal, QAbstractTableModel, QModelIndex
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QTableView, QStackedWidget, QHeaderView, QAbstractItemView,
)

from core.library_store import LibraryStore
from ui.widgets.empty_state import EmptyStateWidget


class _GenresTableModel(QAbstractTableModel):
    """Thin table wrapper so we can show two columns (Name, Track Count) in a QTableView."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._genres: list[tuple[str, int]] = []

    def set_genres(self, genres: list[tuple[str, int]]) -> None:
        self.beginResetModel()
        self._genres = list(genres)
        self.endResetModel()

    def genre_at(self, row: int) -> tuple[str, int] | None:
        if 0 <= row < len(self._genres):
            return self._genres[row]
        return None

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self._genres)

    def columnCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else 2

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):
        if orientation == Qt.Orientation.Horizontal and role == Qt.ItemDataRole.DisplayRole:
            return ["Genre", "Tracks"][section]
        return None

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None
        genre_info = self.genre_at(index.row())
        if genre_info is None:
            return None
        name, count = genre_info
        if role == Qt.ItemDataRole.DisplayRole:
            return name if index.column() == 0 else str(count)
        return None


class GenresView(QWidget):
    genre_selected = pyqtSignal(str)  # genre name

    def __init__(self, store: LibraryStore, parent=None):
        super().__init__(parent)
        self.store = store

        outer = QVBoxLayout(self)
        outer.setContentsMargins(16, 12, 16, 0)

        self.stack = QStackedWidget()
        outer.addWidget(self.stack)

        self.empty_widget = EmptyStateWidget(
            title="No genres yet.",
            subtitle="Add a music folder in Settings to see genres here.",
        )
        self.stack.addWidget(self.empty_widget)

        self.table_model = _GenresTableModel(self)

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
        
        counts = {}
        for t in tracks:
            if t.genre:
                genres = [g.strip() for g in t.genre.split(",") if g.strip()]
                for g in genres:
                    # Normalize to Title Case so we don't duplicate e.g. "rock" and "Rock"
                    name = g.title()
                    counts[name] = counts.get(name, 0) + 1
            else:
                counts["Unknown Genre"] = counts.get("Unknown Genre", 0) + 1

        sorted_genres = sorted(counts.items(), key=lambda x: x[0].lower())
        self.table_model.set_genres(sorted_genres)

    def _on_tracks_changed(self, *_args) -> None:
        self.refresh()

    def _on_double_clicked(self, index) -> None:
        genre_info = self.table_model.genre_at(index.row())
        if genre_info:
            self.genre_selected.emit(genre_info[0])
