"""
Artists tab: Artist Name | Number of Tracks, per spec.
Clicking an artist navigates to that Artist Page (built in Step 5).
"""

from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal, QAbstractTableModel, QModelIndex, QObject, QEvent, QSize
from PyQt6.QtGui import QCursor, QIcon
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QTableView, QStackedWidget, QHeaderView, QAbstractItemView,
    QStyledItemDelegate, QStyleOptionViewItem, QStyle
)

from core.library_store import LibraryStore
from ui.models.library_group_models import ArtistsListModel
from ui.widgets.empty_state import EmptyStateWidget
from ui.widgets.adjacent_resize_helper import AdjacentResizeHelper
from PyQt6.QtCore import QAbstractTableModel, QModelIndex, QRectF
from PyQt6.QtGui import QPixmap, QPainter, QPainterPath


def get_artist_collage(store: LibraryStore, artist_name: str, target_size: int = 160, theme: dict = None) -> QPixmap:
    import os
    from core.metadata_reader import get_album_art
    from ui.svg_icon import get_default_artist_cover

    # Supersampling: Render at 4x resolution for maximum crispness in the list thumbnail
    render_size = target_size * 4

    cover_path = store.get_artist_image(artist_name)
    if cover_path and os.path.exists(cover_path):
        pix = QPixmap(cover_path)
        if not pix.isNull():
            scaled = pix.scaled(
                render_size, render_size,
                Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                Qt.TransformationMode.SmoothTransformation
            )
            collage = QPixmap(render_size, render_size)
            collage.fill(Qt.GlobalColor.transparent)
            
            painter = QPainter(collage)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
            painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
            
            path = QPainterPath()
            from PyQt6.QtCore import QRectF
            path.addEllipse(QRectF(0, 0, render_size, render_size))
            painter.setClipPath(path)
            
            x = max(0, (scaled.width() - render_size) // 2)
            y = max(0, (scaled.height() - render_size) // 2)
            cropped = scaled.copy(x, y, render_size, render_size)
            
            painter.drawPixmap(0, 0, cropped)
            painter.end()
            
            # Scale down to final target size smoothly
            return collage.scaled(target_size, target_size, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)

    tracks = []
    for t in store.all_tracks():
        if artist_name in t.album_artists:
            tracks.append(t)
    
    distinct_pixmaps = []
    seen_albums = set()
    tracks.sort(key=lambda x: (x.album or "").lower())
    for t in tracks:
        pix = get_album_art(t.path)
        if pix and not pix.isNull():
            album_key = t.album_key
            if album_key not in seen_albums:
                seen_albums.add(album_key)
                distinct_pixmaps.append(pix)
                if len(distinct_pixmaps) == 4:
                    break

    collage = QPixmap(render_size, render_size)
    collage.fill(Qt.GlobalColor.transparent)
    painter = QPainter(collage)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)

    path = QPainterPath()
    from PyQt6.QtCore import QRectF
    path.addEllipse(QRectF(0, 0, render_size, render_size))
    painter.setClipPath(path)

    num_covers = len(distinct_pixmaps)
    if num_covers == 0:
        painter.end()
        return get_default_artist_cover(target_size, theme or {}, corner_radius=target_size/2.0)
    elif num_covers == 1:
        first_pix = distinct_pixmaps[0]
        scaled = first_pix.scaled(
            render_size, render_size,
            Qt.AspectRatioMode.KeepAspectRatioByExpanding,
            Qt.TransformationMode.SmoothTransformation
        )
        x = max(0, (scaled.width() - render_size) // 2)
        y = max(0, (scaled.height() - render_size) // 2)
        scaled = scaled.copy(x, y, render_size, render_size)
        painter.drawPixmap(0, 0, scaled)
    elif num_covers == 2 or num_covers == 3:
        half_width = render_size // 2
        
        pix1 = distinct_pixmaps[0]
        scaled1 = pix1.scaled(
            half_width, render_size,
            Qt.AspectRatioMode.KeepAspectRatioByExpanding,
            Qt.TransformationMode.SmoothTransformation
        )
        x1 = max(0, (scaled1.width() - half_width) // 2)
        y1 = max(0, (scaled1.height() - render_size) // 2)
        painter.drawPixmap(0, 0, scaled1.copy(x1, y1, half_width, render_size))
        
        pix2 = distinct_pixmaps[1]
        scaled2 = pix2.scaled(
            render_size - half_width, render_size,
            Qt.AspectRatioMode.KeepAspectRatioByExpanding,
            Qt.TransformationMode.SmoothTransformation
        )
        x2 = max(0, (scaled2.width() - (render_size - half_width)) // 2)
        y2 = max(0, (scaled2.height() - render_size) // 2)
        painter.drawPixmap(half_width, 0, scaled2.copy(x2, y2, render_size - half_width, render_size))
    else:
        half_size = render_size // 2
        coords = [
            (0, 0),
            (half_size, 0),
            (0, half_size),
            (half_size, half_size)
        ]
        for i in range(4):
            pix = distinct_pixmaps[i]
            scaled = pix.scaled(
                half_size, half_size,
                Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                Qt.TransformationMode.SmoothTransformation
            )
            x = max(0, (scaled.width() - half_size) // 2)
            y = max(0, (scaled.height() - half_size) // 2)
            cx, cy = coords[i]
            painter.drawPixmap(cx, cy, scaled.copy(x, y, half_size, half_size))
            
    painter.end()
    
    # Scale down to final target size smoothly
    return collage.scaled(target_size, target_size, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)


class _ArtistsTableModel(QAbstractTableModel):
    """Thin table wrapper around ArtistsListModel data so we can show
    two columns (Name, Track Count) in a QTableView, matching the spec's
    table layout rather than a plain list.
    """

    def __init__(self, base_model: ArtistsListModel, view: ArtistsView, parent=None):
        super().__init__(parent)
        self.base_model = base_model
        self.view = view
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
        if role == Qt.ItemDataRole.UserRole + 1 and index.column() == 0:
            store = self.view.store
            theme_key = store.cache.settings.theme
            from ui.theme import THEMES, DEFAULT_THEME
            theme = THEMES.get(theme_key, THEMES[DEFAULT_THEME])
            # Return pixmap via custom role so delegate can draw it manually (sharp)
            return get_artist_collage(store, artist.name, 40, theme)
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
        self.table_model = _ArtistsTableModel(self.base_model, self, self)

        self.table = QTableView()
        self.table.setModel(self.table_model)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(50)
        from PyQt6.QtCore import QSize
        self.table.setIconSize(QSize(40, 40))
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
    def __init__(self, parent=None, has_avatars: bool = True):
        super().__init__(parent)
        self.hovered_row = -1
        self.has_avatars = has_avatars

    def paint(self, painter, option, index):
        from PyQt6.QtCore import QRectF
        from PyQt6.QtGui import QPainterPath

        opt = QStyleOptionViewItem(option)
        self.initStyleOption(opt, index)
        if index.row() == self.hovered_row:
            opt.state |= QStyle.StateFlag.State_MouseOver
        else:
            opt.state &= ~QStyle.StateFlag.State_MouseOver

        if self.has_avatars:
            # Fetch our manually-supplied pixmap (custom role) before super() draws
            cover_pix = index.data(Qt.ItemDataRole.UserRole + 1) if index.column() == 0 else None

            # Let Qt draw background, hover highlight, and text — but without any decoration
            opt.decorationSize = QSize(0, 0)
            opt.icon = QIcon()
            # Shift text rect right to leave room for the avatar
            ICON_AREA = 48  # 40px icon + 8px gap
            opt.rect.setLeft(opt.rect.left() + ICON_AREA)
            super().paint(painter, opt, index)
            opt.rect.setLeft(opt.rect.left() - ICON_AREA)  # restore (defensive)

            # Now draw the circular avatar ourselves with full quality
            if cover_pix and not cover_pix.isNull() and index.column() == 0:
                AVATAR_SIZE = 36
                x = option.rect.left() + 5
                y = option.rect.top() + (option.rect.height() - AVATAR_SIZE) // 2
                painter.save()
                painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
                painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
                clip = QPainterPath()
                clip.addEllipse(QRectF(x, y, AVATAR_SIZE, AVATAR_SIZE))
                painter.setClipPath(clip)
                painter.drawPixmap(x, y, AVATAR_SIZE, AVATAR_SIZE, cover_pix)
                painter.restore()
        else:
            # No avatars — just draw normally (no text shift)
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
