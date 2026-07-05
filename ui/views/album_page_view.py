"""
AlbumPageView: Dedicated page displaying details for a specific album,
including disc-grouped track tables, stats, and a large album cover.
"""

from __future__ import annotations

import math
import time

from PyQt6.QtCore import (
    Qt, pyqtSignal, QTimer, QRect, QPoint, QRectF, QSize, QEvent, QObject,
    QAbstractTableModel, QModelIndex
)
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QSplitter,
    QTableView, QHeaderView, QAbstractItemView, QStyledItemDelegate, QStyle, QStyleOptionViewItem,
    QScrollArea, QSizePolicy
)
from PyQt6.QtGui import QFont, QColor, QPainter, QBrush, QPen, QPixmap

from core.library_store import LibraryStore
from core.models import Track
from core.metadata_reader import get_album_art
from ui.theme import THEMES, DEFAULT_THEME
from ui.widgets.adjacent_resize_helper import AdjacentResizeHelper

COL_TRACK_NO = 0
COL_TITLE = 1
COL_ARTISTS = 2
COL_GENRE = 3
COL_DURATION = 4
COLUMN_HEADERS = ["#", "Title", "Artist(s)", "Genre", "Duration"]


def format_duration(seconds: float) -> str:
    if seconds <= 0:
        return "--:--"
    m, s = divmod(int(seconds), 60)
    return f"{m}:{s:02d}"


