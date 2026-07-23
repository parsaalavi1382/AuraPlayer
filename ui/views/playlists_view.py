"""
Playlists tab view: displays non-removable smart playlists and customizable
playlists in a responsive layout matching the Artists tab table style for custom playlists.
"""

from __future__ import annotations

import os
from PyQt6.QtCore import Qt, pyqtSignal, QRectF, QPoint, QRect, QAbstractTableModel, QModelIndex, QObject, QEvent
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QGridLayout, QInputDialog, QMessageBox, QSizePolicy, QMenu,
    QTableView, QAbstractItemView, QHeaderView, QStyledItemDelegate,
    QStyleOptionViewItem, QStyle
)
from PyQt6.QtGui import QPainter, QPainterPath, QPixmap, QColor, QFont, QAction, QPen

from core.library_store import LibraryStore
from ui.theme import THEMES, DEFAULT_THEME
from ui.svg_icon import get_default_cover
from ui.widgets.adjacent_resize_helper import AdjacentResizeHelper


def get_playlist_collage(store: LibraryStore, playlist_id: str, size: int = 160, theme: dict = None) -> QPixmap:
    # 1. Check for custom cover path first
    if not playlist_id.startswith("smart_"):
        pl_obj = store.get_playlist(playlist_id)
        if pl_obj and pl_obj.cover_path and os.path.exists(pl_obj.cover_path):
            pix = QPixmap(pl_obj.cover_path)
            if not pix.isNull():
                return pix.scaled(
                    size, size,
                    Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                    Qt.TransformationMode.SmoothTransformation
                )

    # 2. Query tracks in chronological addition order (added_track_paths)
    tracks = []
    if not playlist_id.startswith("smart_"):
        pl_obj = store.get_playlist(playlist_id)
        if pl_obj:
            paths = pl_obj.added_track_paths if pl_obj.added_track_paths else pl_obj.track_paths
            for p in paths:
                t = store.get_track(p)
                if t:
                    tracks.append(t)

    if not tracks:
        tracks = store.get_playlist_tracks(playlist_id)

    distinct_pixmaps = []
    seen_albums = set()
    for t in tracks:
        from core.metadata_reader import get_album_art
        pix = get_album_art(t.path)
        if pix and not pix.isNull():
            album_key = t.album_key
            if album_key not in seen_albums:
                seen_albums.add(album_key)
                distinct_pixmaps.append(pix)
                if len(distinct_pixmaps) == 4:
                    break

    collage = QPixmap(size, size)
    collage.fill(Qt.GlobalColor.transparent)
    painter = QPainter(collage)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)

    # Clip to rounded rect with 12px corners for large cards, or 4px for small thumbnails
    corner_radius = 12.0 if size > 64 else 4.0
    path = QPainterPath()
    path.addRoundedRect(QRectF(0, 0, size, size), corner_radius, corner_radius)
    painter.setClipPath(path)

    num_covers = len(distinct_pixmaps)
    if num_covers == 0:
        painter.end()
        return get_default_cover(size, theme, corner_radius=corner_radius)
    elif num_covers == 1:
        first_pix = distinct_pixmaps[0]
        scaled = first_pix.scaled(
            size, size,
            Qt.AspectRatioMode.KeepAspectRatioByExpanding,
            Qt.TransformationMode.SmoothTransformation
        )
        if scaled.width() != size or scaled.height() != size:
            x = max(0, (scaled.width() - size) // 2)
            y = max(0, (scaled.height() - size) // 2)
            scaled = scaled.copy(x, y, size, size)
        painter.drawPixmap(0, 0, scaled)
    elif num_covers == 2 or num_covers == 3:
        # Show two album covers split vertically (left half and right half)
        half_width = size // 2
        
        # Cover 1: Left half
        pix1 = distinct_pixmaps[0]
        scaled1 = pix1.scaled(
            half_width, size,
            Qt.AspectRatioMode.KeepAspectRatioByExpanding,
            Qt.TransformationMode.SmoothTransformation
        )
        if scaled1.width() != half_width or scaled1.height() != size:
            x = max(0, (scaled1.width() - half_width) // 2)
            y = max(0, (scaled1.height() - size) // 2)
            scaled1 = scaled1.copy(x, y, half_width, size)
        painter.drawPixmap(0, 0, scaled1)
        
        # Cover 2: Right half
        pix2 = distinct_pixmaps[1]
        scaled2 = pix2.scaled(
            half_width, size,
            Qt.AspectRatioMode.KeepAspectRatioByExpanding,
            Qt.TransformationMode.SmoothTransformation
        )
        if scaled2.width() != half_width or scaled2.height() != size:
            x = max(0, (scaled2.width() - half_width) // 2)
            y = max(0, (scaled2.height() - size) // 2)
            scaled2 = scaled2.copy(x, y, half_width, size)
        painter.drawPixmap(half_width, 0, scaled2)
    else:
        # Show four album covers (2x2 grid)
        half_size = size // 2
        coords = [
            (0, 0),
            (half_size, 0),
            (0, half_size),
            (half_size, half_size)
        ]
        for i, pix in enumerate(distinct_pixmaps[:4]):
            scaled = pix.scaled(
                half_size, half_size,
                Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                Qt.TransformationMode.SmoothTransformation
            )
            if scaled.width() != half_size or scaled.height() != half_size:
                x = max(0, (scaled.width() - half_size) // 2)
                y = max(0, (scaled.height() - half_size) // 2)
                scaled = scaled.copy(x, y, half_size, half_size)
            x, y = coords[i]
            painter.drawPixmap(x, y, scaled)

    painter.end()
    return collage


def get_smart_playlist_cover(playlist_id: str, size: int = 160, theme_key: str = "dark") -> QPixmap:
    is_light = (theme_key == "light")
    
    # Select colors
    if is_light:
        if playlist_id == "smart_favorites":
            bg = "#FCE8E6"
            fg = "#C53929"
        elif playlist_id == "smart_recently_added":
            bg = "#FEF7E0"
            fg = "#B06000"
        elif playlist_id == "smart_recently_played":
            bg = "#E8F0FE"
            fg = "#1967D2"
        else: # smart_most_played
            bg = "#E6F4EA"
            fg = "#137333"
    else:
        if playlist_id == "smart_favorites":
            bg = "#3C1E20"
            fg = "#FFA6AA"
        elif playlist_id == "smart_recently_added":
            bg = "#3D2D14"
            fg = "#FFD180"
        elif playlist_id == "smart_recently_played":
            bg = "#122047"
            fg = "#A4C2FF"
        else: # smart_most_played
            bg = "#0A3A21"
            fg = "#A3E2B6"

    # Resolve icon name
    icon_name = {
        "smart_favorites": "heart",
        "smart_recently_added": "recently_added",
        "smart_recently_played": "history",
        "smart_most_played": "trending_up"
    }.get(playlist_id, "disc")

    # Create pixmap
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)
    
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    
    # Clip to rounded rect (12px corners)
    path = QPainterPath()
    path.addRoundedRect(QRectF(0, 0, size, size), 12.0, 12.0)
    painter.setClipPath(path)
    
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QColor(bg))
    painter.drawRect(0, 0, size, size)
    
    # Load and draw SVG icon (centered, size 48px or 64px)
    icon_size = 48 if size <= 160 else 64
    from ui.svg_icon import svg_pixmap
    # Render at 4x resolution for premium, ultra-crisp display
    render_size = icon_size * 4
    if playlist_id == "smart_favorites":
        ico_px = svg_pixmap(icon_name, fg, render_size, filled=True)
    else:
        ico_px = svg_pixmap(icon_name, fg, render_size)
        
    if not ico_px.isNull():
        x = (size - icon_size) // 2
        y = (size - icon_size) // 2
        painter.drawPixmap(QRectF(x, y, icon_size, icon_size), ico_px, QRectF(ico_px.rect()))
        
    painter.end()
    return pixmap


class SmartPlaylistCard(QWidget):
    clicked = pyqtSignal(str)

    def __init__(self, playlist_id: str, title: str, track_count: int, icon_name: str, store: LibraryStore, parent=None):
        super().__init__(parent)
        self.playlist_id = playlist_id
        self.title = title
        self.track_count = track_count
        self.icon_name = icon_name
        self.store = store
        self.is_hovered = False
        self.is_drag_over = False

        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedHeight(95)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setAcceptDrops(True)

    def dragEnterEvent(self, event):
        if self.playlist_id == "smart_favorites":
            if event.mimeData().hasFormat("application/x-aura-tracks") or event.mimeData().hasText():
                event.acceptProposedAction()
                self.is_drag_over = True
                self.update()

    def dragMoveEvent(self, event):
        if self.playlist_id == "smart_favorites":
            if event.mimeData().hasFormat("application/x-aura-tracks") or event.mimeData().hasText():
                event.acceptProposedAction()

    def dragLeaveEvent(self, event):
        self.is_drag_over = False
        self.update()

    def dropEvent(self, event):
        self.is_drag_over = False
        self.update()
        if self.playlist_id == "smart_favorites":
            mime = event.mimeData()
            if mime.hasFormat("application/x-aura-tracks") or mime.hasText():
                text = mime.text()
                paths = [p.strip() for p in text.split("\n") if p.strip()]
                if paths:
                    self.store.add_tracks_to_playlist(self.playlist_id, paths)
                    event.acceptProposedAction()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self.playlist_id)

    def enterEvent(self, event):
        self.is_hovered = True
        self.update()

    def leaveEvent(self, event):
        self.is_hovered = False
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        theme_key = self.store.cache.settings.theme
        is_light = (theme_key == "light")

        if is_light:
            if self.playlist_id == "smart_favorites":
                bg = "#FCE8E6" if not self.is_hovered else "#FADAD6"
                fg = "#C53929"
                fg_sec = "#8C514A"
            elif self.playlist_id == "smart_recently_added":
                bg = "#FEF7E0" if not self.is_hovered else "#FDF0CD"
                fg = "#B06000"
                fg_sec = "#80633C"
            elif self.playlist_id == "smart_recently_played":
                bg = "#E8F0FE" if not self.is_hovered else "#D2E3FC"
                fg = "#1967D2"
                fg_sec = "#527EBF"
            else: # smart_most_played
                bg = "#E6F4EA" if not self.is_hovered else "#CEEAD6"
                fg = "#137333"
                fg_sec = "#49855C"
        else:
            if self.playlist_id == "smart_favorites":
                bg = "#3C1E20" if not self.is_hovered else "#4D2628"
                fg = "#FFA6AA"
                fg_sec = "#CFA3A5"
            elif self.playlist_id == "smart_recently_added":
                bg = "#3D2D14" if not self.is_hovered else "#4E3A1A"
                fg = "#FFD180"
                fg_sec = "#D2C0A5"
            elif self.playlist_id == "smart_recently_played":
                bg = "#122047" if not self.is_hovered else "#1B2F63"
                fg = "#A4C2FF"
                fg_sec = "#8B97AE"
            else: # smart_most_played
                bg = "#0A3A21" if not self.is_hovered else "#0F5230"
                fg = "#A3E2B6"
                fg_sec = "#8B97AE"

        painter.save()
        if getattr(self, "is_drag_over", False):
            theme_key = self.store.cache.settings.theme
            theme = THEMES.get(theme_key, THEMES[DEFAULT_THEME])
            accent = theme.get("accent", "#6C5CE7")
            painter.setPen(QPen(QColor(accent), 2))
        else:
            painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(bg))
        painter.drawRoundedRect(QRectF(self.rect()).adjusted(1, 1, -1, -1), 12.0, 12.0)
        painter.restore()

        from ui.svg_icon import svg_pixmap
        if self.playlist_id == "smart_favorites":
            ico_px = svg_pixmap(self.icon_name, fg, 96, filled=True)
        else:
            ico_px = svg_pixmap(self.icon_name, fg, 96)
            
        if not ico_px.isNull():
            painter.drawPixmap(QRectF(16, 12, 24, 24), ico_px, QRectF(ico_px.rect()))

        painter.save()
        font = QFont("Segoe UI", 10, QFont.Weight.DemiBold)
        painter.setFont(font)
        text_primary_color = fg if is_light else "#FFFFFF"
        painter.setPen(QColor(text_primary_color))
        painter.drawText(16, 56, self.title)
        painter.restore()

        painter.save()
        font = QFont("Segoe UI", 8, QFont.Weight.Normal)
        painter.setFont(font)
        tracks_text = "1 track" if self.track_count == 1 else f"{self.track_count} tracks"
        painter.setPen(QColor(fg_sec))
        painter.drawText(16, 74, tracks_text)
        painter.restore()


class PlaylistDelegate(QStyledItemDelegate):
    """Renders playlist cover art thumbnail (based on 4 album covers of tracklist in addition order)
    on the left side of Column 0 in the custom playlists table, matching TracksView layout.
    """

    def __init__(self, table: QTableView, store: LibraryStore, view: QWidget, parent=None):
        super().__init__(parent)
        self.table = table
        self.store = store
        self.view = view
        self._pixmap_cache: dict[str, QPixmap] = {}

    def clear_cache(self):
        self._pixmap_cache.clear()

    def paint(self, painter, option, index):
        if index.column() != 0:
            opt = QStyleOptionViewItem(option)
            self.initStyleOption(opt, index)
            if index.row() == getattr(self, 'hovered_row', -1):
                opt.state |= QStyle.StateFlag.State_MouseOver
            else:
                opt.state &= ~QStyle.StateFlag.State_MouseOver
            super().paint(painter, opt, index)
            return

        opt = QStyleOptionViewItem(option)
        self.initStyleOption(opt, index)
        opt.text = ""  # Clear text so PE_PanelItemViewItem doesn't draw default text

        if index.row() == getattr(self, 'hovered_row', -1):
            opt.state |= QStyle.StateFlag.State_MouseOver
        else:
            opt.state &= ~QStyle.StateFlag.State_MouseOver

        widget = option.widget
        style = widget.style() if widget else None
        if style:
            style.drawPrimitive(QStyle.PrimitiveElement.PE_PanelItemViewItem, opt, painter, widget)

        pl_obj = index.data(Qt.ItemDataRole.UserRole)
        if not pl_obj:
            super().paint(painter, option, index)
            return

        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        theme_key = self.store.cache.settings.theme
        theme = THEMES.get(theme_key, THEMES[DEFAULT_THEME])

        fm = option.fontMetrics
        y_baseline = option.rect.top() + (option.rect.height() + fm.ascent() - fm.descent()) // 2
        text_color = QColor(theme['text_primary'])

        # Dimensions matching TracksView (28x28 cover with 10px left margin)
        cover_size = 28
        cover_x = option.rect.left() + 10
        cover_y = option.rect.top() + (option.rect.height() - cover_size) // 2
        cover_rect = QRect(cover_x, cover_y, cover_size, cover_size)

        # Retrieve or compute cached cover
        cache_key = f"{pl_obj.id}_{theme_key}_{cover_size}"
        if cache_key in self._pixmap_cache:
            cover_pixmap = self._pixmap_cache[cache_key]
        else:
            cover_pixmap = get_playlist_collage(self.store, pl_obj.id, size=cover_size, theme=theme)
            self._pixmap_cache[cache_key] = cover_pixmap

        # Draw album cover/placeholder clipped to rounded rect (4px radius like TracksView)
        clip_path = QPainterPath()
        clip_path.addRoundedRect(QRectF(cover_rect), 4.0, 4.0)

        painter.save()
        painter.setClipPath(clip_path)
        if cover_pixmap and not cover_pixmap.isNull():
            painter.drawPixmap(cover_rect, cover_pixmap)
        else:
            from ui.svg_icon import get_default_cover
            disc_px = get_default_cover(cover_size, theme, corner_radius=4.0)
            if disc_px and not disc_px.isNull():
                painter.drawPixmap(cover_rect, disc_px)
            else:
                painter.fillRect(cover_rect, QColor(theme.get("surface", "#1c1f26")))
        painter.restore()

        # Draw playlist name text on the right of the cover art
        text_rect_left = cover_x + cover_size + 10
        playlist_name_text = pl_obj.name or "Untitled Playlist"
        elided_name = fm.elidedText(playlist_name_text, Qt.TextElideMode.ElideRight, option.rect.right() - 6 - text_rect_left)

        painter.setPen(text_color)
        painter.drawText(text_rect_left, y_baseline, elided_name)

        painter.restore()


class PlaylistTableHoverFilter(QObject):
    def __init__(self, table, delegate):
        super().__init__(table)
        self.table = table
        self.delegate = delegate
        self.table.verticalScrollBar().valueChanged.connect(self._on_scroll)
        
    def _on_scroll(self):
        try:
            if not self.table or self.table.isHidden():
                return
            from PyQt6.QtGui import QCursor
            pos = self.table.viewport().mapFromGlobal(QCursor.pos())
            self._update_hover(pos)
        except RuntimeError:
            pass
            
    def _update_hover(self, pos):
        index = self.table.indexAt(pos)
        if index.isValid():
            self.delegate.hovered_row = index.row()
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
            self.table.viewport().update()
            
        return super().eventFilter(obj, event)


class _CustomPlaylistsTableModel(QAbstractTableModel):
    """Two-column table wrapper around custom playlists data (Playlist Name, Tracks),
    matching the Artists tab table design.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._playlists: list[tuple[any, int]] = []  # list of (Playlist, track_count)
        self._sort_column = 0
        self._sort_ascending = True

    def set_playlists(self, playlists: list[tuple[any, int]]) -> None:
        self.beginResetModel()
        self._playlists = list(playlists)
        self.endResetModel()

    def playlist_at(self, row: int) -> tuple[any, int] | None:
        if 0 <= row < len(self._playlists):
            return self._playlists[row]
        return None

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self._playlists)

    def columnCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else 2

    def sort_by_column(self, column: int, ascending: bool = True) -> None:
        self.layoutAboutToBeChanged.emit()
        self._sort_column = column
        self._sort_ascending = ascending
        if column == 0:
            self._playlists.sort(key=lambda x: x[0].name.lower(), reverse=not ascending)
        elif column == 1:
            self._playlists.sort(key=lambda x: x[1], reverse=not ascending)
        self.layoutChanged.emit()
        self.headerDataChanged.emit(Qt.Orientation.Horizontal, 0, 1)

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):
        if orientation == Qt.Orientation.Horizontal and role == Qt.ItemDataRole.DisplayRole:
            base_header = ["Playlist Name", "Tracks"][section]
            if section == self._sort_column:
                arrow = "↑" if self._sort_ascending else "↓"
                return f"{arrow} {base_header}"
            return base_header
        return None

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None
        info = self.playlist_at(index.row())
        if info is None:
            return None
        playlist, count = info
        if role == Qt.ItemDataRole.DisplayRole:
            return playlist.name if index.column() == 0 else str(count)
        if role == Qt.ItemDataRole.UserRole:
            return playlist
        return None


class _CustomPlaylistsTableView(QTableView):
    rename_requested = pyqtSignal(str)
    delete_requested = pyqtSignal(str)

    def __init__(self, store: LibraryStore, parent=None):
        super().__init__(parent)
        self.store = store
        self.setAcceptDrops(True)

    def dragEnterEvent(self, event):
        if event.mimeData().hasFormat("application/x-aura-tracks") or event.mimeData().hasText():
            event.acceptProposedAction()
        else:
            super().dragEnterEvent(event)

    def dragMoveEvent(self, event):
        if event.mimeData().hasFormat("application/x-aura-tracks") or event.mimeData().hasText():
            event.acceptProposedAction()
        else:
            super().dragMoveEvent(event)

    def dropEvent(self, event):
        mime = event.mimeData()
        if mime.hasFormat("application/x-aura-tracks") or mime.hasText():
            pos = event.position().toPoint()
            index = self.indexAt(pos)
            if index.isValid():
                pl_obj = index.data(Qt.ItemDataRole.UserRole)
                if pl_obj:
                    text = mime.text()
                    paths = [p.strip() for p in text.split("\n") if p.strip()]
                    if paths:
                        self.store.add_tracks_to_playlist(pl_obj.id, paths)
                        event.acceptProposedAction()
                        return
        super().dropEvent(event)

    def contextMenuEvent(self, event):
        pos = event.pos()
        index = self.indexAt(pos)
        if index.isValid():
            pl_obj = index.data(Qt.ItemDataRole.UserRole)
            if pl_obj:
                self._show_context_menu(event.globalPos(), pl_obj.id, pl_obj.name)

    def _show_context_menu(self, global_pos, playlist_id: str, playlist_name: str):
        menu = QMenu(self)
        
        theme_key = self.store.cache.settings.theme
        theme = THEMES.get(theme_key, THEMES[DEFAULT_THEME])
        bg = theme.get("surface", "#1E222B")
        text = theme.get("text_primary", "#FFFFFF")
        border = theme.get("border", "#2E323C")
        accent = theme.get("accent", "#6C5CE7")

        qss = f"""
            QMenu {{
                background-color: {bg};
                color: {text};
                border: 1px solid {border};
                border-radius: 8px;
                padding: 4px;
            }}
            QMenu::item {{
                padding: 6px 12px;
                border-radius: 4px;
                color: {text};
            }}
            QMenu::item:selected {{
                background-color: {accent};
                color: {text};
            }}
        """
        menu.setStyleSheet(qss)
        
        rename_action = QAction("Rename Playlist", self)
        delete_action = QAction("Delete Playlist", self)
        
        menu.addAction(rename_action)
        menu.addAction(delete_action)

        rename_action.triggered.connect(lambda: self.rename_requested.emit(playlist_id))
        delete_action.triggered.connect(lambda: self.delete_requested.emit(playlist_id))

        menu.exec(global_pos)


class PlaylistsView(QWidget):
    playlist_selected = pyqtSignal(str)

    def __init__(self, store: LibraryStore, parent=None):
        super().__init__(parent)
        self.store = store
        self.smart_cards: list[SmartPlaylistCard] = []

        outer = QVBoxLayout(self)
        outer.setContentsMargins(16, 12, 16, 0)
        outer.setSpacing(8)

        # Smart Grid (2x2 / 1x4 dynamic)
        self.smart_grid = QGridLayout()
        self.smart_grid.setContentsMargins(0, 0, 0, 0)
        self.smart_grid.setSpacing(12)
        outer.addLayout(self.smart_grid)

        # Interactive Row Header (Create Playlist and Stats)
        self.header_layout = QHBoxLayout()
        self.header_layout.setContentsMargins(0, 4, 0, 4)

        # "+ Create Playlist" button
        self.create_btn = QPushButton("+ Create Playlist")
        self.create_btn.setObjectName("textButton")
        self.create_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.create_btn.clicked.connect(self._on_create_playlist)
        self.header_layout.addWidget(self.create_btn)

        self.header_layout.addStretch()

        self.stats_lbl = QLabel("0 playlists")
        self.stats_lbl.setStyleSheet("font-size: 13px; font-weight: normal; background: transparent;")
        self.header_layout.addWidget(self.stats_lbl)

        outer.addLayout(self.header_layout)

        # Custom empty state label
        self.custom_empty_label = QLabel("No custom playlists yet. Click '+ Create Playlist' to start.")
        self.custom_empty_label.setObjectName("emptyStateSubtitle")
        self.custom_empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        outer.addWidget(self.custom_empty_label)

        # Custom playlists table view (styled like Artists tab)
        self.table_model = _CustomPlaylistsTableModel(self)
        self.table = _CustomPlaylistsTableView(self.store, self)
        self.table.setModel(self.table_model)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(40)
        self.table.setShowGrid(False)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.table.horizontalHeader().setStretchLastSection(False)
        self.table.setColumnWidth(0, 450)
        self.table.setColumnWidth(1, 100)
        self.resize_helper = AdjacentResizeHelper(self.table.horizontalHeader())

        self.delegate = PlaylistDelegate(self.table, self.store, self)
        self.table.setItemDelegate(self.delegate)
        self.table.setMouseTracking(True)
        self.hover_filter = PlaylistTableHoverFilter(self.table, self.delegate)
        self.table.viewport().installEventFilter(self.hover_filter)

        self.table.horizontalHeader().sectionClicked.connect(self._on_header_clicked)
        self.table.doubleClicked.connect(self._on_double_clicked)
        self.table.rename_requested.connect(self._on_rename_playlist)
        self.table.delete_requested.connect(self._on_delete_playlist)

        outer.addWidget(self.table, stretch=1)

        self.store.playlists_changed.connect(self._on_playlists_changed)
        self.store.tracks_added.connect(self._on_playlists_changed)
        self.store.track_updated.connect(self._on_playlists_changed)
        self.store.track_removed.connect(self._on_playlists_changed)
        
        self.refresh()

    def _layout_smart_cards(self) -> None:
        if len(self.smart_cards) < 4:
            return
        
        w = self.width()
        # Breakpoint consistent with wide desktop: 850px
        use_one_row = (w > 850)
        
        # Remove from grid
        for card in self.smart_cards:
            self.smart_grid.removeWidget(card)
            
        if use_one_row:
            # 1 row, 4 columns
            for i, card in enumerate(self.smart_cards):
                self.smart_grid.addWidget(card, 0, i)
        else:
            # 2 rows, 2 columns
            for i, card in enumerate(self.smart_cards):
                grid_row = i // 2 if not use_one_row else 0
                grid_col = i % 2 if not use_one_row else i
                self.smart_grid.addWidget(card, grid_row, grid_col)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._layout_smart_cards()

    def refresh(self) -> None:
        if hasattr(self, "delegate"):
            self.delegate.clear_cache()

        # Style stats label based on theme
        theme_key = self.store.cache.settings.theme
        theme = THEMES.get(theme_key, THEMES[DEFAULT_THEME])
        self.stats_lbl.setStyleSheet(f"color: {theme['text_secondary']}; font-size: 13px; font-weight: normal; background: transparent;")

        # Clear existing smart cards
        while self.smart_grid.count() > 0:
            item = self.smart_grid.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()
        self.smart_cards.clear()

        # 1. SMART PLAYLISTS
        smarts = [
            ("smart_favorites", "Favorites", "heart"),
            ("smart_recently_added", "Recently added", "recently_added"),
            ("smart_recently_played", "Recently played", "history"),
            ("smart_most_played", "Most played", "trending_up"),
        ]
        
        for pl_id, name, icon_name in smarts:
            tracks = self.store.get_playlist_tracks(pl_id)
            card = SmartPlaylistCard(pl_id, name, len(tracks), icon_name, self.store, self)
            card.clicked.connect(self.playlist_selected.emit)
            self.smart_cards.append(card)

        self._layout_smart_cards()

        # 2. CUSTOM PLAYLISTS
        customs = [p for p in self.store.all_playlists() if not p.id.startswith("smart_")]
        
        playlist_tuples = []
        for p in customs:
            tracks = self.store.get_playlist_tracks(p.id)
            playlist_tuples.append((p, len(tracks)))

        self.table_model.set_playlists(playlist_tuples)

        sort_col = getattr(self.table_model, "_sort_column", 0)
        sort_asc = getattr(self.table_model, "_sort_ascending", True)
        self.table_model.sort_by_column(sort_col, sort_asc)

        # Update stats
        self.stats_lbl.setText(f"{len(customs)} playlists")

        # Show / hide custom empty label vs table
        if not customs:
            self.custom_empty_label.show()
            self.table.hide()
        else:
            self.custom_empty_label.hide()
            self.table.show()

    def _on_playlists_changed(self, *_args) -> None:
        self.refresh()

    def _on_header_clicked(self, index: int) -> None:
        if self.table_model._sort_column == index:
            new_asc = not self.table_model._sort_ascending
        else:
            new_asc = True
        self.table_model.sort_by_column(index, new_asc)

    def _on_double_clicked(self, index) -> None:
        info = self.table_model.playlist_at(index.row())
        if info:
            self.playlist_selected.emit(info[0].id)

    def _on_create_playlist(self) -> None:
        name, ok = QInputDialog.getText(
            self, "Create Playlist",
            "Enter playlist name:",
            text=""
        )
        if ok and name.strip():
            playlist_id = self.store.create_playlist(name.strip())
            self.playlist_selected.emit(playlist_id)

    def _on_rename_playlist(self, playlist_id: str) -> None:
        pl_obj = self.store.get_playlist(playlist_id)
        if not pl_obj:
            return
        
        name, ok = QInputDialog.getText(
            self, "Rename Playlist",
            f"Rename '{pl_obj.name}' to:",
            text=pl_obj.name
        )
        if ok and name.strip() and name.strip() != pl_obj.name:
            self.store.rename_playlist(playlist_id, name.strip())

    def _on_delete_playlist(self, playlist_id: str) -> None:
        pl_obj = self.store.get_playlist(playlist_id)
        if not pl_obj:
            return
        reply = QMessageBox.question(
            self, "Delete Playlist",
            f"Are you sure you want to delete '{pl_obj.name}'?\n\nThis cannot be undone.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            self.store.delete_playlist(playlist_id)
