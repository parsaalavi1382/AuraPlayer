"""
Artists tab: Artist Name | Number of Tracks, per spec.
Clicking an artist navigates to that Artist Page (built in Step 5).
"""

from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal, QAbstractTableModel, QModelIndex, QObject, QEvent
from PyQt6.QtGui import QCursor
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QTableView, QStackedWidget, QHeaderView, QAbstractItemView,
    QStyledItemDelegate, QStyleOptionViewItem, QStyle
)

from core.library_store import LibraryStore
from ui.models.library_group_models import ArtistsListModel
from ui.widgets.empty_state import EmptyStateWidget
from ui.widgets.adjacent_resize_helper import AdjacentResizeHelper
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
        self._sort_column = 0
        self._sort_ascending = True

    def _on_reset(self):
        self.beginResetModel()
        self.endResetModel()

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else self.base_model.rowCount()

    def columnCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else 2

    def sort_by_column(self, column: int, ascending: bool = True) -> None:
        self._sort_column = column
        self._sort_ascending = ascending
        self.base_model.sort_by_column(column, ascending)
        self.headerDataChanged.emit(Qt.Orientation.Horizontal, 0, 1)

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):
        if orientation == Qt.Orientation.Horizontal and role == Qt.ItemDataRole.DisplayRole:
            base_header = ["Artist Name", "Tracks"][section]
            if section == self._sort_column:
                arrow = "↑" if self._sort_ascending else "↓"
                return f"{arrow} {base_header}"
            return base_header
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
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.table.horizontalHeader().setStretchLastSection(False)
        self.table.setColumnWidth(0, 450)
        self.table.setColumnWidth(1, 100)
        self.resize_helper = AdjacentResizeHelper(self.table.horizontalHeader())
        
        self.delegate = SimpleRowHoverDelegate(self.table)
        self.table.setItemDelegate(self.delegate)
        self.table.setMouseTracking(True)
        self.hover_filter = SimpleRowHoverFilter(self.table, self.delegate)
        self.table.viewport().installEventFilter(self.hover_filter)
        
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
        self.base_model.set_tracks(tracks)
        
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
        artist = self.base_model.artist_at(index.row())
        if artist:
            self.artist_selected.emit(artist.name)


class SimpleRowHoverDelegate(QStyledItemDelegate):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.hovered_row = -1

    def paint(self, painter, option, index):
        opt = QStyleOptionViewItem(option)
        self.initStyleOption(opt, index)
        if index.row() == self.hovered_row:
            opt.state |= QStyle.StateFlag.State_MouseOver
        else:
            opt.state &= ~QStyle.StateFlag.State_MouseOver
        super().paint(painter, opt, index)


class SimpleRowHoverFilter(QObject):
    def __init__(self, table, delegate):
        super().__init__(table)
        self.table = table
        self.delegate = delegate
        self.table.verticalScrollBar().valueChanged.connect(self._on_scroll)
        
    def _on_scroll(self):
        try:
            if not self.table or self.table.isHidden():
                return
            pos = self.table.viewport().mapFromGlobal(QCursor.pos())
            self._update_hover(pos)
        except RuntimeError:
            pass
            
    def _update_hover(self, pos):
        index = self.table.indexAt(pos)
        if index.isValid():
            self.delegate.hovered_row = index.row()
            self.table.setCursor(Qt.CursorShape.ArrowCursor)
        else:
            self.delegate.hovered_row = -1
            self.table.setCursor(Qt.CursorShape.ArrowCursor)
        if self.table and self.table.viewport():
            self.table.viewport().update()

    def eventFilter(self, obj, event):
        try:
            if not self.table or self.table.isHidden():
                return False
            _ = self.table.viewport()
        except RuntimeError:
            return False

        if event.type() == QEvent.Type.MouseMove:
            self._update_hover(event.position().toPoint())
        elif event.type() == QEvent.Type.Leave:
            self.delegate.hovered_row = -1
            if self.table and self.table.viewport():
                self.table.viewport().update()
                
        return super().eventFilter(obj, event)
