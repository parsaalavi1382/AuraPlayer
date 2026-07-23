"""
PlaylistPageView: Dedicated page displaying details for a specific playlist
(smart or custom), including track tables, stats, drag-reordering,
cover picking, renaming, deletion, and context menus.
"""

from __future__ import annotations

import math
import os
import time

from PyQt6.QtCore import (
    Qt, pyqtSignal, QTimer, QRect, QPoint, QRectF, QSize, QEvent, QObject,
    QAbstractTableModel, QModelIndex
)
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QInputDialog,
    QHeaderView, QAbstractItemView, QStyledItemDelegate, QStyle, QStyleOptionViewItem,
    QScrollArea, QSizePolicy, QFileDialog, QMessageBox, QMenu
)
from PyQt6.QtGui import QFont, QColor, QPainter, QBrush, QPen, QPixmap, QAction, QPainterPath

from core.library_store import LibraryStore
from core.models import Track
from core.metadata_reader import get_album_art
from ui.theme import THEMES, DEFAULT_THEME
from ui.widgets.adjacent_resize_helper import AdjacentResizeHelper
from ui.widgets.drag_table_view import AuraDragTableView

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


class PlaylistTracksTableModel(QAbstractTableModel):
    def __init__(self, tracks: list[Track], parent=None):
        super().__init__(parent)
        self._tracks = list(tracks)
        self._currently_playing_path = None
        self._danger_color = "#E05C5C"
        self._sort_column = -1
        self._sort_ascending = True

    def rowCount(self, parent=QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self._tracks)

    def columnCount(self, parent=QModelIndex()) -> int:
        return 0 if parent.isValid() else len(COLUMN_HEADERS)

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):
        if orientation == Qt.Orientation.Horizontal and role == Qt.ItemDataRole.DisplayRole:
            base_header = COLUMN_HEADERS[section]
            if section == self._sort_column:
                arrow = "↑" if self._sort_ascending else "↓"
                return f"{arrow} {base_header}"
            return base_header
        return None

    def sort(self, column: int, order: Qt.SortOrder) -> None:
        self._sort_column = column
        ascending = (order == Qt.SortOrder.AscendingOrder)
        self._sort_ascending = ascending

        if column == COL_TITLE:
            self._tracks.sort(key=lambda t: (t.title or "").lower(), reverse=not ascending)
        elif column == COL_ARTISTS:
            self._tracks.sort(key=lambda t: ", ".join(t.artists).lower(), reverse=not ascending)
        elif column == COL_ALBUM:
            self._tracks.sort(key=lambda t: (t.album or "").lower(), reverse=not ascending)
        elif column == COL_GENRE:
            self._tracks.sort(key=lambda t: (t.genre or "").lower(), reverse=not ascending)
        elif column == COL_DURATION:
            self._tracks.sort(key=lambda t: t.duration, reverse=not ascending)

        # Propagate back to parent view to preserve sort state across table rebuilds
        if self.parent() is not None:
            self.parent().active_sort_column = column
            self.parent().active_sort_ascending = ascending
            self.parent().store.set_playlist_sort_state(self.parent().playlist_id, column, ascending)

        self.layoutChanged.emit()

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
            return track

        if role == Qt.ItemDataRole.ForegroundRole and track.file_missing:
            return QColor(self._danger_color)

        return None

    def track_at(self, row: int) -> Track | None:
        if 0 <= row < len(self._tracks):
            return self._tracks[row]
        return None