class AlbumTracksTableModel(QAbstractTableModel):
    def __init__(self, tracks: list[Track], parent=None):
        super().__init__(parent)
        self._tracks = sorted(
            tracks,
            key=lambda t: (t.disc_number, t.track_number if t.track_number is not None else 999, t.title.lower())
        )
        self._currently_playing_path = None
        self._danger_color = "#E05C5C"

    def rowCount(self, parent=QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self._tracks)

    def columnCount(self, parent=QModelIndex()) -> int:
        return 0 if parent.isValid() else len(COLUMN_HEADERS)

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):
        if orientation == Qt.Orientation.Horizontal and role == Qt.ItemDataRole.DisplayRole:
            return COLUMN_HEADERS[section]
        return None

    def data(self, index: QModelIndex, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None
        track = self._tracks[index.row()]
        col = index.column()

        if role == Qt.ItemDataRole.DisplayRole:
            if col == COL_TRACK_NO:
                return str(track.track_number) if track.track_number is not None else "-"
            if col == COL_TITLE:
                return track.title
            if col == COL_ARTISTS:
                return ", ".join(track.artists)
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


class AlbumTrackHoverDelegate(QStyledItemDelegate):
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
        if col not in (COL_TRACK_NO, COL_TITLE, COL_ARTISTS, COL_GENRE):
            super().paint(painter, option, index)
            return

        # Prepare style option
        opt = QStyleOptionViewItem(option)
        self.initStyleOption(opt, index)
        opt.text = ""

        widget = option.widget
        style = widget.style() if widget else None
        if style:
            style.drawPrimitive(QStyle.PrimitiveElement.PE_PanelItemViewItem, opt, painter, widget)

        track = index.data(Qt.ItemDataRole.UserRole)
        if not track:
            super().paint(painter, option, index)
            return

        painter.save()

        # Determine states
        is_current = False
        is_playing = False
        if self.view.engine:
            is_current = (self.view.engine.get_current_track_path() == track.path)
            is_playing = is_current and self.view.engine.is_playing()

        is_row_hovered = (index.row() == self.hovered_row)

        theme_key = self.view.store.cache.settings.theme
        theme = THEMES.get(theme_key, THEMES[DEFAULT_THEME])

        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # Get cell geometry
        rect = option.rect.adjusted(6, 0, -6, 0)
        fm = option.fontMetrics
        y_baseline = rect.top() + (rect.height() + fm.ascent() - fm.descent()) // 2

        if col == COL_TRACK_NO:
            # Draw Equalizer Animation if current track is PLAYING
            if is_playing:
                max_bar_h = 12
                bar_w = 2
                spacing = 1
                eq_w = 3 * bar_w + 2 * spacing
                eq_x = rect.left() + (rect.width() - eq_w) // 2
                eq_y = rect.top() + (rect.height() - max_bar_h) // 2

                t = time.time()
                h1 = 0.2 + 0.7 * abs(math.sin(t * 9.0))
                h2 = 0.3 + 0.6 * abs(math.sin(t * 13.0 + 1.5))
                h3 = 0.1 + 0.8 * abs(math.sin(t * 7.5 + 3.0))

                heights = [h1 * max_bar_h, h2 * max_bar_h, h3 * max_bar_h]

                painter.save()
                painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(QBrush(QColor(theme['accent'])))
                for i, h in enumerate(heights):
                    x = eq_x + i * (bar_w + spacing)
                    y = (eq_y + max_bar_h) - h
                    painter.drawRect(QRectF(x, y, bar_w, h))
                painter.restore()

            # Draw Play icon if PAUSED + Hovered
            elif is_row_hovered:
                painter.save()
                font = QFont()
                font.setPointSize(9)
                font.setBold(True)
                painter.setFont(font)
                painter.setPen(QColor(theme['accent']))
                painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, "▶")
                painter.restore()

            # Draw Track Number otherwise
            else:
                painter.save()
                painter.setPen(QColor(theme['accent'] if is_current else theme['text_secondary']))
                track_no_str = str(track.track_number) if track.track_number is not None else "-"
                painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, track_no_str)
                painter.restore()

        elif col == COL_TITLE:
            title_text = track.title or "Unknown Title"
            elided_title = fm.elidedText(title_text, Qt.TextElideMode.ElideRight, rect.width())

            font = painter.font()
            if is_current:
                font.setBold(True)
                painter.setPen(QColor(theme['accent']))
            else:
                font.setBold(False)
                painter.setPen(QColor(theme['text_primary']))
            painter.setFont(font)

            painter.drawText(rect.left(), y_baseline, elided_title)

        elif col == COL_ARTISTS:
            artists_text = ", ".join(track.artists)
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
                        artist_hovered = is_row_hovered and rect.contains(self.mouse_pos) and artist_rect.contains(self.mouse_pos)

                        font = painter.font()
                        font.setUnderline(artist_hovered)
                        painter.setFont(font)

                        if option.state & QStyle.StateFlag.State_Selected:
                            painter.setPen(QColor(theme['text_primary']))
                        else:
                            painter.setPen(QColor(theme['accent'] if artist_hovered else theme['text_secondary']))

                        painter.drawText(x_offset, y_baseline, elided_artist)
                    else:
                        if x_offset + ellipsis_width <= max_x + 5:
                            painter.setPen(QColor(theme['text_secondary']))
                            painter.drawText(x_offset, y_baseline, ellipsis)
                    break
                else:
                    artist_rect = QRect(x_offset, rect.top(), artist_width, rect.height())
                    artist_hovered = is_row_hovered and rect.contains(self.mouse_pos) and artist_rect.contains(self.mouse_pos)

                    font = painter.font()
                    font.setUnderline(artist_hovered)
                    painter.setFont(font)

                    if option.state & QStyle.StateFlag.State_Selected:
                        painter.setPen(QColor(theme['text_primary']))
                    else:
                        painter.setPen(QColor(theme['accent'] if artist_hovered else theme['text_secondary']))

                    painter.drawText(x_offset, y_baseline, artist)
                    x_offset += artist_width

                    if next_delim:
                        font.setUnderline(False)
                        painter.setFont(font)
                        painter.setPen(QColor(theme['text_secondary']))
                        painter.drawText(x_offset, y_baseline, next_delim)
                        x_offset += delim_width

        elif col == COL_GENRE:
            genre_text = track.genre or "—"
            if genre_text and genre_text != "—" and genre_text != "-":
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
                            genre_hovered = is_row_hovered and rect.contains(self.mouse_pos) and genre_rect.contains(self.mouse_pos)

                            font = painter.font()
                            font.setUnderline(genre_hovered)
                            painter.setFont(font)

                            if option.state & QStyle.StateFlag.State_Selected:
                                painter.setPen(QColor(theme['text_primary']))
                            else:
                                painter.setPen(QColor(theme['accent'] if genre_hovered else theme['text_secondary']))

                            painter.drawText(x_offset, y_baseline, elided_genre)
                        else:
                            if x_offset + ellipsis_width <= max_x + 5:
                                painter.setPen(QColor(theme['text_secondary']))
                                painter.drawText(x_offset, y_baseline, ellipsis)
                        break
                    else:
                        genre_rect = QRect(x_offset, rect.top(), genre_width, rect.height())
                        genre_hovered = is_row_hovered and rect.contains(self.mouse_pos) and genre_rect.contains(self.mouse_pos)

                        font = painter.font()
                        font.setUnderline(genre_hovered)
                        painter.setFont(font)

                        if option.state & QStyle.StateFlag.State_Selected:
                            painter.setPen(QColor(theme['text_primary']))
                        else:
                            painter.setPen(QColor(theme['accent'] if genre_hovered else theme['text_secondary']))

                        painter.drawText(x_offset, y_baseline, genre)
                        x_offset += genre_width

                        if next_delim:
                            font.setUnderline(False)
                            painter.setFont(font)
                            painter.setPen(QColor(theme['text_secondary']))
                            painter.drawText(x_offset, y_baseline, next_delim)
                            x_offset += delim_width
            else:
                painter.setPen(QColor(theme['text_secondary']))
                painter.drawText(rect, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, genre_text)

        painter.restore()


