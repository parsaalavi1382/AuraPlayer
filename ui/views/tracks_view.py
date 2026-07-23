"""
Tracks tab: sortable list with Shuffle/Play All at top, per spec.

Step 2 scope: full table display, sorting, and the More (…) menu UI
(Edit Metadata / Remove Song / Add to Playlist) are present and wired
to real LibraryStore mutations where the underlying feature already
exists (Remove Song works now -- it's just a cache mutation). Edit
Metadata opens a confirmation that the feature lands in Step 6, and Add
to Playlist similarly previews to Step 7, so the menu's shape is right
even though those two actions aren't functional yet.

Per-row album-art thumbnails and the three-bar now-playing visualiser
are deferred to Step 3/4 once the playback engine exists to actually
drive "is this row playing" -- right now nothing can ever be playing,
so building the visualiser would just be inert decoration. The column
layout already reserves the visual space for it.

Step 3+4 update: Play All / Shuffle now read track order from the
TABLE MODEL (i.e. whatever order is currently visibly displayed),
not from LibraryStore.all_tracks() directly. Those previously could
silently disagree -- all_tracks() returns dict-insertion order, while
the model may be sorted by a different column -- which meant "Play
All" could start playing in an order that didn't match what the user
was looking at. Shuffle still applies its own randomization on top
once PlaybackEngine.play_all() receives the list; the visible order
only matters as the STARTING order for shuffle=False.
"""

from __future__ import annotations

import math
import time

from PyQt6.QtCore import Qt, pyqtSignal, QPoint, QRect, QEvent, QObject, QTimer, QRectF
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QTableView, QPushButton, QMenu,
    QHeaderView, QStackedWidget, QMessageBox, QAbstractItemView,
    QStyledItemDelegate, QStyle, QStyleOptionViewItem,
)
from PyQt6.QtGui import QAction, QFont, QColor, QPainter, QPainterPath, QBrush, QPen, QPixmap

from core.library_store import LibraryStore
from ui.models.tracks_table_model import TracksTableModel, COL_TITLE, COL_ARTISTS, COL_ALBUM, COL_GENRE, COL_DURATION
from ui.widgets.drag_table_view import AuraDragTableView
from ui.widgets.empty_state import EmptyStateWidget
from ui.widgets.adjacent_resize_helper import AdjacentResizeHelper