class PlaylistTrackHoverDelegate(QStyledItemDelegate):
    def __init__(self, table, view, parent=None):
        super().__init__(parent)
        self.table = table
        self.view = view
        self.mouse_pos = QPoint(-1, -1)
        self.hovered_row = -1
        self.art_cache = {}

    def set_mouse_pos(self, pos: QPoint):
        self.mouse_pos = pos

    def clear_mouse_pos(self):
        self.mouse_pos = QPoint(-1, -1)

    def is_over_album_cover(self, index, pos) -> bool:
        if index.column() != COL_TITLE:
            return False
        rect = self.table.visualRect(index)
        if not rect.contains(pos):
            return False
        cover_size = 28
        cover_x = rect.left() + 10
        cover_y = rect.top() + (rect.height() - cover_size) // 2
        cover_rect = QRect(cover_x, cover_y, cover_size, cover_size)
        return cover_rect.contains(pos)

    def is_over_clickable_text(self, index, pos) -> bool:
        col = index.column()
        if col == COL_ARTISTS:
            return self.get_artist_at_pos(index, pos) is not None
        elif col == COL_GENRE:
            return self.get_genre_at_pos(index, pos) is not None
        elif col == COL_ALBUM:
            rect = self.table.visualRect(index).adjusted(6, 0, -6, 0)
            if not rect.contains(pos):
                return False
            fm = self.table.fontMetrics()
            album_text = index.data(Qt.ItemDataRole.DisplayRole) or ""
            album_width = fm.horizontalAdvance(album_text)
            if rect.left() + album_width > rect.right():
                elided_album = fm.elidedText(album_text, Qt.TextElideMode.ElideRight, rect.width())
                elided_width = fm.horizontalAdvance(elided_album)
                album_rect = QRect(rect.left(), rect.top(), elided_width, rect.height())
                return album_rect.contains(pos)
            else:
                album_rect = QRect(rect.left(), rect.top(), album_width, rect.height())
                return album_rect.contains(pos)
        return False

    def get_artist_at_pos(self, index, pos) -> str | None:
        col = index.column()
        if col != COL_ARTISTS:
            return None
            
        rect = self.table.visualRect(index).adjusted(6, 0, -6, 0)
        if not rect.contains(pos):
            return None
            
        fm = self.table.fontMetrics()
        max_x = rect.right()
        ellipsis_width = fm.horizontalAdvance("...")
        
        artists_text = index.data(Qt.ItemDataRole.DisplayRole) or ""
        artists = [a.strip() for a in artists_text.split(",") if a.strip()]
        
        x_offset = rect.left()
        for i, artist in enumerate(artists):
            artist_width = fm.horizontalAdvance(artist)
            next_delim = ", " if i < len(artists) - 1 else ""
            delim_width = fm.horizontalAdvance(next_delim) if next_delim else 0
            
            if x_offset + artist_width + delim_width > max_x:
                available_w = max_x - x_offset - ellipsis_width
                if available_w > 10:
                    elided_artist = fm.elidedText(artist, Qt.TextElideMode.ElideRight, available_w)
                    elided_width = fm.horizontalAdvance(elided_artist)
                    artist_rect = QRect(x_offset, rect.top(), elided_width, rect.height())
                    if artist_rect.contains(pos):
                        return artist
                break
            else:
                artist_rect = QRect(x_offset, rect.top(), artist_width, rect.height())
                if artist_rect.contains(pos):
                    return artist
                x_offset += artist_width + delim_width
                
        return None

    def get_genre_at_pos(self, index, pos) -> str | None:
        col = index.column()
        if col != COL_GENRE:
            return None
            
        rect = self.table.visualRect(index).adjusted(6, 0, -6, 0)
        if not rect.contains(pos):
            return None
            
        fm = self.table.fontMetrics()
        max_x = rect.right()
        ellipsis_width = fm.horizontalAdvance("...")
        
        genre_text = index.data(Qt.ItemDataRole.DisplayRole) or ""
        if not genre_text or genre_text == "—":
            return None
            
        genres = [g.strip() for g in genre_text.split(",") if g.strip()]
        
        x_offset = rect.left()
        for i, genre in enumerate(genres):
            genre_width = fm.horizontalAdvance(genre)
            next_delim = ", " if i < len(genres) - 1 else ""
            delim_width = fm.horizontalAdvance(next_delim) if next_delim else 0
            
            if x_offset + genre_width + delim_width > max_x:
                available_w = max_x - x_offset - ellipsis_width
                if available_w > 10:
                    elided_genre = fm.elidedText(genre, Qt.TextElideMode.ElideRight, available_w)
                    elided_width = fm.horizontalAdvance(elided_genre)
                    genre_rect = QRect(x_offset, rect.top(), elided_width, rect.height())
                    if genre_rect.contains(pos):
                        return genre
                break
            else:
                genre_rect = QRect(x_offset, rect.top(), genre_width, rect.height())
                if genre_rect.contains(pos):
                    return genre
                x_offset += genre_width + delim_width
                
        return None

    def paint(self, painter, option, index):
        col = index.column()
        if col not in (COL_TITLE, COL_ARTISTS, COL_ALBUM, COL_GENRE, COL_DURATION):
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
        opt.text = ""

        if index.row() == getattr(self, 'hovered_row', -1):
            opt.state |= QStyle.StateFlag.State_MouseOver
        else:
            opt.state &= ~QStyle.StateFlag.State_MouseOver

        widget = option.widget
        style = widget.style() if widget else None
        if style:
            style.drawPrimitive(QStyle.PrimitiveElement.PE_PanelItemViewItem, opt, painter, widget)

        track = index.data(Qt.ItemDataRole.UserRole)
        if not track:
            super().paint(painter, option, index)
            return

        painter.save()

        is_current = False
        is_playing = False
        if self.view.engine:
            is_current = (self.view.engine.get_current_track_path() == track.path)
            is_playing = is_current and self.view.engine.is_playing()

        is_row_hovered = (index.row() == self.hovered_row)

        theme_key = self.view.store.cache.settings.theme
        theme = THEMES.get(theme_key, THEMES[DEFAULT_THEME])

        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        rect = option.rect.adjusted(6, 0, -6, 0)
        fm = option.fontMetrics
        y_baseline = rect.top() + (rect.height() + fm.ascent() - fm.descent()) // 2

        if col == COL_TITLE:
            # Dimensions for album cover (mirroring tracks_view exactly)
            cover_size = 28
            cover_x = option.rect.left() + 10
            cover_y = option.rect.top() + (option.rect.height() - cover_size) // 2
            cover_rect = QRect(cover_x, cover_y, cover_size, cover_size)

            # Cache & Load scaled art
            if track.path not in self.art_cache:
                raw_pixmap = get_album_art(track.path)
                if raw_pixmap and not raw_pixmap.isNull():
                    scaled = raw_pixmap.scaled(
                        cover_size, cover_size,
                        Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                        Qt.TransformationMode.SmoothTransformation,
                    )
                    self.art_cache[track.path] = scaled
                else:
                    self.art_cache[track.path] = None

            pixmap = self.art_cache[track.path]

            # Draw album cover/placeholder with 4px corners
            clip_path = QPainterPath()
            clip_path.addRoundedRect(QRectF(cover_rect), 4.0, 4.0)

            painter.save()
            painter.setClipPath(clip_path)
            if pixmap:
                painter.drawPixmap(cover_rect, pixmap)
            else:
                from ui.svg_icon import get_default_cover
                disc_px = get_default_cover(cover_size, theme, corner_radius=4.0)
                if disc_px and not disc_px.isNull():
                    painter.drawPixmap(cover_rect, disc_px)
                else:
                    painter.fillRect(cover_rect, QColor(theme['surface']))
            painter.restore()

            # Dark overlay if playing or hovered
            if is_playing or is_row_hovered:
                painter.save()
                painter.setClipPath(clip_path)
                painter.fillRect(cover_rect, QColor(0, 0, 0, 110))
                painter.restore()

            # Equalizer or Play icon overlay
            if is_playing:
                max_bar_h = 12
                bar_w = 3
                spacing = 2
                eq_x = cover_rect.left() + (cover_size - (3 * bar_w + 2 * spacing)) // 2
                eq_y = cover_rect.top() + (cover_size - max_bar_h) // 2

                t = time.time()
                h1 = 0.2 + 0.7 * abs(math.sin(t * 9.0))
                h2 = 0.3 + 0.6 * abs(math.sin(t * 13.0 + 1.5))
                h3 = 0.1 + 0.8 * abs(math.sin(t * 7.5 + 3.0))

                heights = [h1 * max_bar_h, h2 * max_bar_h, h3 * max_bar_h]

                painter.save()
                painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(QBrush(QColor("#FFFFFF")))
                for i, h in enumerate(heights):
                    x = eq_x + i * (bar_w + spacing)
                    y = (eq_y + max_bar_h) - h
                    painter.drawRect(QRectF(x, y, bar_w, h))
                painter.restore()

            elif is_row_hovered:
                painter.save()
                painter.setRenderHint(QPainter.RenderHint.Antialiasing)
                font = QFont()
                font.setPointSize(9)
                font.setBold(True)
                painter.setFont(font)
                painter.setPen(QColor("#FFFFFF"))
                play_rect = cover_rect.adjusted(1, 0, 0, 0)
                painter.drawText(play_rect, Qt.AlignmentFlag.AlignCenter, "▶")
                painter.restore()

            # Draw the track title text on the right of the cover
            title_text = track.title or "Unknown Title"
            text_rect = option.rect.adjusted(cover_size + 18, 0, -6, 0)
            elided_title = fm.elidedText(title_text, Qt.TextElideMode.ElideRight, text_rect.width())

            font = painter.font()
            if is_current:
                font.setBold(True)
                painter.setPen(QColor(theme['accent']))
            else:
                font.setBold(False)
                painter.setPen(QColor(theme['text_primary']))
            painter.setFont(font)

            painter.drawText(text_rect.left(), y_baseline, elided_title)

        elif col in (COL_ARTISTS, COL_ALBUM, COL_GENRE):
            is_hovered = option.rect.contains(self.mouse_pos)
            text_color = QColor(theme['text_secondary'])
            
            if col == COL_ARTISTS:
                artists_text = index.data(Qt.ItemDataRole.DisplayRole) or ""
                artists = [a.strip() for a in artists_text.split(",") if a.strip()]
                
                x_offset = rect.left()
                max_x = rect.right()
                ellipsis = "..."
                ellipsis_width = fm.horizontalAdvance(ellipsis)
                
                for i, artist in enumerate(artists):
                    artist_width = fm.horizontalAdvance(artist)
                    next_delim = ", " if i < len(artists) - 1 else ""
                    delim_width = fm.horizontalAdvance(next_delim) if next_delim else 0
                    
                    if x_offset + artist_width + delim_width > max_x:
                        available_w = max_x - x_offset - ellipsis_width
                        if available_w > 10:
                            elided_artist = fm.elidedText(artist, Qt.TextElideMode.ElideRight, available_w)
                            elided_width = fm.horizontalAdvance(elided_artist)
                            
                            artist_rect = QRect(x_offset, rect.top(), elided_width, rect.height())
                            artist_hovered = is_hovered and artist_rect.contains(self.mouse_pos)
                            
                            font = painter.font()
                            font.setUnderline(artist_hovered)
                            painter.setFont(font)
                            if artist_hovered and not (option.state & QStyle.StateFlag.State_Selected):
                                painter.setPen(QColor(theme['accent']))
                            else:
                                painter.setPen(text_color)
                            painter.drawText(x_offset, y_baseline, elided_artist)
                        else:
                            if x_offset + ellipsis_width <= max_x + 5:
                                painter.setPen(text_color)
                                painter.drawText(x_offset, y_baseline, ellipsis)
                        break
                    else:
                        artist_rect = QRect(x_offset, rect.top(), artist_width, rect.height())
                        artist_hovered = is_hovered and artist_rect.contains(self.mouse_pos)
                        
                        font = painter.font()
                        font.setUnderline(artist_hovered)
                        painter.setFont(font)
                        if artist_hovered and not (option.state & QStyle.StateFlag.State_Selected):
                            painter.setPen(QColor(theme['accent']))
                        else:
                            painter.setPen(text_color)
                        
                        painter.drawText(x_offset, y_baseline, artist)
                        x_offset += artist_width
                        
                        if next_delim:
                            font.setUnderline(False)
                            painter.setFont(font)
                            painter.setPen(text_color)
                            painter.drawText(x_offset, y_baseline, next_delim)
                            x_offset += delim_width

            elif col == COL_ALBUM:
                album_text = index.data(Qt.ItemDataRole.DisplayRole) or ""
                album_width = fm.horizontalAdvance(album_text)
                
                font = painter.font()
                if rect.left() + album_width > rect.right():
                    elided_album = fm.elidedText(album_text, Qt.TextElideMode.ElideRight, rect.width())
                    elided_width = fm.horizontalAdvance(elided_album)
                    album_rect = QRect(rect.left(), rect.top(), elided_width, rect.height())
                    album_hovered = is_hovered and album_rect.contains(self.mouse_pos)
                    
                    font.setUnderline(album_hovered)
                    painter.setFont(font)
                    if album_hovered and not (option.state & QStyle.StateFlag.State_Selected):
                        painter.setPen(QColor(theme['accent']))
                    else:
                        painter.setPen(text_color)
                    painter.drawText(rect.left(), y_baseline, elided_album)
                else:
                    album_rect = QRect(rect.left(), rect.top(), album_width, rect.height())
                    album_hovered = is_hovered and album_rect.contains(self.mouse_pos)
                    
                    font.setUnderline(album_hovered)
                    painter.setFont(font)
                    if album_hovered and not (option.state & QStyle.StateFlag.State_Selected):
                        painter.setPen(QColor(theme['accent']))
                    else:
                        painter.setPen(text_color)
                    painter.drawText(rect.left(), y_baseline, album_text)

            elif col == COL_GENRE:
                genre_text = index.data(Qt.ItemDataRole.DisplayRole) or ""
                if genre_text and genre_text != "—":
                    genres = [g.strip() for g in genre_text.split(",") if g.strip()]
                    x_offset = rect.left()
                    max_x = rect.right()
                    ellipsis = "..."
                    ellipsis_width = fm.horizontalAdvance(ellipsis)
                    
                    for i, genre in enumerate(genres):
                        genre_width = fm.horizontalAdvance(genre)
                        next_delim = ", " if i < len(genres) - 1 else ""
                        delim_width = fm.horizontalAdvance(next_delim) if next_delim else 0
                        
                        if x_offset + genre_width + delim_width > max_x:
                            available_w = max_x - x_offset - ellipsis_width
                            if available_w > 10:
                                elided_genre = fm.elidedText(genre, Qt.TextElideMode.ElideRight, available_w)
                                elided_width = fm.horizontalAdvance(elided_genre)
                                
                                genre_rect = QRect(x_offset, rect.top(), elided_width, rect.height())
                                genre_hovered = is_hovered and genre_rect.contains(self.mouse_pos)
                                
                                font = painter.font()
                                font.setUnderline(genre_hovered)
                                painter.setFont(font)
                                if genre_hovered and not (option.state & QStyle.StateFlag.State_Selected):
                                    painter.setPen(QColor(theme['accent']))
                                else:
                                    painter.setPen(text_color)
                                painter.drawText(x_offset, y_baseline, elided_genre)
                            else:
                                if x_offset + ellipsis_width <= max_x + 5:
                                    painter.setPen(text_color)
                                    painter.drawText(x_offset, y_baseline, ellipsis)
                            break
                        else:
                            genre_rect = QRect(x_offset, rect.top(), genre_width, rect.height())
                            genre_hovered = is_hovered and genre_rect.contains(self.mouse_pos)
                            
                            font = painter.font()
                            font.setUnderline(genre_hovered)
                            painter.setFont(font)
                            if genre_hovered and not (option.state & QStyle.StateFlag.State_Selected):
                                painter.setPen(QColor(theme['accent']))
                            else:
                                painter.setPen(text_color)
                            
                            painter.drawText(x_offset, y_baseline, genre)
                            x_offset += genre_width + delim_width
                else:
                    painter.drawText(rect.left(), y_baseline, "—")

        elif col == COL_DURATION:
            dur_text = format_duration(track.duration)
            painter.setPen(QColor(theme['text_secondary']))
            painter.drawText(rect, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, dur_text)

        painter.restore()