class AlbumHoverEventFilter(QObject):
    def __init__(self, table, delegate, view):
        super().__init__(table)
        self.table = table
        self.delegate = delegate
        self.view = view

    def eventFilter(self, obj, event):
        if event.type() == QEvent.Type.MouseMove:
            pos = event.position().toPoint()
            self.delegate.set_mouse_pos(pos)

            index = self.table.indexAt(pos)
            if index.isValid():
                self.delegate.hovered_row = index.row()
                col = index.column()
                if col == COL_ARTISTS:
                    clicked_artist = self.delegate.get_artist_at_pos(index, pos)
                    if clicked_artist:
                        self.table.setCursor(Qt.CursorShape.PointingHandCursor)
                    else:
                        self.table.setCursor(Qt.CursorShape.ArrowCursor)
                elif col == COL_GENRE:
                    clicked_genre = self.delegate.get_genre_at_pos(index, pos)
                    if clicked_genre:
                        self.table.setCursor(Qt.CursorShape.PointingHandCursor)
                    else:
                        self.table.setCursor(Qt.CursorShape.ArrowCursor)
                elif col == COL_TRACK_NO:
                    self.table.setCursor(Qt.CursorShape.PointingHandCursor)
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
                    if col == COL_TRACK_NO:
                        model = self.table.model()
                        if model:
                            self.view._on_row_double_clicked(index, model)
                            return True
                    elif col == COL_ARTISTS:
                        clicked_artist = self.delegate.get_artist_at_pos(index, pos)
                        if clicked_artist:
                            self.view.artist_requested.emit(clicked_artist)
                            return True
                    elif col == COL_GENRE:
                        clicked_genre = self.delegate.get_genre_at_pos(index, pos)
                        if clicked_genre:
                            if hasattr(self.view, "genre_requested"):
                                self.view.genre_requested.emit(clicked_genre)
                            return True

        return super().eventFilter(obj, event)


