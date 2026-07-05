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
from ui.widgets.adjacent_resize_helper import AdjacentResizeHelper


class _GenresTableModel(QAbstractTableModel):
    """Thin table wrapper so we can show two columns (Name, Track Count) in a QTableView."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._genres: list[tuple[str, int]] = []
        self._sort_column = 0
        self._sort_ascending = True

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

    def sort_by_column(self, column: int, ascending: bool = True) -> None:
        self.layoutAboutToBeChanged.emit()
        self._sort_column = column
        self._sort_ascending = ascending
        if column == 0:
            self._genres.sort(key=lambda x: x[0].lower(), reverse=not ascending)
        elif column == 1:
            self._genres.sort(key=lambda x: x[1], reverse=not ascending)
        self.layoutChanged.emit()
        self.headerDataChanged.emit(Qt.Orientation.Horizontal, 0, 1)

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):
        if orientation == Qt.Orientation.Horizontal and role == Qt.ItemDataRole.DisplayRole:
            base_header = ["Genre", "Tracks"][section]
            if section == self._sort_column:
                arrow = "↑" if self._sort_ascending else "↓"
                return f"{arrow} {base_header}"
            return base_header
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
        self.table.setShowGrid(True)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.table.horizontalHeader().setStretchLastSection(False)
        self.table.setColumnWidth(0, 450)
        self.table.setColumnWidth(1, 100)
        self.resize_helper = AdjacentResizeHelper(self.table.horizontalHeader())
        self.table.horizontalHeader().sectionClicked.connect(self._on_header_clicked)
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
        
        sort_col = getattr(self.table_model, "_sort_column", 0)
        sort_asc = getattr(self.table_model, "_sort_ascending", True)
        self.table_model.sort_by_column(sort_col, sort_asc)

    def _on_tracks_changed(self, *_args) -> None:
        self.refresh()

    def _on_header_clicked(self, index: int) -> None:
        if self.table_model._sort_column == index:
            new_asc = not self.table_model._sort_ascending
        else:
            new_asc = True
        self.table_model.sort_by_column(index, new_asc)

    def _on_double_clicked(self, index) -> None:
        genre_info = self.table_model.genre_at(index.row())
        if genre_info:
            self.genre_selected.emit(genre_info[0])