class PlaylistHoverEventFilter(QObject):
    def __init__(self, table, delegate, view):
        super().__init__(table)
        self.table = table
        self.delegate = delegate
        self.view = view
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
        self.delegate.set_mouse_pos(pos)
        index = self.table.indexAt(pos)
        if index.isValid():
            self.delegate.hovered_row = index.row()
            col = index.column()
            if col in (COL_ARTISTS, COL_ALBUM, COL_GENRE):
                if self.delegate.is_over_clickable_text(index, pos):
                    self.table.setCursor(Qt.CursorShape.PointingHandCursor)
                else:
                    self.table.setCursor(Qt.CursorShape.ArrowCursor)
            elif col == COL_TITLE and self.delegate.is_over_album_cover(index, pos):
                self.table.setCursor(Qt.CursorShape.PointingHandCursor)
            else:
                self.table.setCursor(Qt.CursorShape.ArrowCursor)
        else:
            self.delegate.hovered_row = -1
            self.table.setCursor(Qt.CursorShape.ArrowCursor)

        if self.table and self.table.viewport():
            self.table.viewport().update()

    def eventFilter(self, obj, event):
        try:
            if self.table is None:
                return False
            # Check if viewport or table is deleted
            viewport = self.table.viewport()
            if not viewport:
                return False

            if event.type() == QEvent.Type.MouseMove:
                # Ensure mouseMoveEvent is passed to table for dragging
                self.table.mouseMoveEvent(event)
                self._update_hover(event.position().toPoint())

            elif event.type() == QEvent.Type.Leave:
                self.delegate.clear_mouse_pos()
                self.delegate.hovered_row = -1
                viewport.update()
                self.table.setCursor(Qt.CursorShape.ArrowCursor)

            elif event.type() == QEvent.Type.MouseButtonPress:
                if event.button() == Qt.MouseButton.LeftButton:
                    pos = event.position().toPoint()
                    self.table._drag_start_pos = pos  # Capture drag start pos
                    
                    index = self.table.indexAt(pos)
                    if index.isValid():
                        col = index.column()
                        if col == COL_TITLE and self.delegate.is_over_album_cover(index, pos):
                            self.view._on_row_double_clicked(index)
                            return True
                        elif col == COL_ARTISTS:
                            clicked_artist = self.delegate.get_artist_at_pos(index, pos)
                            if clicked_artist:
                                self.view.artist_requested.emit(clicked_artist)
                                return True
                        elif col == COL_ALBUM:
                            if self.delegate.is_over_clickable_text(index, pos):
                                track = index.data(Qt.ItemDataRole.UserRole)
                                if track and track.album_key:
                                    self.view.album_requested.emit(track.album_key)
                                    return True
                        elif col == COL_GENRE:
                            clicked_genre = self.delegate.get_genre_at_pos(index, pos)
                            if clicked_genre:
                                self.view.genre_requested.emit(clicked_genre)
                                return True

            elif event.type() in (QEvent.Type.DragEnter, QEvent.Type.DragMove, QEvent.Type.Drop, QEvent.Type.DragLeave):
                if event.type() == QEvent.Type.DragEnter:
                    self.table.dragEnterEvent(event)
                    return True
                elif event.type() == QEvent.Type.DragMove:
                    self.table.dragMoveEvent(event)
                    return True
                elif event.type() == QEvent.Type.Drop:
                    self.table.dropEvent(event)
                    return True
                elif event.type() == QEvent.Type.DragLeave:
                    self.table.dragLeaveEvent(event)
                    return True

        except RuntimeError:
            return False

        return super().eventFilter(obj, event)


