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

from PyQt6.QtCore import Qt, pyqtSignal, QAbstractTableModel, QModelIndex, QPoint, QRect, QEvent, QObject
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QTableView, QStackedWidget, QHeaderView, QAbstractItemView,
    QStyledItemDelegate, QStyleOptionViewItem, QStyle
)
from PyQt6.QtGui import QColor, QFont, QPainter, QPixmap

from core.library_store import LibraryStore
from core.metadata_reader import get_album_art
from ui.models.library_group_models import AlbumsListModel
from ui.models.tracks_table_model import format_duration
from ui.widgets.empty_state import EmptyStateWidget
from ui.theme import THEMES, DEFAULT_THEME
from ui.widgets.adjacent_resize_helper import AdjacentResizeHelper

COL_ALBUM_NAME = 0
COL_ALBUM_ARTISTS = 1
COL_ALBUM_DURATION = 3
COL_ALBUM_YEAR = 2


class AlbumHoverDelegate(QStyledItemDelegate):
    def __init__(self, table, view, parent=None):
        super().__init__(parent)
        self.table = table
        self.view = view
        self.mouse_pos = QPoint(-1, -1)
        self.hovered_row = -1

    def set_mouse_pos(self, pos: QPoint):
        self.mouse_pos = pos

    def clear_mouse_pos(self):
        self.mouse_pos = QPoint(-1, -1)

    def paint(self, painter, option, index):
        col = index.column()
        if col not in (COL_ALBUM_NAME, COL_ALBUM_ARTISTS):
            super().paint(painter, option, index)
            return

        # Prepare style option
        opt = QStyleOptionViewItem(option)
        self.initStyleOption(opt, index)
        opt.text = ""  # Clear text

        widget = option.widget
        style = widget.style() if widget else None
        if style:
            style.drawPrimitive(QStyle.PrimitiveElement.PE_PanelItemViewItem, opt, painter, widget)

        album = index.data(Qt.ItemDataRole.UserRole)
        if not album:
            super().paint(painter, option, index)
            return

        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        theme_key = self.view.store.cache.settings.theme
        theme = THEMES.get(theme_key, THEMES[DEFAULT_THEME])

        is_hovered = (index.row() == self.hovered_row)
        rect = option.rect.adjusted(6, 0, -6, 0)
        fm = option.fontMetrics
        y_baseline = rect.top() + (rect.height() + fm.ascent() - fm.descent()) // 2

        if option.state & QStyle.StateFlag.State_Selected:
            text_color = QColor(theme['text_primary'])
        else:
            text_color = QColor(theme['text_primary'])

        if col == COL_ALBUM_NAME:
            # Draw album cover art on the left
            cover_size = 28
            cover_rect = QRect(rect.left(), rect.top() + (rect.height() - cover_size) // 2, cover_size, cover_size)
            
            # Load art
            art_pixmap = None
            if album.tracks:
                art_pixmap = get_album_art(album.tracks[0].path)
                
            if art_pixmap and not art_pixmap.isNull():
                scaled = art_pixmap.scaled(
                    cover_size, cover_size,
                    Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                    Qt.TransformationMode.SmoothTransformation,
                )
                painter.drawPixmap(cover_rect, scaled)
            else:
                from ui.svg_icon import get_default_cover
                disc_px = get_default_cover(cover_size, theme, corner_radius=4.0)
                if disc_px and not disc_px.isNull():
                    painter.drawPixmap(cover_rect, disc_px)
                else:
                    painter.fillRect(cover_rect, QColor(theme.get("surface", "#1c1f26")))

            # Draw album name text on the right of the cover art
            text_rect_left = rect.left() + cover_size + 10
            album_name_text = album.album_name or "Unknown Album"
            elided_name = fm.elidedText(album_name_text, Qt.TextElideMode.ElideRight, rect.right() - text_rect_left)
            
            painter.setPen(text_color)
            painter.drawText(text_rect_left, y_baseline, elided_name)

        elif col == COL_ALBUM_ARTISTS:
            artists = album.album_artists
            x_offset = rect.left()
            for i, artist in enumerate(artists):
                artist_width = fm.horizontalAdvance(artist)
                artist_rect = QRect(x_offset, rect.top(), artist_width, rect.height())
                
                artist_hovered = is_hovered and rect.contains(self.mouse_pos) and artist_rect.contains(self.mouse_pos)
                
                font = painter.font()
                font.setUnderline(artist_hovered)
                painter.setFont(font)
                
                if artist_hovered and not (option.state & QStyle.StateFlag.State_Selected):
                    painter.setPen(QColor(theme['accent']))
                else:
                    painter.setPen(QColor(theme['text_secondary']) if not (option.state & QStyle.StateFlag.State_Selected) else text_color)
                    
                painter.drawText(x_offset, y_baseline, artist)
                x_offset += artist_width
                
                if i < len(artists) - 1:
                    comma = ", "
                    comma_width = fm.horizontalAdvance(comma)
                    font.setUnderline(False)
                    painter.setFont(font)
                    painter.setPen(QColor(theme['text_secondary']) if not (option.state & QStyle.StateFlag.State_Selected) else text_color)
                    painter.drawText(x_offset, y_baseline, comma)
                    x_offset += comma_width

        painter.restore()


class AlbumHoverEventFilter(QObject):
    def __init__(self, table, delegate, view):
        super().__init__(table)
        self.table = table
        self.delegate = delegate
        self.view = view

    def eventFilter(self, obj, event):
        try:
            if not self.table or self.table.isHidden():
                return False
            _ = self.table.viewport()
        except RuntimeError:
            return False

        if event.type() == QEvent.Type.MouseMove:
            pos = event.position().toPoint()
            self.delegate.set_mouse_pos(pos)

            index = self.table.indexAt(pos)
            if index.isValid():
                self.delegate.hovered_row = index.row()
                col = index.column()
                if col == COL_ALBUM_ARTISTS:
                    # Check if over artist text
                    rect = self.table.visualRect(index).adjusted(6, 0, -6, 0)
                    fm = self.table.fontMetrics()
                    album = index.data(Qt.ItemDataRole.UserRole)
                    if album and album.album_artists:
                        artists = album.album_artists
                        x_offset = rect.left()
                        over_artist = False
                        for artist in artists:
                            artist_width = fm.horizontalAdvance(artist)
                            artist_rect = QRect(x_offset, rect.top(), artist_width, rect.height())
                            if artist_rect.contains(pos):
                                over_artist = True
                                break
                            x_offset += artist_width + fm.horizontalAdvance(", ")

                        if over_artist:
                            self.table.setCursor(Qt.CursorShape.PointingHandCursor)
                        else:
                            self.table.setCursor(Qt.CursorShape.ArrowCursor)
                    else:
                        self.table.setCursor(Qt.CursorShape.ArrowCursor)
                else:
                    self.table.setCursor(Qt.CursorShape.ArrowCursor)
            else:
                self.delegate.hovered_row = -1
                self.table.setCursor(Qt.CursorShape.ArrowCursor)

            self.table.viewport().update()

        elif event.type() == QEvent.Type.Leave:
            self.delegate.clear_mouse_pos()
            self.delegate.hovered_row = -1
            self.table.viewport().update()
            self.table.setCursor(Qt.CursorShape.ArrowCursor)

        elif event.type() == QEvent.Type.MouseButtonPress:
            if event.button() == Qt.MouseButton.LeftButton:
                pos = event.position().toPoint()
                index = self.table.indexAt(pos)
                if index.isValid():
                    col = index.column()
                    if col == COL_ALBUM_ARTISTS:
                        rect = self.table.visualRect(index).adjusted(6, 0, -6, 0)
                        fm = self.table.fontMetrics()
                        album = index.data(Qt.ItemDataRole.UserRole)
                        if album and album.album_artists:
                            artists = album.album_artists
                            x_offset = rect.left()
                            for artist in artists:
                                artist_width = fm.horizontalAdvance(artist)
                                artist_rect = QRect(x_offset, rect.top(), artist_width, rect.height())
                                if artist_rect.contains(pos):
                                    self.view.artist_selected.emit(artist)
                                    return True
                                x_offset += artist_width + fm.horizontalAdvance(", ")

        return super().eventFilter(obj, event)


class _AlbumsTableModel(QAbstractTableModel):
    COLUMNS = ["Album Name", "Artists", "Year", "Duration"]

    def __init__(self, base_model: AlbumsListModel, parent=None):
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
        return 0 if parent.isValid() else len(self.COLUMNS)

    def sort_by_column(self, column: int, ascending: bool = True) -> None:
        self._sort_column = column
        self._sort_ascending = ascending
        self.base_model.sort_by_column(column, ascending)
        self.headerDataChanged.emit(Qt.Orientation.Horizontal, 0, len(self.COLUMNS) - 1)

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):
        if orientation == Qt.Orientation.Horizontal and role == Qt.ItemDataRole.DisplayRole:
            base_header = self.COLUMNS[section]
            if section == self._sort_column:
                arrow = "↑" if self._sort_ascending else "↓"
                return f"{arrow} {base_header}"
            return base_header
        return None

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None
        album = self.base_model.album_at(index.row())
        if album is None:
            return None
        if role == Qt.ItemDataRole.DisplayRole:
            col = index.column()
            if col == COL_ALBUM_NAME:
                return album.album_name
            if col == COL_ALBUM_ARTISTS:
                return ", ".join(album.album_artists)
            if col == COL_ALBUM_DURATION:
                return format_duration(album.total_duration)
            if col == COL_ALBUM_YEAR:
                return album.year or "—"
        if role == Qt.ItemDataRole.UserRole:
            return album
        return None