class TracksView(QWidget):
    track_double_clicked = pyqtSignal(str)   # track path -> go to Player Screen
    album_requested = pyqtSignal(str)         # album_key -> go to Album page
    artist_requested = pyqtSignal(str)        # artist name -> go to Artist page
    genre_requested = pyqtSignal(str)         # genre name -> go to Genre page
    play_all_requested = pyqtSignal(list, bool)  # track paths, shuffle
    settings_requested = pyqtSignal()         # "Open Settings" empty-state button clicked

    def __init__(self, store: LibraryStore, engine=None, parent=None):
        super().__init__(parent)
        self.store = store
        self.engine = engine

        outer = QVBoxLayout(self)
        outer.setContentsMargins(16, 12, 16, 0)
        outer.setSpacing(8)

        # --- Shuffle / Play All row ---
        action_row = QHBoxLayout()
        self.stats_lbl = QLabel("")
        action_row.addWidget(self.stats_lbl)
        action_row.addStretch()

        self.play_all_btn = QPushButton("▶  Play All")
        self.play_all_btn.setObjectName("accentButton")
        self.play_all_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.shuffle_btn = QPushButton("🔀  Shuffle")
        self.shuffle_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        action_row.addWidget(self.play_all_btn)
        action_row.addWidget(self.shuffle_btn)
        outer.addLayout(action_row)

        self.play_all_btn.clicked.connect(lambda: self._play_all(shuffle=False))
        self.shuffle_btn.clicked.connect(lambda: self._play_all(shuffle=True))

        # --- Stacked: empty state vs table ---
        self.stack = QStackedWidget()
        outer.addWidget(self.stack)

        self.empty_widget = EmptyStateWidget(
            title="No music folder selected.",
            subtitle="Please add a folder in Settings.",
            action_label="Open Settings",
        )
        if self.empty_widget.action_button is not None:
            self.empty_widget.action_button.clicked.connect(self.settings_requested.emit)
        self.stack.addWidget(self.empty_widget)

        self.table = AuraDragTableView()
        self.model = TracksTableModel(self)
        self.table.setModel(self.model)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(40) # Comfortable row height for album art
        self.table.setShowGrid(False)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.table.horizontalHeader().setStretchLastSection(False)
        self.table.setColumnWidth(COL_TITLE, 250)
        self.table.setColumnWidth(COL_ARTISTS, 180)
        self.table.setColumnWidth(COL_ALBUM, 180)
        self.table.setColumnWidth(COL_GENRE, 120)
        self.table.setColumnWidth(COL_DURATION, 80)
        self.resize_helper = AdjacentResizeHelper(self.table.horizontalHeader(), self.store, "tracks_table")
        self.table.horizontalHeader().sectionClicked.connect(self._on_header_clicked)
        self.table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._show_context_menu)
        self.table.doubleClicked.connect(self._on_row_double_clicked)
        
        self.delegate = TrackHoverDelegate(self.table, self)
        self.table.setItemDelegate(self.delegate)
        self.table.setMouseTracking(True)
        self.hover_filter = HoverEventFilter(self.table, self.delegate, self)
        self.table.viewport().installEventFilter(self.hover_filter)
        
        self.stack.addWidget(self.table)

        # --- Animation timer for Equalizer ---
        self.animation_timer = QTimer(self)
        self.animation_timer.setInterval(120)  # ~8 fps
        self.animation_timer.timeout.connect(self._on_animation_tick)
        
        if self.engine:
            self.engine.playback_state_changed.connect(self._on_playback_changed)
            self.engine.track_changed.connect(self._on_playback_changed)

        # --- Wire to store ---
        self.store.tracks_added.connect(self._on_tracks_changed)
        self.store.track_removed.connect(self._on_tracks_changed)
        self.store.track_updated.connect(self._on_tracks_changed)

        self.refresh()
        self._update_animation_timer()

    def _on_playback_changed(self, *args) -> None:
        self.table.viewport().update()
        self._update_animation_timer()

    def _on_animation_tick(self) -> None:
        self.table.viewport().update()

    def _update_animation_timer(self) -> None:
        if self.engine and self.engine.is_playing():
            if not self.animation_timer.isActive():
                self.animation_timer.start()
        else:
            if self.animation_timer.isActive():
                self.animation_timer.stop()

    # ---------- Data refresh ----------

    def refresh(self) -> None:
        from ui.theme import THEMES, DEFAULT_THEME
        theme_key = self.store.cache.settings.theme if self.store and hasattr(self.store, 'cache') else "dark"
        theme = THEMES.get(theme_key, THEMES[DEFAULT_THEME])
        self.stats_lbl.setStyleSheet(f"color: {theme['text_secondary']}; font-size: 13px; font-weight: normal; background: transparent;")

        tracks = self.store.all_tracks()
        if not tracks:
            self.stats_lbl.setText("")
            self.stack.setCurrentWidget(self.empty_widget)
            return
        self.stack.setCurrentWidget(self.table)
        count = len(tracks)
        self.stats_lbl.setText(f"{count} track{'s' if count != 1 else ''}")
        self.model.set_tracks(tracks)
        sort_col = getattr(self.model, "_sort_column", COL_TITLE)
        sort_asc = getattr(self.model, "_sort_ascending", True)
        self.model.sort_alphabetical(sort_col, sort_asc)

    def _on_tracks_changed(self, *_args) -> None:
        self.refresh()

    def _on_header_clicked(self, index: int) -> None:
        if self.model._sort_column == index:
            new_asc = not self.model._sort_ascending
        else:
            new_asc = True
        self.model.sort_alphabetical(index, new_asc)
        self.model.headerDataChanged.emit(Qt.Orientation.Horizontal, 0, self.model.columnCount() - 1)

    # ---------- Interactions ----------

    def _on_row_double_clicked(self, index) -> None:
        track = self.model.track_at(index.row())
        if not track:
            return
        if track.file_missing:
            QMessageBox.warning(
                self, "File missing",
                "This file is missing. Please remove it from library or update the path."
            )
            return
        self.track_double_clicked.emit(track.path)

    def _play_all(self, shuffle: bool) -> None:
        """Per the Step 3+4 spec: when shuffle is OFF, the queue must
        start in the table's CURRENT VISIBLE ORDER -- not the library's
        raw storage order. self.model already holds tracks in whatever
        order is currently displayed (it's re-sorted in place by
        sort_alphabetical() / future column-click sorting), so we read
        directly from it via track_at() rather than re-querying the
        store, which would silently reintroduce dict-insertion order.

        Shuffle itself is still performed by PlaybackEngine.play_all()
        once it receives this list -- this method only controls the
        STARTING order, which only matters when shuffle=False.
        """
        ordered_tracks = [
            self.model.track_at(row) for row in range(self.model.rowCount())
        ]
        ordered_tracks = [t for t in ordered_tracks if t is not None]
        if not ordered_tracks:
            return
        paths = [t.path for t in ordered_tracks if not t.file_missing]
        if not paths:
            return
        self.play_all_requested.emit(paths, shuffle)

    def _show_context_menu(self, pos) -> None:
        index = self.table.indexAt(pos)
        if not index.isValid():
            return
            
        # Select the row under right-click to fix selected-row highlight
        self.table.selectRow(index.row())
        
        track = self.model.track_at(index.row())
        if not track:
            return

        menu = QMenu(self)

        from ui.theme import THEMES, DEFAULT_THEME
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
        
        # Play / Queue controls
        if self.engine:
            add_queue_action = QAction("Add to Queue", self)
            menu.addAction(add_queue_action)
            add_queue_action.triggered.connect(lambda: self.engine.add_to_queue(track.path))
            
            play_next_action = QAction("Play Next", self)
            menu.addAction(play_next_action)
            play_next_action.triggered.connect(lambda: self.engine.play_next(track.path))
            
            menu.addSeparator()

        edit_action = QAction("Edit Metadata", self)
        remove_action = QAction("Remove Song", self)
        menu.addAction(edit_action)
        menu.addAction(remove_action)

        edit_action.triggered.connect(lambda: self._on_edit_metadata(track))
        remove_action.triggered.connect(lambda: self._on_remove_song(track))

        menu.addSeparator()

        # Add to Playlist Submenu
        add_playlist_menu = QMenu("Add to Playlist", self)
        add_playlist_menu.setStyleSheet(qss)
        custom_playlists = [p for p in self.store.all_playlists() if not p.id.startswith("smart_")]
        
        # Include Favorites
        fav_action = QAction("Favorites", self)
        fav_action.triggered.connect(lambda: self.store.add_tracks_to_playlist("smart_favorites", [track.path]))
        add_playlist_menu.addAction(fav_action)
        
        if custom_playlists:
            add_playlist_menu.addSeparator()
            for pl in custom_playlists:
                action = QAction(pl.name, self)
                action.triggered.connect(lambda checked, p_id=pl.id: self.store.add_tracks_to_playlist(p_id, [track.path]))
                add_playlist_menu.addAction(action)
                
        menu.addMenu(add_playlist_menu)

        menu.exec(self.table.viewport().mapToGlobal(pos))

    def _on_edit_metadata(self, track) -> None:
        from ui.widgets.metadata_editor_dialog import MetadataEditorDialog
        dialog = MetadataEditorDialog(track, self.store, self)
        dialog.exec()

    def _on_remove_song(self, track) -> None:
        reply = QMessageBox.question(
            self, "Remove song?",
            f'Remove "{track.title}" from your library?\n\n'
            "This only removes it from the library -- the file itself is not deleted.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            self.store.remove_track(track.path)


class TrackHoverDelegate(QStyledItemDelegate):
    def __init__(self, table, parent=None):
        super().__init__(parent)
        self.table = table
        self.view = parent
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

    def paint(self, painter, option, index):
        col = index.column()
        if col not in (COL_TITLE, COL_ARTISTS, COL_ALBUM, COL_GENRE):
            opt = QStyleOptionViewItem(option)
            self.initStyleOption(opt, index)
            if index.row() == getattr(self, 'hovered_row', -1):
                opt.state |= QStyle.StateFlag.State_MouseOver
            else:
                opt.state &= ~QStyle.StateFlag.State_MouseOver
            super().paint(painter, opt, index)
            return

        from ui.theme import THEMES, DEFAULT_THEME
        theme_key = self.view.store.cache.settings.theme
        theme = THEMES.get(theme_key, THEMES[DEFAULT_THEME])

        if col == COL_TITLE:
            # Prepare style option
            opt = QStyleOptionViewItem(option)
            self.initStyleOption(opt, index)
            opt.text = "" # Clear text so PE_PanelItemViewItem doesn't draw it
            
            if index.row() == self.hovered_row:
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
            
            # Dimensions
            cover_size = 28
            cover_x = option.rect.left() + 10
            cover_y = option.rect.top() + (option.rect.height() - cover_size) // 2
            cover_rect = QRect(cover_x, cover_y, cover_size, cover_size)
            
            # 1. Cache & Load scaled art
            if track.path not in self.art_cache:
                from core.metadata_reader import get_album_art
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
            
            # Determine states
            is_current = False
            is_playing = False
            if self.view.engine:
                is_current = (self.view.engine.get_current_track_path() == track.path)
                is_playing = is_current and self.view.engine.is_playing()
                
            is_row_hovered = (index.row() == self.hovered_row)
            
            # Get theme colors
            bg_color = QColor(theme['surface'])
            text_color = QColor(theme['text_secondary'])
            
            # Draw album cover/placeholder
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
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
                    painter.fillRect(cover_rect, bg_color)
            painter.restore()
            
            # Dark overlay if playing or hovered
            if is_playing or is_row_hovered:
                painter.save()
                painter.setClipPath(clip_path)
                painter.fillRect(cover_rect, QColor(0, 0, 0, 110))
                painter.restore()
                
            # Equalizer or Play icon overlay
            if is_playing:
                # Equalizer animation (State A)
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
                # Play icon (State B)
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
                
            # Now draw the track title text on the right
            text_rect = option.rect.adjusted(cover_size + 18, 0, -6, 0)
            
            if option.state & QStyle.StateFlag.State_Selected:
                title_color = QColor(theme['text_primary'])
            else:
                title_color = QColor(theme['text_primary'])
                fg = index.data(Qt.ItemDataRole.ForegroundRole)
                if fg:
                    title_color = fg.color()
                    
            painter.setPen(title_color)
            
            fm = option.fontMetrics
            y_baseline = text_rect.top() + (text_rect.height() + fm.ascent() - fm.descent()) // 2
            
            title_text = track.title or "Unknown Title"
            elided_title = fm.elidedText(title_text, Qt.TextElideMode.ElideRight, text_rect.width())
            
            font = painter.font()
            if is_current:
                font.setBold(True)
                if not (option.state & QStyle.StateFlag.State_Selected):
                    painter.setPen(QColor(theme['accent']))
            else:
                font.setBold(False)
            painter.setFont(font)
            
            painter.drawText(text_rect.left(), y_baseline, elided_title)
            
            painter.restore()
            return

        # Prepare a copy of the option without text
        opt = QStyleOptionViewItem(option)
        self.initStyleOption(opt, index)
        opt.text = "" # Clear the text so it doesn't paint twice
        
        if index.row() == self.hovered_row:
            opt.state |= QStyle.StateFlag.State_MouseOver
        else:
            opt.state &= ~QStyle.StateFlag.State_MouseOver
        
        # Draw standard background/selection/etc. using primitive panel drawing instead of super().paint()
        # This prevents the base implementation from calling initStyleOption internally and re-drawing the text
        widget = option.widget
        style = widget.style() if widget else None
        if style:
            style.drawPrimitive(QStyle.PrimitiveElement.PE_PanelItemViewItem, opt, painter, widget)

        # Now paint our text
        painter.save()
        
        # Determine text color based on selection state
        if option.state & QStyle.StateFlag.State_Selected:
            text_color = QColor(theme['text_primary'])
        else:
            text_color = QColor(theme['text_secondary'] if index.column() != 1 else theme['text_primary'])
            # If there's an explicit foreground role:
            fg = index.data(Qt.ItemDataRole.ForegroundRole)
            if fg:
                text_color = fg.color()
                
        painter.setPen(text_color)
        
        # Determine if mouse is over this cell
        is_hovered = option.rect.contains(self.mouse_pos)
        
        # Indent slightly (e.g. 6px matching other cells)
        rect = option.rect.adjusted(6, 0, -6, 0)
        
        fm = option.fontMetrics
        y_baseline = rect.top() + (rect.height() + fm.ascent() - fm.descent()) // 2

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
                        x_offset += genre_width
                        
                        if next_delim:
                            font.setUnderline(False)
                            painter.setFont(font)
                            painter.setPen(text_color)
                            painter.drawText(x_offset, y_baseline, next_delim)
                            x_offset += delim_width
            else:
                painter.drawText(rect.left(), y_baseline, "—")

        painter.restore()

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


class HoverEventFilter(QObject):
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
            elif col == COL_TITLE and hasattr(self.delegate, "is_over_album_cover") and self.delegate.is_over_album_cover(index, pos):
                self.table.setCursor(Qt.CursorShape.PointingHandCursor)
            else:
                self.table.setCursor(Qt.CursorShape.ArrowCursor)
        else:
            self.delegate.hovered_row = -1
            self.table.setCursor(Qt.CursorShape.ArrowCursor)
            
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
                    if col == COL_TITLE and hasattr(self.delegate, "is_over_album_cover") and self.delegate.is_over_album_cover(index, pos):
                        if hasattr(self.view, "_on_row_double_clicked"):
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
                                
        return super().eventFilter(obj, event)