class HoverableCoverLabel(QLabel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.is_hovered = False
        self.setMouseTracking(True)
        self.custom_playlist = True

    def enterEvent(self, event):
        self.is_hovered = True
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self.is_hovered = False
        self.update()
        super().leaveEvent(event)

    def paintEvent(self, event):
        super().paintEvent(event)
        
        if self.custom_playlist and self.is_hovered:
            painter = QPainter(self)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            
            rect = self.rect()
            clip_path = QPainterPath()
            clip_path.addRoundedRect(QRectF(rect), 8.0, 8.0)
            painter.setClipPath(clip_path)
            
            # Dark overlay
            painter.fillRect(rect, QColor(0, 0, 0, 150))
            
            # Pencil symbol ✏ center & slightly above center
            font = QFont("Segoe UI", 26)
            font.setBold(True)
            painter.setFont(font)
            painter.setPen(QColor("#FFFFFF"))
            
            pencil_text = "✏"
            fm = painter.fontMetrics()
            pencil_w = fm.horizontalAdvance(pencil_text)
            pencil_h = fm.height()
            
            pencil_x = (rect.width() - pencil_w) // 2
            pencil_y = (rect.height() - pencil_h) // 2 - 12
            
            painter.drawText(pencil_x, pencil_y + fm.ascent(), pencil_text)
            
            # "Choose Photo" text below pencil
            text_font = QFont("Segoe UI", 10, QFont.Weight.Medium)
            painter.setFont(text_font)
            text_val = "choose photo"
            text_fm = painter.fontMetrics()
            text_w = text_fm.horizontalAdvance(text_val)
            
            text_x = (rect.width() - text_w) // 2
            text_y = pencil_y + fm.height() + 4
            
            painter.drawText(text_x, text_y + text_fm.ascent(), text_val)
            painter.end()


class PlaylistPageView(QWidget):
    track_double_clicked = pyqtSignal(str)
    artist_requested = pyqtSignal(str)
    genre_requested = pyqtSignal(str)
    album_requested = pyqtSignal(str)
    play_all_requested = pyqtSignal(list, bool)
    playlist_deleted = pyqtSignal(str) # Emitted to notify container to close the tab

    def __init__(self, playlist_id: str, store: LibraryStore, engine=None, parent=None):
        super().__init__(parent)
        self.main_window = parent
        self.playlist_id = playlist_id
        self.store = store
        self.engine = engine
        self.playlist_tracks: list[Track] = []
        self.is_smart = playlist_id.startswith("smart_")
        self.active_sort_column, self.active_sort_ascending = self.store.get_playlist_sort_state(playlist_id)

        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(0, 0, 0, 0)
        self.main_layout.setSpacing(0)

        # Main scroll area wrapping the whole page
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.scroll.setObjectName("playlistScrollArea")
        self.scroll.setStyleSheet("#playlistScrollArea { background: transparent; border: none; }")
        self.main_layout.addWidget(self.scroll)

        # Scroll content widget
        self.scroll_content = QWidget()
        self.scroll_content.setObjectName("playlistScrollContent")
        self.scroll_content.setStyleSheet("#playlistScrollContent { background: transparent; }")
        self.scroll_layout = QVBoxLayout(self.scroll_content)
        self.scroll_layout.setContentsMargins(24, 24, 24, 24)
        self.scroll_layout.setSpacing(24)
        self.scroll.setWidget(self.scroll_content)

        # Header Widget
        self.header_widget = None

        # Table View
        self.table = None

        self.animation_timer = QTimer(self)
        self.animation_timer.setInterval(120)
        self.animation_timer.timeout.connect(self._on_animation_tick)

        if self.engine:
            self.engine.playback_state_changed.connect(self._on_playback_changed)
            self.engine.track_changed.connect(self._on_playback_changed)

        # Connect to store updates
        self.store.playlists_changed.connect(self._on_playlists_changed_signal)
        self.store.tracks_added.connect(self._on_tracks_changed_signal)
        self.store.track_removed.connect(self._on_tracks_changed_signal)
        self.store.track_updated.connect(self._on_tracks_changed_signal)

        self.refresh()
        self._update_animation_timer()

    def _on_playlists_changed_signal(self, pl_id: str) -> None:
        if pl_id == self.playlist_id:
            self.refresh()

    def _on_tracks_changed_signal(self, *args) -> None:
        self.refresh()

    def resize_table_to_contents(self) -> None:
        try:
            if self.table is not None:
                # Safe liveness check
                _ = self.table.parent()
                model = self.table.model()
                if not model:
                    return
                num_rows = model.rowCount()
                row_height = self.table.verticalHeader().defaultSectionSize() or 36
                header_height = self.table.horizontalHeader().height() or 28
                if num_rows == 0:
                    self.table.setFixedHeight(0)
                else:
                    total_height = num_rows * row_height + header_height + 4
                    self.table.setFixedHeight(total_height)
        except RuntimeError:
            self.table = None

    def resizeEvent(self, event):
        super().resizeEvent(event)
        QTimer.singleShot(0, self.resize_table_to_contents)

    def showEvent(self, event):
        super().showEvent(event)
        QTimer.singleShot(0, self.resize_table_to_contents)

    def _on_playback_changed(self, *args) -> None:
        self._update_animation_timer()
        try:
            if self.table is not None:
                _ = self.table.parent()
                viewport = self.table.viewport()
                if viewport:
                    viewport.update()
        except RuntimeError:
            self.table = None

    def _on_animation_tick(self) -> None:
        try:
            if self.table is not None:
                _ = self.table.parent()
                viewport = self.table.viewport()
                if viewport:
                    viewport.update()
        except RuntimeError:
            self.table = None

    def _update_animation_timer(self) -> None:
        if self.engine and self.engine.is_playing():
            if not self.animation_timer.isActive():
                self.animation_timer.start()
        else:
            if self.animation_timer.isActive():
                self.animation_timer.stop()

    def refresh(self) -> None:
        # Resolve active theme
        theme_key = self.store.cache.settings.theme
        theme = THEMES.get(theme_key, THEMES[DEFAULT_THEME])
        from ui.theme import apply_theme_vars

        # 1. Clear C++ reference first, then clean up old widgets
        self.table = None
        while self.scroll_layout.count():
            child = self.scroll_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()

        # 2. Re-query tracks
        self.playlist_tracks = self.store.get_playlist_tracks(self.playlist_id)

        # 3. Resolve metadata
        if self.is_smart:
            pl_name = {
                "smart_recently_added": "Recently Added",
                "smart_favorites": "Favorites",
                "smart_recently_played": "Recently Played",
                "smart_most_played": "Most Played 🔥",
            }.get(self.playlist_id, "Smart Playlist")
            cover_path = None
        else:
            pl_obj = self.store.get_playlist(self.playlist_id)
            if not pl_obj:
                # Playlist was deleted
                return
            pl_name = pl_obj.name
            cover_path = pl_obj.cover_path

        total_duration = sum(t.duration for t in self.playlist_tracks)
        tracks_word = "Track" if len(self.playlist_tracks) == 1 else "Tracks"
        stats_text = f"{len(self.playlist_tracks)} {tracks_word} • Total: {format_duration(total_duration)}"

        # ------------------------------------------------------------------
        # Header Row
        # ------------------------------------------------------------------
        self.header_widget = QWidget()
        self.header_widget.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        header_layout = QHBoxLayout(self.header_widget)
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_layout.setSpacing(24)

        # Large Playlist Cover Image
        self.art_container = QWidget()
        self.art_container.setFixedSize(160, 160)
        self.art_container.setStyleSheet(apply_theme_vars("border-radius: 8px; background-color: var(--surface);", theme))
        art_box = QHBoxLayout(self.art_container)
        art_box.setContentsMargins(0, 0, 0, 0)

        self.art_label = HoverableCoverLabel()
        self.art_label.setFixedSize(160, 160)
        self.art_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.art_label.custom_playlist = not self.is_smart
        art_box.addWidget(self.art_label)

        # Load cover / Generate collage
        has_custom_cover = False
        if self.is_smart:
            from ui.views.playlists_view import get_smart_playlist_cover
            smart_cover = get_smart_playlist_cover(self.playlist_id, size=160, theme_key=theme_key)
            self.art_label.setPixmap(smart_cover)
            has_custom_cover = True
        else:
            if cover_path and os.path.exists(cover_path):
                pix = QPixmap(cover_path)
                if not pix.isNull():
                    scaled = pix.scaled(
                        160, 160,
                        Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                        Qt.TransformationMode.SmoothTransformation,
                    )
                    self.art_label.setPixmap(scaled)
                    has_custom_cover = True

        if not has_custom_cover:
            from ui.views.playlists_view import get_playlist_collage
            collage_px = get_playlist_collage(self.store, self.playlist_id, size=160, theme=theme)
            self.art_label.setPixmap(collage_px)

        # Cover column layout to support "✕ Revert Cover" button
        cover_col = QVBoxLayout()
        cover_col.setContentsMargins(0, 0, 0, 0)
        cover_col.setSpacing(6)
        cover_col.addWidget(self.art_container)

        # Cover interactions (only for custom playlists)
        if not self.is_smart:
            self.art_label.setCursor(Qt.CursorShape.PointingHandCursor)
            self.art_label.setToolTip("Click to choose playlist photo")
            self.art_label.mousePressEvent = lambda e: self._change_cover() if e.button() == Qt.MouseButton.LeftButton else None
            
            if has_custom_cover:
                revert_btn = QPushButton("✕ Revert Cover")
                revert_btn.setObjectName("textButton")
                revert_btn.setToolTip("Revert to automatic collage cover art")
                revert_btn.setCursor(Qt.CursorShape.PointingHandCursor)
                revert_btn.clicked.connect(self._revert_cover)
                cover_col.addWidget(revert_btn)
            else:
                cover_col.addStretch()
        else:
            cover_col.addStretch()

        header_layout.addLayout(cover_col)

        # Info text column
        info_layout = QVBoxLayout()
        info_layout.setSpacing(4)

        # pl_type_desc label ("SMART PLAYLIST" / "CUSTOM PLAYLIST") has been deleted per user request.

        self.title_label = QLabel(pl_name)
        self.title_label.setFont(QFont("Segoe UI", 24, QFont.Weight.Bold))
        self.title_label.setStyleSheet(apply_theme_vars("color: var(--text_primary);", theme))
        info_layout.addWidget(self.title_label)

        self.stats_lbl = QLabel(stats_text)
        self.stats_lbl.setStyleSheet(apply_theme_vars("color: var(--text_secondary); font-size: 13px;", theme))
        info_layout.addWidget(self.stats_lbl)
        info_layout.addStretch()

        # Action Buttons row
        btn_layout = QHBoxLayout()
        play_btn = QPushButton("▶  Play All")
        play_btn.setObjectName("accentButton")
        play_btn.clicked.connect(lambda: self._play_playlist_tracks(shuffle=False))

        shuf_btn = QPushButton("🔀  Shuffle")
        shuf_btn.clicked.connect(lambda: self._play_playlist_tracks(shuffle=True))

        btn_layout.addWidget(play_btn)
        btn_layout.addWidget(shuf_btn)

        if not self.is_smart:
            # Custom Playlists can be Renamed or Deleted
            rename_btn = QPushButton("✏  Rename")
            rename_btn.clicked.connect(self._rename_playlist)
            delete_btn = QPushButton("🗑  Delete")
            delete_btn.clicked.connect(self._delete_playlist)
            btn_layout.addWidget(rename_btn)
            btn_layout.addWidget(delete_btn)

        btn_layout.addStretch()
        info_layout.addLayout(btn_layout)

        header_layout.addLayout(info_layout, stretch=1)
        self.scroll_layout.addWidget(self.header_widget)

        # ------------------------------------------------------------------
        # Tracks Table
        # ------------------------------------------------------------------
        if not self.playlist_tracks:
            # Empty playlist placeholder
            empty_state = QLabel("Drag songs here or use right-click menus to add songs to this playlist.")
            empty_state.setAlignment(Qt.AlignmentFlag.AlignCenter)
            empty_state.setStyleSheet(apply_theme_vars("color: var(--text_secondary); font-size: 13px; margin: 40px;", theme))
            
            # Still need to support drops on empty state for custom playlists!
            if not self.is_smart:
                empty_state.setAcceptDrops(True)
                empty_state.dragEnterEvent = lambda e: e.acceptProposedAction() if (e.mimeData().hasFormat("application/x-aura-tracks") or e.mimeData().hasText()) else None
                empty_state.dragMoveEvent = lambda e: e.acceptProposedAction() if (e.mimeData().hasFormat("application/x-aura-tracks") or e.mimeData().hasText()) else None
                def handle_empty_drop(event):
                    mime = event.mimeData()
                    text = mime.text()
                    paths = [p.strip() for p in text.split("\n") if p.strip()]
                    if paths:
                        self.store.add_tracks_to_playlist(self.playlist_id, paths)
                        event.acceptProposedAction()
                empty_state.dropEvent = handle_empty_drop
            
            self.scroll_layout.addWidget(empty_state)
            self.scroll_layout.addStretch(1)
            return

        self.table = AuraDragTableView()
        self.table.store = self.store
        # Enable dragging & dropping for custom playlists and Favorites
        can_reorder_and_sort = (not self.is_smart) or (self.playlist_id == "smart_favorites")
        if can_reorder_and_sort:
            self.table.setAcceptDrops(True)
            self.table.setDragDropMode(QAbstractItemView.DragDropMode.DragDrop)
            self.table.reordered.connect(self._on_table_reordered)
            self.table.dropped_paths.connect(self._on_table_dropped_paths)
        else:
            self.table.setAcceptDrops(False)
            self.table.setDragDropMode(QAbstractItemView.DragDropMode.DragOnly)

        model = PlaylistTracksTableModel(self.playlist_tracks, self)
        self.table.setModel(model)
        
        if can_reorder_and_sort:
            self.table.horizontalHeader().sectionClicked.connect(self._on_header_clicked)
        
        # Restore preserved active sort state if valid
        if self.active_sort_column != -1:
            sort_order = Qt.SortOrder.AscendingOrder if self.active_sort_ascending else Qt.SortOrder.DescendingOrder
            model.sort(self.active_sort_column, sort_order)

        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(36)
        self.table.setShowGrid(False)

        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.table.horizontalHeader().setStretchLastSection(False)
        self.table.setColumnWidth(COL_TITLE, 230)
        self.table.setColumnWidth(COL_ARTISTS, 170)
        self.table.setColumnWidth(COL_ALBUM, 170)
        self.table.setColumnWidth(COL_GENRE, 110)
        self.table.setColumnWidth(COL_DURATION, 80)
        self.table.resize_helper = AdjacentResizeHelper(self.table.horizontalHeader(), self.store, "playlist_table")

        delegate = PlaylistTrackHoverDelegate(self.table, self)
        self.table.setItemDelegate(delegate)
        self.table.setMouseTracking(True)
        hover_filter = PlaylistHoverEventFilter(self.table, delegate, self)
        self.table.viewport().installEventFilter(hover_filter)

        # Double-click handler
        self.table.doubleClicked.connect(self._on_row_double_clicked)

        # Context menu handler
        self.table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._show_context_menu)

        # Turn off native scrollbars to allow full-page scrolling
        self.table.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.table.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.table.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        self.scroll_layout.addWidget(self.table, stretch=0)
        self.scroll_layout.addStretch(1)

        # Recalculate height
        QTimer.singleShot(0, self.resize_table_to_contents)

    def _play_playlist_tracks(self, shuffle: bool) -> None:
        valid_paths = [t.path for t in self.playlist_tracks if not t.file_missing]
        if valid_paths:
            self.play_all_requested.emit(valid_paths, shuffle)

    def _change_cover(self) -> None:
        if self.is_smart:
            return
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Choose Playlist Cover Photo", "",
            "Image Files (*.png *.jpg *.jpeg *.webp *.bmp)"
        )
        if file_path:
            self.store.set_playlist_cover(self.playlist_id, file_path)
            self.refresh()

    def _revert_cover(self) -> None:
        if self.is_smart:
            return
        self.store.set_playlist_cover(self.playlist_id, None)
        self.refresh()

    def _rename_playlist(self) -> None:
        pl_obj = self.store.get_playlist(self.playlist_id)
        if not pl_obj:
            return
        name, ok = QInputDialog.getText(
            self, "Rename Playlist",
            f"Rename '{pl_obj.name}' to:",
            text=pl_obj.name
        )
        if ok and name.strip() and name.strip() != pl_obj.name:
            self.store.rename_playlist(self.playlist_id, name.strip())
            self.refresh()

    def _delete_playlist(self) -> None:
        pl_obj = self.store.get_playlist(self.playlist_id)
        if not pl_obj:
            return
        reply = QMessageBox.question(
            self, "Delete Playlist?",
            f"Are you sure you want to delete the playlist '{pl_obj.name}'?\n\nThis action cannot be undone.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            self.store.delete_playlist(self.playlist_id)
            self.playlist_deleted.emit(self.playlist_id)

    def _on_table_reordered(self, from_row: int, to_row: int) -> None:
        if self.active_sort_column != -1:
            try:
                if self.table is not None:
                    model = self.table.model()
                    if model and hasattr(model, "_tracks"):
                        sorted_paths = [t.path for t in model._tracks]
                        self.store.set_playlist_track_paths(self.playlist_id, sorted_paths)
            except Exception:
                pass
            self.active_sort_column = -1
            self.store.set_playlist_sort_state(self.playlist_id, -1, True)

        try:
            if self.table is not None:
                _ = self.table.parent()
                model = self.table.model()
                if model and hasattr(model, "_sort_column"):
                    model._sort_column = -1
        except RuntimeError:
            self.table = None

        self.store.reorder_playlist(self.playlist_id, from_row, to_row)
        self.refresh()

    def _on_header_clicked(self, column: int) -> None:
        try:
            if self.table is not None:
                model = self.table.model()
                if model:
                    if model._sort_column == column:
                        ascending = not model._sort_ascending
                    else:
                        ascending = True
                    
                    self.active_sort_column = column
                    self.active_sort_ascending = ascending
                    
                    order = Qt.SortOrder.AscendingOrder if ascending else Qt.SortOrder.DescendingOrder
                    model.sort(column, order)
                    model.headerDataChanged.emit(Qt.Orientation.Horizontal, 0, model.columnCount() - 1)
        except RuntimeError:
            self.table = None

    def _on_table_dropped_paths(self, paths: list[str], to_row: int = -1) -> None:
        self.store.add_tracks_to_playlist(self.playlist_id, paths, at_index=None)
        self.refresh()

    def _on_row_double_clicked(self, index) -> None:
        try:
            if self.table is not None:
                _ = self.table.parent()
                model = self.table.model()
                if not model:
                    return
                track = model.track_at(index.row())
                if track:
                    if track.file_missing:
                        return
                    self.track_double_clicked.emit(track.path)
        except RuntimeError:
            self.table = None

    def _show_context_menu(self, pos) -> None:
        try:
            if not self.table:
                return
            _ = self.table.parent()
            index = self.table.indexAt(pos)
            if not index.isValid():
                return
            model = self.table.model()
            if not model:
                return
            track = model.track_at(index.row())
            if not track:
                return
        except RuntimeError:
            self.table = None
            return

        menu = QMenu(self)

        # Style menu and its submenus with playlist theme colors
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

        # Play / Play Next / Queue
        play_act = QAction("Play", self)
        play_next_act = QAction("Play Next", self)
        enqueue_act = QAction("Add to Queue", self)
        
        play_act.triggered.connect(lambda: self.track_double_clicked.emit(track.path))
        if self.engine:
            play_next_act.triggered.connect(lambda: self.engine.play_next(track.path))
            enqueue_act.triggered.connect(lambda: self.engine.enqueue(track.path))
        
        menu.addAction(play_act)
        menu.addAction(play_next_act)
        menu.addAction(enqueue_act)
        menu.addSeparator()

        # Favorites toggling
        is_fav = self.store.is_favorite(track.path)
        fav_text = "Remove from Favorites" if is_fav else "Add to Favorites"
        fav_act = QAction(fav_text, self)
        fav_act.triggered.connect(lambda: self.store.toggle_favorite(track.path))
        menu.addAction(fav_act)

        # Add to Custom Playlist sub-menu
        add_to_pl_menu = QMenu("Add to Playlist", self)
        add_to_pl_menu.setStyleSheet(qss)
        custom_playlists = [p for p in self.store.all_playlists() if not p.id.startswith("smart_")]
        if custom_playlists:
            for pl in custom_playlists:
                act = QAction(pl.name, self)
                # Capture playlist id in lambda
                act.triggered.connect(lambda checked, pl_id=pl.id: self.store.add_tracks_to_playlist(pl_id, [track.path]))
                add_to_pl_menu.addAction(act)
        else:
            no_pl_act = QAction("No custom playlists", self)
            no_pl_act.setEnabled(False)
            add_to_pl_menu.addAction(no_pl_act)
        menu.addMenu(add_to_pl_menu)

        # Remove from this playlist (only if custom playlist or smart_favorites)
        can_remove = (not self.is_smart) or (self.playlist_id == "smart_favorites")
        if can_remove:
            remove_act = QAction("Remove from this Playlist", self)
            if self.playlist_id == "smart_favorites":
                remove_act.triggered.connect(lambda: self.store.toggle_favorite(track.path))
            else:
                # Custom playlist: remove by index
                remove_act.triggered.connect(lambda: self._remove_track_by_index(index.row()))
            menu.addAction(remove_act)

        menu.exec(self.table.mapToGlobal(pos))

    def _remove_track_by_index(self, row: int) -> None:
        try:
            track = None
            if self.table is not None:
                model = self.table.model()
                if model:
                    track = model.track_at(row)
            if not track and 0 <= row < len(self.playlist_tracks):
                track = self.playlist_tracks[row]
                
            if track:
                self.store.remove_track_from_playlist(self.playlist_id, track.path)
                self.refresh()
        except Exception as e:
            print(f"Error removing track: {e}")