class AlbumsView(QWidget):
    album_selected = pyqtSignal(str)  # album_key
    artist_selected = pyqtSignal(str) # artist name

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
        self.table.verticalHeader().setDefaultSectionSize(40)
        self.table.setShowGrid(True)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.table.horizontalHeader().setStretchLastSection(False)
        self.table.setColumnWidth(COL_ALBUM_NAME, 250)
        self.table.setColumnWidth(COL_ALBUM_ARTISTS, 250)
        self.table.setColumnWidth(COL_ALBUM_YEAR, 80)
        self.table.setColumnWidth(COL_ALBUM_DURATION, 100)
        self.resize_helper = AdjacentResizeHelper(self.table.horizontalHeader())
        self.table.horizontalHeader().sectionClicked.connect(self._on_header_clicked)
        self.table.doubleClicked.connect(self._on_double_clicked)

        self.delegate = AlbumHoverDelegate(self.table, self)
        self.table.setItemDelegate(self.delegate)
        self.table.setMouseTracking(True)
        self.hover_filter = AlbumHoverEventFilter(self.table, self.delegate, self)
        self.table.viewport().installEventFilter(self.hover_filter)

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
        
        sort_col = getattr(self.table_model, "_sort_column", COL_ALBUM_NAME)
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
        album = self.base_model.album_at(index.row())
        if album:
            self.album_selected.emit(album.album_key)