class AlbumPageView(QWidget):
    track_double_clicked = pyqtSignal(str)
    album_requested = pyqtSignal(str)
    artist_requested = pyqtSignal(str)
    genre_requested = pyqtSignal(str)
    play_all_requested = pyqtSignal(list, bool)

    def __init__(self, album_key: str, store: LibraryStore, engine=None, parent=None):
        super().__init__(parent)
        self.main_window = parent
        self.album_key = album_key
        self.store = store
        self.engine = engine
        self.album_tracks: list[Track] = []
        self._tables = []

        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(0, 0, 0, 0)
        self.main_layout.setSpacing(0)

        # Main scroll area wrapping the whole page
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.scroll.setObjectName("albumScrollArea")
        self.scroll.setStyleSheet("#albumScrollArea { background: transparent; border: none; }")
        self.main_layout.addWidget(self.scroll)

        # Scroll content widget
        self.scroll_content = QWidget()
        self.scroll_content.setObjectName("albumScrollContent")
        self.scroll_content.setStyleSheet("#albumScrollContent { background: transparent; }")
        self.scroll_layout = QVBoxLayout(self.scroll_content)
        self.scroll_layout.setContentsMargins(24, 24, 24, 24)
        self.scroll_layout.setSpacing(24)
        self.scroll.setWidget(self.scroll_content)

        # We will dynamically populate this layout on refresh()
        self.header_widget = QWidget()
        self.scroll_layout.addWidget(self.header_widget)

        self.tables_container = QWidget()
        self.tables_layout = QVBoxLayout(self.tables_container)
        self.tables_layout.setContentsMargins(0, 0, 0, 0)
        self.tables_layout.setSpacing(16)
        self.scroll_layout.addWidget(self.tables_container)

        self.animation_timer = QTimer(self)
        self.animation_timer.setInterval(120)
        self.animation_timer.timeout.connect(self._on_animation_tick)

        if self.engine:
            self.engine.playback_state_changed.connect(self._on_playback_changed)
            self.engine.track_changed.connect(self._on_playback_changed)

        self.refresh()
        self._update_animation_timer()

    def resize_tables_to_contents(self) -> None:
        for table in self._tables:
            model = table.model()
            if not model:
                continue
            num_rows = model.rowCount()
            row_height = table.verticalHeader().defaultSectionSize() or 36
            header_height = table.horizontalHeader().height() or 28
            if num_rows == 0:
                table.setFixedHeight(0)
            else:
                total_height = num_rows * row_height + header_height + 4
                table.setFixedHeight(total_height)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        QTimer.singleShot(0, self.resize_tables_to_contents)

    def showEvent(self, event):
        super().showEvent(event)
        QTimer.singleShot(0, self.resize_tables_to_contents)

    def _on_playback_changed(self, *args) -> None:
        self._update_animation_timer()
        self.refresh_tables_viewports()

    def _on_animation_tick(self) -> None:
        self.refresh_tables_viewports()

    def refresh_tables_viewports(self):
        # Refresh any instantiated QTableViews
        for child in self.tables_container.findChildren(QTableView):
            child.viewport().update()

    def _update_animation_timer(self) -> None:
        if self.engine and self.engine.is_playing():
            if not self.animation_timer.isActive():
                self.animation_timer.start()
        else:
            if self.animation_timer.isActive():
                self.animation_timer.stop()

    def refresh(self) -> None:
        self._tables = []

        # Delete and recreate header_widget to prevent overlapping layouts
        if hasattr(self, "header_widget") and self.header_widget is not None:
            self.scroll_layout.removeWidget(self.header_widget)
            self.header_widget.deleteLater()
            self.header_widget = None

        self.header_widget = QWidget()
        self.header_widget.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.scroll_layout.insertWidget(0, self.header_widget)

        # Delete and recreate tables_container to prevent overlapping layouts
        if hasattr(self, "tables_container") and self.tables_container is not None:
            self.scroll_layout.removeWidget(self.tables_container)
            self.tables_container.deleteLater()
            self.tables_container = None

        self.tables_container = QWidget()
        self.tables_layout = QVBoxLayout(self.tables_container)
        self.tables_layout.setContentsMargins(0, 0, 0, 0)
        self.tables_layout.setSpacing(16)
        self.scroll_layout.addWidget(self.tables_container)

        all_tracks = self.store.all_tracks()
        album_tracks = [t for t in all_tracks if t.album_key == self.album_key]
        self.album_tracks = album_tracks
        if not album_tracks:
            return

        # Sort tracks by disc, track number, title
        album_tracks.sort(key=lambda t: (t.disc_number, t.track_number if t.track_number is not None else 999, t.title.lower()))

        first_track = album_tracks[0]
        album_title = first_track.album
        album_artists = first_track.album_artists
        year = first_track.year
        total_duration = sum(t.duration for t in album_tracks)

        # ------------------------------------------------------------------
        # Re-build Header
        # ------------------------------------------------------------------
        header_layout = QHBoxLayout(self.header_widget)
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_layout.setSpacing(24)

        # Resolve active theme
        theme_key = self.store.cache.settings.theme
        theme = THEMES.get(theme_key, THEMES[DEFAULT_THEME])
        from ui.theme import apply_theme_vars

        # Large Album Art on the Left
        self.art_label = QLabel()
        self.art_label.setFixedSize(160, 160)
        self.art_label.setStyleSheet(apply_theme_vars("border-radius: 8px; background-color: var(--surface);", theme))
        
        # Load art
        art_pixmap = get_album_art(first_track.path)
        if art_pixmap and not art_pixmap.isNull():
            scaled = art_pixmap.scaled(
                160, 160,
                Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                Qt.TransformationMode.SmoothTransformation,
            )
            self.art_label.setPixmap(scaled)
        else:
            from ui.svg_icon import get_default_cover
            self.art_label.setText("")
            disc_px = get_default_cover(160, theme, corner_radius=12.0)
            self.art_label.setPixmap(disc_px)

        header_layout.addWidget(self.art_label)

        # Header Info Text
        info_layout = QVBoxLayout()
        info_layout.setSpacing(4)
        
        self.title_label = QLabel(album_title)
        self.title_label.setFont(QFont("Segoe UI", 24, QFont.Weight.Bold))
        self.title_label.setStyleSheet(apply_theme_vars("color: var(--text_primary);", theme))
        info_layout.addWidget(self.title_label)

        # Artists row (underlined clickable)
        artist_row = QHBoxLayout()
        artist_row.setSpacing(4)
        artist_row.setContentsMargins(0, 0, 0, 0)
        
        artists_label = QLabel("by")
        artists_label.setStyleSheet(apply_theme_vars("color: var(--text_secondary);", theme))
        artist_row.addWidget(artists_label)

        for i, art_name in enumerate(album_artists):
            btn = QPushButton(art_name)
            btn.setFlat(True)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setStyleSheet(apply_theme_vars("""
                QPushButton {
                    color: var(--accent);
                    border: none;
                    font-size: 14px;
                    font-weight: bold;
                    padding: 0;
                    background: transparent;
                }
                QPushButton:hover {
                    text-decoration: underline;
                }
            """, theme))
            btn.clicked.connect(lambda checked, name=art_name: self.artist_requested.emit(name))
            artist_row.addWidget(btn)
            
            if i < len(album_artists) - 1:
                comma = QLabel(", ")
                comma.setStyleSheet(apply_theme_vars("color: var(--text_secondary);", theme))
                artist_row.addWidget(comma)
        artist_row.addStretch()
        info_layout.addLayout(artist_row)

        # Year and Stats
        display_year = year[:4] if (year and len(year) >= 4 and year[:4].isdigit()) else year
        tracks_word = "Track" if len(album_tracks) == 1 else "Tracks"
        stats_text = f"{display_year} • {len(album_tracks)} {tracks_word} • Total: {format_duration(total_duration)}"
        self.stats_lbl = QLabel(stats_text)
        self.stats_lbl.setStyleSheet(apply_theme_vars("color: var(--text_secondary); font-size: 13px;", theme))
        info_layout.addWidget(self.stats_lbl)
        info_layout.addStretch()

        # Play / Shuffle / Edit Album buttons
        btn_layout = QHBoxLayout()
        play_btn = QPushButton("▶  Play Album")
        play_btn.setObjectName("accentButton")
        play_btn.clicked.connect(lambda: self._play_album_tracks(album_tracks, shuffle=False))

        shuf_btn = QPushButton("🔀  Shuffle")
        shuf_btn.clicked.connect(lambda: self._play_album_tracks(album_tracks, shuffle=True))

        edit_album_btn = QPushButton("✏  Edit Album")
        edit_album_btn.clicked.connect(self._open_album_editor)

        btn_layout.addWidget(play_btn)
        btn_layout.addWidget(shuf_btn)
        btn_layout.addWidget(edit_album_btn)
        btn_layout.addStretch()
        info_layout.addLayout(btn_layout)

        header_layout.addLayout(info_layout, stretch=1)

        # ------------------------------------------------------------------
        # Group by Disc & Create Tables
        # ------------------------------------------------------------------
        discs = {}
        for t in album_tracks:
            discs.setdefault(t.disc_number, []).append(t)

        sorted_discs = sorted(discs.items())
        show_disc_headers = True

        for disc_no, tracks in sorted_discs:
            if show_disc_headers:
                header_container = QWidget()
                header_h_layout = QHBoxLayout(header_container)
                header_h_layout.setContentsMargins(0, 12, 0, 4)
                header_h_layout.setSpacing(8)

                theme_key = self.store.cache.settings.theme
                theme = THEMES.get(theme_key, THEMES[DEFAULT_THEME])

                from ui.svg_icon import svg_pixmap
                disc_icon_lbl = QLabel()
                disc_icon_lbl.setPixmap(svg_pixmap("disc", theme["text_primary"], 16))

                disc_title = QLabel(f"Disc {disc_no}")
                disc_title.setFont(QFont("Segoe UI", 13, QFont.Weight.Bold))
                disc_title.setStyleSheet(apply_theme_vars("color: var(--text_primary);", theme))

                header_h_layout.addWidget(disc_icon_lbl)
                header_h_layout.addWidget(disc_title)
                header_h_layout.addStretch()

                self.tables_layout.addWidget(header_container)

            table = QTableView()
            model = AlbumTracksTableModel(tracks, self)
            table.setModel(model)
            table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
            table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
            table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
            table.verticalHeader().setVisible(False)
            table.verticalHeader().setDefaultSectionSize(36)
            table.setShowGrid(True)

            table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
            table.horizontalHeader().setStretchLastSection(False)
            table.setColumnWidth(COL_TRACK_NO, 40)
            table.setColumnWidth(COL_TITLE, 250)
            table.setColumnWidth(COL_ARTISTS, 180)
            table.setColumnWidth(COL_GENRE, 120)
            table.setColumnWidth(COL_DURATION, 80)
            table.resize_helper = AdjacentResizeHelper(table.horizontalHeader(), self.store, "album_table")

            delegate = AlbumTrackHoverDelegate(table, self)
            table.setItemDelegate(delegate)
            table.setMouseTracking(True)
            hover_filter = AlbumHoverEventFilter(table, delegate, self)
            table.viewport().installEventFilter(hover_filter)

            # Double-click handler
            table.doubleClicked.connect(lambda index, m=model: self._on_row_double_clicked(index, m))

            # Context menu handler
            table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
            table.customContextMenuRequested.connect(lambda pos, t=table, m=model: self._show_context_menu(pos, t, m))

            # Turn off native scrollbars to allow full-page scrolling
            table.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
            table.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
            table.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

            self.tables_layout.addWidget(table, stretch=0)
            self._tables.append(table)

        # Add a stretch spacer at bottom of tables container
        self.tables_layout.addStretch(1)

        # Trigger table height recalculation
        QTimer.singleShot(0, self.resize_tables_to_contents)

    def _show_context_menu(self, pos, table, model) -> None:
        index = table.indexAt(pos)
        if not index.isValid():
            return
        track = model.track_at(index.row())
        if not track:
            return

        from PyQt6.QtWidgets import QMenu, QMessageBox
        from PyQt6.QtGui import QAction

        menu = QMenu(self)
        edit_action = QAction("Edit Metadata", self)
        remove_action = QAction("Remove Song", self)
        add_playlist_action = QAction("Add to Playlist", self)
        menu.addAction(edit_action)
        menu.addAction(remove_action)
        menu.addAction(add_playlist_action)

        edit_action.triggered.connect(lambda: self._on_edit_metadata(track))
        remove_action.triggered.connect(lambda: self._on_remove_song(track))
        add_playlist_action.triggered.connect(lambda: self._on_add_to_playlist(track))

        menu.exec(table.viewport().mapToGlobal(pos))

    def _on_edit_metadata(self, track) -> None:
        from ui.widgets.metadata_editor_dialog import MetadataEditorDialog
        dialog = MetadataEditorDialog(track, self.store, self)
        dialog.exec()

    def _on_remove_song(self, track) -> None:
        from PyQt6.QtWidgets import QMessageBox
        reply = QMessageBox.question(
            self, "Remove song?",
            f'Remove "{track.title}" from your library?\n\n'
            "This only removes it from the library -- the file itself is not deleted.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            self.store.remove_track(track.path)

    def _on_add_to_playlist(self, track) -> None:
        from PyQt6.QtWidgets import QMessageBox
        QMessageBox.information(
            self, "Coming in Step 7",
            "Playlists are built in Step 7. This menu item will let you add this "
            "track to one once playlists exist."
        )

    def _on_row_double_clicked(self, index, model) -> None:
        track = model.track_at(index.row())
        if track:
            if track.file_missing:
                return
            self.track_double_clicked.emit(track.path)

    def _play_album_tracks(self, tracks: list[Track], shuffle: bool) -> None:
        valid_paths = [t.path for t in tracks if not t.file_missing]
        if valid_paths:
            self.play_all_requested.emit(valid_paths, shuffle)

    def refresh_from_signal(self, *args) -> None:
        try:
            self.refresh()
        except RuntimeError:
            pass

    def _open_album_editor(self) -> None:
        from ui.widgets.album_editor_dialog import AlbumEditorDialog
        if not self.album_tracks:
            return
        dlg = AlbumEditorDialog(self.album_tracks, self.store, self)
        if dlg.exec():
            # Since the dialog updated all tracks in self.album_tracks in-place,
            # we can read the new values directly.
            first_track = self.album_tracks[0]
            new_album = first_track.album
            new_album_artists = first_track.album_artists
            primary_artist = (new_album_artists or ["Unknown Artist"])[0]
            new_key = f"{new_album}::{primary_artist}"

            # Update main window tab if needed
            if hasattr(self, "main_window") and self.main_window and hasattr(self.main_window, "tabs"):
                tabs = self.main_window.tabs
                idx = tabs.indexOf(self)
                if idx != -1:
                    new_tab_title = f"{new_album} | Album"
                    tabs.setTabText(idx, new_tab_title)

            # Update local album key
            self.album_key = new_key
            self.refresh()

    def disconnect_signals(self) -> None:
        try:
            self.store.tracks_added.disconnect(self.refresh_from_signal)
        except (TypeError, RuntimeError):
            pass
        try:
            self.store.track_removed.disconnect(self.refresh_from_signal)
        except (TypeError, RuntimeError):
            pass
        try:
            self.store.track_updated.disconnect(self.refresh_from_signal)
        except (TypeError, RuntimeError):
            pass
