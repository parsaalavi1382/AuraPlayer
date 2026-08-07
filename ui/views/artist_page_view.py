"""
ArtistPageView: Dedicated page displaying details for a specific artist,
including stats, albums, "Appears On" tracks, and a full track list.
"""

from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal, QTimer, QRect
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTableView, QHeaderView, QAbstractItemView, QScrollArea, QFrame,
    QSizePolicy, QGridLayout, QMenu, QFileDialog
)
from PyQt6.QtGui import QFont, QPixmap, QPainter, QPainterPath, QColor, QLinearGradient, QCursor, QAction, QFontMetrics, QTextLayout, QTextOption

from core.library_store import LibraryStore
from core.models import Track
from core.metadata_reader import get_album_art
from ui.models.tracks_table_model import TracksTableModel, COL_TITLE, COL_ARTISTS, COL_ALBUM, COL_GENRE, COL_DURATION
from ui.views.tracks_view import TrackHoverDelegate, HoverEventFilter
from ui.widgets.adjacent_resize_helper import AdjacentResizeHelper
from ui.widgets.drag_table_view import AuraDragTableView


def elide_text_2_lines(text: str, font: QFont, width: int) -> str:
    if not text:
        return ""
    layout = QTextLayout(text, font)
    option = QTextOption()
    option.setWrapMode(QTextOption.WrapMode.WrapAtWordBoundaryOrAnywhere)
    layout.setTextOption(option)
    
    layout.beginLayout()
    line1 = layout.createLine()
    if not line1.isValid():
        layout.endLayout()
        return text
    line1.setLineWidth(width)
    
    line2 = layout.createLine()
    if not line2.isValid():
        layout.endLayout()
        return text
    line2.setLineWidth(width)
    
    line3 = layout.createLine()
    layout.endLayout()
    
    if not line3.isValid():
        return text
    
    l1_len = line1.textLength()
    l1_text = text[:l1_len]
    l2_remainder = text[l1_len:].lstrip()
    
    fm = QFontMetrics(font)
    elided_l2 = fm.elidedText(l2_remainder, Qt.TextElideMode.ElideRight, width)
    
    return l1_text + elided_l2


class AlbumCard(QWidget):
    clicked = pyqtSignal(str) # album_key

    def __init__(self, album_key: str, album_name: str, track_path: str, parent=None, is_appears_on: bool = False, main_artist: str = "", card_width: int = 158):
        super().__init__(parent)
        self.album_key = album_key
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        
        # Resolve active theme
        store = None
        p = self.parent()
        while p:
            if hasattr(p, "store"):
                store = p.store
                break
            p = p.parent()
        
        theme_key = "dark"
        if store:
            theme_key = store.cache.settings.theme
        else:
            from PyQt6.QtWidgets import QApplication
            for w in QApplication.topLevelWidgets():
                if hasattr(w, "store"):
                    theme_key = w.store.cache.settings.theme
                    break
        
        def rebuild_grids_with_current_width(self):
            # Determine available width for grids
            width = self.scroll.viewport().width() - 48
            if width <= 100:
                width = self.width() - 48
            if width < 100:
                width = 300
            
            # Safely check if components are initialized before calling their methods
            if hasattr(self, "albums_grid") and self.albums_grid is not None:
                self.albums_grid.rebuild_grid(width)
                
            if hasattr(self, "appears_on_grid") and self.appears_on_grid is not None:
                self.appears_on_grid.rebuild_grid(width)
                
            if hasattr(self, "resize_table_to_contents"):
                self.resize_table_to_contents()
                
        from PyQt6.QtCore import QSize
        self.icon_size = QSize(140, 140)

        from ui.theme import THEMES, apply_theme_vars, DEFAULT_THEME
        theme = THEMES.get(theme_key, THEMES[DEFAULT_THEME])

        # Outer layout
        outer_layout = QVBoxLayout(self)
        outer_layout.setContentsMargins(0, 0, 0, 0)
        outer_layout.setSpacing(0)
        
        # Inner Frame
        self.frame = QFrame()
        self.frame.setObjectName("albumCardFrame")
        self.frame.setStyleSheet(apply_theme_vars("""
            #albumCardFrame {
                border-radius: 8px;
                background-color: transparent;
            }
            #albumCardFrame:hover, #albumCardFrame[focused="true"] {
                background-color: var(--surface_hover);
            }
        """, theme))
        
        layout = QVBoxLayout(self.frame)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(6)
        
        # Determine inner cover size
        cover_size = card_width - 8 # subtract margins (4 + 4)

        # Cover Art (High res target for original quality)
        self.cover_label = QLabel()
        self.cover_label.setFixedSize(cover_size, cover_size)
        self.cover_label.setScaledContents(True)
        self.cover_label.setStyleSheet(apply_theme_vars("border-radius: 8px; background-color: var(--surface);", theme))
        
        dpr = self.devicePixelRatioF() if hasattr(self, "devicePixelRatioF") else 1.0
        
        high_res_target = 400
        effective_radius = 8.0 * (high_res_target / max(1, cover_size))
        
        pixmap = get_album_art(track_path, target_size=high_res_target, dpr=dpr, corner_radius=effective_radius)
        if pixmap and not pixmap.isNull():
            self.cover_label.setPixmap(pixmap)
        else:
            from ui.svg_icon import get_default_cover
            self.cover_label.setText("")
            disc_px = get_default_cover(high_res_target, theme, corner_radius=effective_radius)
            self.cover_label.setPixmap(disc_px)
        
        layout.addWidget(self.cover_label, alignment=Qt.AlignmentFlag.AlignCenter)
        
        # Album name (Max 2 lines)
        name_font = QFont("Segoe UI", 10, QFont.Weight.Bold)
        elided_name = elide_text_2_lines(album_name, name_font, cover_size)
        self.name_label = QLabel(elided_name)
        self.name_label.setWordWrap(True)
        self.name_label.setFixedWidth(cover_size)
        self.name_label.setAlignment(Qt.AlignmentFlag.AlignLeft)
        self.name_label.setFont(name_font)
        self.name_label.setStyleSheet(apply_theme_vars("color: var(--text_primary);", theme))
        layout.addWidget(self.name_label)
        
        # Artist name under title (Max 1 line)
        sec_font = QFont("Segoe UI", 9, QFont.Weight.Normal)
        fm_sec = QFontMetrics(sec_font)
        display_artist = main_artist if main_artist else ""
        elided_artist = fm_sec.elidedText(display_artist, Qt.TextElideMode.ElideRight, cover_size)
        self.sec_label = QLabel(elided_artist)
        self.sec_label.setFont(sec_font)
        self.sec_label.setStyleSheet(apply_theme_vars("color: var(--text_secondary);", theme))
        self.sec_label.setWordWrap(False)
        self.sec_label.setFixedWidth(cover_size)
        self.sec_label.setAlignment(Qt.AlignmentFlag.AlignLeft)
        layout.addWidget(self.sec_label)
            
        layout.addStretch()
        outer_layout.addWidget(self.frame)
        
        # Set fixed size for the whole card adapting to dynamically computed width
        card_height = card_width + 64
        self.setFixedSize(card_width, card_height)
        
    def focusInEvent(self, event):
        super().focusInEvent(event)
        self.frame.setProperty("focused", True)
        self.frame.style().unpolish(self.frame)
        self.frame.style().polish(self.frame)
        p = self.parent()
        while p:
            from PyQt6.QtWidgets import QScrollArea
            if isinstance(p, QScrollArea):
                p.ensureWidgetVisible(self)
                break
            p = p.parent()

    def focusOutEvent(self, event):
        super().focusOutEvent(event)
        self.frame.setProperty("focused", False)
        self.frame.style().unpolish(self.frame)
        self.frame.style().polish(self.frame)

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Space):
            self.clicked.emit(self.album_key)
            event.accept()
        else:
            super().keyPressEvent(event)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self.album_key)


class AlbumGridWidget(QWidget):
    album_clicked = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.grid_layout = QGridLayout(self)
        self.grid_layout.setContentsMargins(0, 0, 0, 0)
        self.grid_layout.setSpacing(12)  # Nice space between rows and columns
        self.grid_layout.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        
        self._albums = []
        self._is_appears_on = False

    def set_albums(self, albums, is_appears_on=False):
        self._albums = albums
        self._is_appears_on = is_appears_on
        self.rebuild_grid()

    def get_cards(self):
        cards = []
        for i in range(self.grid_layout.count()):
            item = self.grid_layout.itemAt(i)
            if item and item.widget():
                cards.append(item.widget())
        return cards

    def rebuild_grid(self, container_width: int = 0):
        # Clear existing layout items
        while self.grid_layout.count():
            item = self.grid_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
                
        if not self._albums:
            self.setFixedHeight(0)
            return
            
        min_card_width = 158
        spacing = 12
        
        # Calculate how many columns can fit in container_width
        if container_width <= 0:
            container_width = 500  # Safe fallback
            
        max_cols = max(1, (container_width + spacing) // (min_card_width + spacing))
        
        actual_card_width = (container_width - (max_cols - 1) * spacing) // max_cols
        actual_card_height = actual_card_width + 64
        
        for idx, (key, name, year, track_path, main_artist) in enumerate(self._albums):
            row = idx // max_cols
            col = idx % max_cols
            card = AlbumCard(key, name, track_path, is_appears_on=self._is_appears_on, main_artist=main_artist, card_width=actual_card_width)
            card.clicked.connect(self.album_clicked.emit)
            self.grid_layout.addWidget(card, row, col)
            
        # Set dynamic height of this component to show all wrapped rows beautifully
        num_rows = (len(self._albums) + max_cols - 1) // max_cols
        total_height = num_rows * actual_card_height + (num_rows - 1) * spacing
        self.setFixedHeight(total_height)


class ArtistHoverableCoverLabel(QLabel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.is_hovered = False
        self.setMouseTracking(True)
        self.has_custom_image = False
        self.setCursor(Qt.CursorShape.PointingHandCursor)

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
        
        if self.is_hovered:
            painter = QPainter(self)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            
            rect = self.rect()
            clip_path = QPainterPath()
            from PyQt6.QtCore import QRectF
            clip_path.addEllipse(QRectF(rect))
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
            text_val = "edit photo" if self.has_custom_image else "choose photo"
            text_fm = painter.fontMetrics()
            text_w = text_fm.horizontalAdvance(text_val)
            
            text_x = (rect.width() - text_w) // 2
            text_y = pencil_y + fm.height() + 4
            
            painter.drawText(text_x, text_y + text_fm.ascent(), text_val)
            painter.end()


class ArtistPageView(QWidget):
    track_double_clicked = pyqtSignal(str)
    album_requested = pyqtSignal(str)
    artist_requested = pyqtSignal(str)
    genre_requested = pyqtSignal(str)
    play_all_requested = pyqtSignal(list, bool)

    def __init__(self, artist_name: str, store: LibraryStore, engine=None, parent=None):
        super().__init__(parent)
        self.artist_name = artist_name
        self.store = store
        self.engine = engine

        # Top level layout
        outer_layout = QVBoxLayout(self)
        outer_layout.setContentsMargins(0, 0, 0, 0)
        outer_layout.setSpacing(0)

        # Main scroll area
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.scroll.setObjectName("artistScrollArea")
        self.scroll.setStyleSheet("#artistScrollArea { background: transparent; border: none; }")
        outer_layout.addWidget(self.scroll)

        # Scroll content widget
        self.scroll_content = QWidget()
        self.scroll_content.setObjectName("artistScrollContent")
        self.scroll_content.setStyleSheet("#artistScrollContent { background: transparent; }")
        self.scroll_layout = QVBoxLayout(self.scroll_content)
        self.scroll_layout.setContentsMargins(24, 24, 24, 24)
        self.scroll_layout.setSpacing(24)
        self.scroll.setWidget(self.scroll_content)

        # ------------------------------------------------------------------
        # Header Area
        # ------------------------------------------------------------------
        header_layout = QHBoxLayout()
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_layout.setSpacing(24)

        self.cover_label = ArtistHoverableCoverLabel()
        self.cover_label.setFixedSize(120, 120)
        self.cover_label.setScaledContents(True)
        self.cover_label.mousePressEvent = self._on_cover_clicked
        header_layout.addWidget(self.cover_label)

        text_layout = QVBoxLayout()
        text_layout.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        text_layout.setSpacing(8)

        # Artist Name
        self.title_label = QLabel(self.artist_name)
        self.title_label.setObjectName("playerScreenTitle")
        self.title_label.setFont(QFont("Segoe UI", 28, QFont.Weight.Bold))
        self.title_label.setStyleSheet("color: var(--text_primary);")
        self.title_label.setWordWrap(True)
        
        # Track Count
        self.stats_label = QLabel()
        self.stats_label.setObjectName("emptyStateSubtitle")
        self.stats_label.setFont(QFont("Segoe UI", 12))
        self.stats_label.setStyleSheet("color: var(--text_secondary);")
        
        text_layout.addWidget(self.title_label)
        text_layout.addWidget(self.stats_label)
        header_layout.addLayout(text_layout)
        header_layout.addStretch()

        # Play / Shuffle Buttons row - mirroring tracks tab's details
        buttons_layout = QHBoxLayout()
        buttons_layout.setSpacing(12)
        
        self.play_btn = QPushButton("▶  Play Artist")
        self.play_btn.setObjectName("accentButton")
        self.play_btn.clicked.connect(lambda: self._play_artist_tracks(shuffle=False))
        
        self.shuffle_btn = QPushButton("🔀  Shuffle")
        self.shuffle_btn.clicked.connect(lambda: self._play_artist_tracks(shuffle=True))

        buttons_layout.addWidget(self.play_btn)
        buttons_layout.addWidget(self.shuffle_btn)
        header_layout.addLayout(buttons_layout)

        self.scroll_layout.addLayout(header_layout)

        # ------------------------------------------------------------------
        # Section 1 - Albums
        # ------------------------------------------------------------------
        self.albums_container = QWidget()
        albums_layout = QVBoxLayout(self.albums_container)
        albums_layout.setContentsMargins(0, 0, 0, 0)
        albums_layout.setSpacing(12)
        
        self.albums_title = QLabel("Albums")
        self.albums_title.setFont(QFont("Segoe UI", 16, QFont.Weight.Bold))
        self.albums_title.setStyleSheet("color: var(--text_primary);")
        albums_layout.addWidget(self.albums_title)
        
        self.albums_grid = AlbumGridWidget()
        self.albums_grid.album_clicked.connect(self.album_requested.emit)
        albums_layout.addWidget(self.albums_grid)
        self.scroll_layout.addWidget(self.albums_container)

        # ------------------------------------------------------------------
        # Section 2 - Appears On
        # ------------------------------------------------------------------
        self.appears_on_container = QWidget()
        appears_layout = QVBoxLayout(self.appears_on_container)
        appears_layout.setContentsMargins(0, 0, 0, 0)
        appears_layout.setSpacing(12)
        
        self.appears_on_title = QLabel("Appears on")
        self.appears_on_title.setFont(QFont("Segoe UI", 16, QFont.Weight.Bold))
        self.appears_on_title.setStyleSheet("color: var(--text_primary);")
        appears_layout.addWidget(self.appears_on_title)
        
        self.appears_on_grid = AlbumGridWidget()
        self.appears_on_grid.album_clicked.connect(self.album_requested.emit)
        appears_layout.addWidget(self.appears_on_grid)
        self.scroll_layout.addWidget(self.appears_on_container)

        # ------------------------------------------------------------------
        # Section 3 - Track List
        # ------------------------------------------------------------------
        self.tracks_container = QWidget()
        tracks_layout = QVBoxLayout(self.tracks_container)
        tracks_layout.setContentsMargins(0, 0, 0, 0)
        tracks_layout.setSpacing(12)

        self.tracks_title = QLabel("Tracks")
        self.tracks_title.setFont(QFont("Segoe UI", 16, QFont.Weight.Bold))
        self.tracks_title.setStyleSheet("color: var(--text_primary);")
        tracks_layout.addWidget(self.tracks_title)

        self.table = AuraDragTableView()
        self.model = TracksTableModel(self)
        self.table.setModel(self.model)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(50)  # Two-line rows: title + artist
        self.table.setShowGrid(False)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.table.horizontalHeader().setStretchLastSection(False)
        self.table.setColumnWidth(COL_TITLE, 400)  # Wider: shows title+artist merged
        self.table.setColumnHidden(COL_ARTISTS, True)  # Artist shown in merged Title cell
        self.table.setColumnWidth(COL_ALBUM, 180)
        self.table.setColumnWidth(COL_GENRE, 120)
        self.table.setColumnWidth(COL_DURATION, 80)
        self.resize_helper = AdjacentResizeHelper(self.table.horizontalHeader(), self.store, "tracks_table")
        self.table.horizontalHeader().sectionClicked.connect(self._on_header_clicked)
        self.table.doubleClicked.connect(self._on_row_double_clicked)

        # Context menu handler
        self.table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._show_context_menu)

        # Disable table scrollbars so the entire page scrolls together
        self.table.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.table.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.table.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        self.delegate = TrackHoverDelegate(self.table, self)
        self.table.setItemDelegate(self.delegate)
        self.table.setMouseTracking(True)
        self.hover_filter = HoverEventFilter(self.table, self.delegate, self)
        self.table.viewport().installEventFilter(self.hover_filter)

        tracks_layout.addWidget(self.table)
        self.scroll_layout.addWidget(self.tracks_container)

        # --- Animation timer for Equalizer ---
        self.animation_timer = QTimer(self)
        self.animation_timer.setInterval(50)
        self.animation_timer.timeout.connect(self._on_animation_tick)

        if self.engine:
            self.engine.playback_state_changed.connect(self._on_playback_changed)
            self.engine.track_changed.connect(self._on_playback_changed)

        self.refresh()
        self._update_animation_timer()

    def _on_cover_clicked(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            has_custom = bool(self.store.get_artist_image(self.artist_name))
            if has_custom:
                menu = QMenu(self)
                edit_action = QAction("Edit", self)
                delete_action = QAction("Delete", self)
                menu.addAction(edit_action)
                menu.addAction(delete_action)
                
                action = menu.exec(event.globalPosition().toPoint())
                if action == edit_action:
                    self._prompt_cover_file()
                elif action == delete_action:
                    self.store.set_artist_image(self.artist_name, None)
                    self.refresh()
            else:
                self._prompt_cover_file()

    def _prompt_cover_file(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Select Artist Profile Picture", "",
            "Images (*.png *.jpg *.jpeg *.bmp *.webp)"
        )
        if path:
            self.store.set_artist_image(self.artist_name, path)
            self.refresh()

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

    def _on_header_clicked(self, index: int) -> None:
        self.model.cycle_sort(index)
        self.model.headerDataChanged.emit(Qt.Orientation.Horizontal, 0, self.model.columnCount() - 1)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        QTimer.singleShot(0, self.rebuild_grids_with_current_width)

    def showEvent(self, event):
        super().showEvent(event)
        QTimer.singleShot(0, self.rebuild_grids_with_current_width)

    def rebuild_grids_with_current_width(self):
        # Determine available width for grids
        width = self.scroll.viewport().width() - 48
        if width <= 100:
            width = self.width() - 48
        if width < 100:
            width = 300
        
        # Safely check if components are initialized before calling their methods
        if hasattr(self, "albums_grid") and self.albums_grid is not None:
            self.albums_grid.rebuild_grid(width)
            
        if hasattr(self, "appears_on_grid") and self.appears_on_grid is not None:
            self.appears_on_grid.rebuild_grid(width)
            
        if hasattr(self, "resize_table_to_contents"):
            self.resize_table_to_contents()

    def resize_table_to_contents(self) -> None:
        # Safely return if the model or table hasn't been fully initialized yet
        if not hasattr(self, "model") or self.model is None:
            return
        if not hasattr(self, "table") or self.table is None:
            return

        num_rows = self.model.rowCount()
        row_height = self.table.verticalHeader().defaultSectionSize() or 40
        header_height = self.table.horizontalHeader().height() or 30
        
        if num_rows == 0:
            self.table.setFixedHeight(0)
            return
            
        total_height = num_rows * row_height + header_height + 4
        self.table.setFixedHeight(total_height)

    def apply_theme_colors(self):
        theme_key = self.store.cache.settings.theme
        from ui.theme import THEMES, DEFAULT_THEME, apply_theme_vars
        theme = THEMES.get(theme_key, THEMES[DEFAULT_THEME])
        
        self.title_label.setStyleSheet(apply_theme_vars("color: var(--text_primary);", theme))
        self.stats_label.setStyleSheet(apply_theme_vars("color: var(--text_secondary);", theme))
        self.albums_title.setStyleSheet(apply_theme_vars("color: var(--text_primary);", theme))
        self.appears_on_title.setStyleSheet(apply_theme_vars("color: var(--text_primary);", theme))
        self.tracks_title.setStyleSheet(apply_theme_vars("color: var(--text_primary);", theme))

    def refresh(self) -> None:
        self.apply_theme_colors()
        all_tracks = self.store.all_tracks()
        
        theme_key = self.store.cache.settings.theme
        from ui.theme import THEMES, DEFAULT_THEME
        theme = THEMES.get(theme_key, THEMES[DEFAULT_THEME])
        from ui.views.artists_view import get_artist_collage
        cover_px = get_artist_collage(self.store, self.artist_name, 120, theme)
        self.cover_label.setPixmap(cover_px)
        self.cover_label.has_custom_image = bool(self.store.get_artist_image(self.artist_name))
        
        # Filter tracks where this artist is listed in artists
        artist_tracks = [t for t in all_tracks if self.artist_name in t.artists]
        self.model.set_tracks(artist_tracks)
        self.model.sort_alphabetical(COL_TITLE)

        self.stats_label.setText(f"{len(artist_tracks)} songs")

        # Find albums by this artist (where the artist is in album_artists)
        albums_list = []
        album_map = {}
        for t in all_tracks:
            if self.artist_name in t.album_artists:
                if t.album_key not in album_map:
                    album_map[t.album_key] = (t.album, t.year, t.path, ", ".join(t.album_artists))
        
        sorted_albums = sorted(album_map.items(), key=lambda x: (x[1][0] or "").lower())
        for key, (name, year, track_path, main_artist) in sorted_albums:
            albums_list.append((key, name, year, track_path, main_artist))
            
        if albums_list:
            self.albums_container.setVisible(True)
            self.albums_grid.set_albums(albums_list, is_appears_on=False)
        else:
            self.albums_container.setVisible(False)

        # Find Appears On tracks: artist is in track.artists, but NOT in track.album_artists
        appears_on_list = []
        appears_on_map = {}
        for t in all_tracks:
            if self.artist_name in t.artists and self.artist_name not in t.album_artists:
                if t.album_key not in appears_on_map:
                    appears_on_map[t.album_key] = (t.album, t.year, t.path, ", ".join(t.album_artists))

        sorted_appears = sorted(appears_on_map.items(), key=lambda x: (x[1][0] or "").lower())
        for key, (name, year, track_path, main_artist) in sorted_appears:
            appears_on_list.append((key, name, year, track_path, main_artist))

        if appears_on_list:
            self.appears_on_container.setVisible(True)
            self.appears_on_grid.set_albums(appears_on_list, is_appears_on=True)
        else:
            self.appears_on_container.setVisible(False)

        # Rebuild grid layout sizing and table height
        QTimer.singleShot(0, self.rebuild_grids_with_current_width)

    def _on_row_double_clicked(self, index) -> None:
        track = self.model.track_at(index.row())
        if track:
            if track.file_missing:
                return
            self.track_double_clicked.emit(track.path)

    def _show_context_menu(self, pos) -> None:
        index = self.table.indexAt(pos)
        if not index.isValid():
            return
        track = self.model.track_at(index.row())
        if not track:
            return

        from ui.context_menu import build_track_context_menu
        menu = build_track_context_menu(
            parent=self,
            track=track,
            store=self.store,
            engine=self.engine,
            on_play=lambda: self.track_double_clicked.emit(track.path),
            on_remove=lambda: self._on_remove_song(track),
            remove_text="Remove Song"
        )
        menu.exec(self.table.viewport().mapToGlobal(pos))

    def _on_edit_metadata(self, track) -> None:
        from ui.widgets.metadata_editor_dialog import MetadataEditorDialog
        dialog = MetadataEditorDialog(track, self.store, self)
        dialog.exec()

    def _on_show_properties(self, track) -> None:
        from ui.widgets.properties_dialog import PropertiesDialog
        dialog = PropertiesDialog(track, self.store, self)
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

    def _play_artist_tracks(self, shuffle: bool) -> None:
        ordered_tracks = [
            self.model.track_at(row) for row in range(self.model.rowCount())
        ]
        ordered_tracks = [t for t in ordered_tracks if t is not None and not t.file_missing]
        if not ordered_tracks:
            return
        paths = [t.path for t in ordered_tracks]
        self.play_all_requested.emit(paths, shuffle)

    def refresh_from_signal(self, *args) -> None:
        try:
            if args and isinstance(args[0], str):
                track_path = args[0]
                if not hasattr(self, "store") or not self.store.get_track(track_path):
                    self.refresh()
                    return
                if hasattr(self, "table") and self.table:
                    model = self.table.model()
                    if model:
                        for row in range(model.rowCount()):
                            track = model.track_at(row)
                            if track and track.path == track_path:
                                idx_start = model.index(row, 0)
                                idx_end = model.index(row, model.columnCount() - 1)
                                model.dataChanged.emit(idx_start, idx_end, [])
                return
            self.refresh()
        except RuntimeError:
            pass

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

    def _ensure_row_visible(self, row: int) -> None:
        if not self.table or row < 0: return
        from PyQt6.QtCore import QPoint
        self.table.setFocus()
        model = self.table.model()
        if model and 0 <= row < model.rowCount():
            self.table.setCurrentIndex(model.index(row, 0))
            self.table.selectRow(row)
        header_h = self.table.horizontalHeader().height() or 30
        row_h = self.table.verticalHeader().defaultSectionSize() or 36
        try:
            row_y = self.table.mapTo(self.scroll_content, QPoint(0, header_h + row * row_h)).y()
            sb = self.scroll.verticalScrollBar()
            if sb:
                val = sb.value()
                view_h = self.scroll.viewport().height()
                if row_y < val:
                    sb.setValue(max(0, row_y - 20))
                elif row_y + row_h > val + view_h:
                    sb.setValue(row_y + row_h - view_h + 20)
        except Exception:
            pass

    def navigate_up(self) -> None:
        if not self.table: return
        model = self.table.model()
        if not model or model.rowCount() == 0: return
        curr_row = self.table.currentIndex().row()
        if curr_row <= 0:
            self._ensure_row_visible(0)
        else:
            self._ensure_row_visible(curr_row - 1)

    def navigate_down(self) -> None:
        if not self.table: return
        model = self.table.model()
        if not model or model.rowCount() == 0: return
        curr_row = self.table.currentIndex().row()
        if curr_row < 0:
            self._ensure_row_visible(0)
        elif curr_row + 1 < model.rowCount():
            self._ensure_row_visible(curr_row + 1)
        else:
            self._ensure_row_visible(model.rowCount() - 1)

    def _get_active_sections(self):
        sections = []
        if self.albums_container.isVisible():
            cards = self.albums_grid.get_cards()
            if cards:
                sections.append(("albums", cards))
        if self.appears_on_container.isVisible():
            cards = self.appears_on_grid.get_cards()
            if cards:
                sections.append(("appears_on", cards))
        if self.tracks_container.isVisible() and self.model.rowCount() > 0:
            sections.append(("tracks", self.table))
        return sections

    def _ensure_card_visible(self, card) -> None:
        from PyQt6.QtCore import QPoint
        card.setFocus()
        card_y = card.mapTo(self.scroll_content, QPoint(0, 0)).y()
        card_h = card.height()
        sb = self.scroll.verticalScrollBar()
        if sb:
            val = sb.value()
            view_h = self.scroll.viewport().height()
            if card_y < val:
                sb.setValue(max(0, card_y - 20))
            elif card_y + card_h > val + view_h:
                sb.setValue(card_y + card_h - view_h + 20)

    def _ensure_row_visible(self, row: int) -> None:
        from PyQt6.QtCore import QPoint
        self.table.setFocus()
        self.table.selectRow(row)
        header_h = self.table.horizontalHeader().height() or 30
        row_h = self.table.verticalHeader().defaultSectionSize() or 40
        row_y = self.table.mapTo(self.scroll_content, QPoint(0, header_h + row * row_h)).y()
        sb = self.scroll.verticalScrollBar()
        if sb:
            val = sb.value()
            view_h = self.scroll.viewport().height()
            if row_y < val:
                sb.setValue(max(0, row_y - 20))
            elif row_y + row_h > val + view_h:
                sb.setValue(row_y + row_h - view_h + 20)

    def _get_current_focus_info(self):
        from PyQt6.QtWidgets import QApplication
        sections = self._get_active_sections()
        if not sections: return None, -1, -1
        
        focus_w = QApplication.focusWidget()
        current_section_idx = -1
        current_card_idx = -1

        for sec_idx, (sec_type, target) in enumerate(sections):
            if sec_type in ("albums", "appears_on"):
                if focus_w in target:
                    current_section_idx = sec_idx
                    current_card_idx = target.index(focus_w)
                    break
            elif sec_type == "tracks":
                if focus_w == self.table or (self.table and self.table.isAncestorOf(focus_w)):
                    current_section_idx = sec_idx
                    break
                    
        return sections, current_section_idx, current_card_idx

    def navigate_down(self) -> None:
        sections, current_section_idx, current_card_idx = self._get_current_focus_info()
        if not sections: return
        
        if current_section_idx == -1:
            sec_type, target = sections[0]
            if sec_type in ("albums", "appears_on"):
                self._ensure_card_visible(target[0])
            elif sec_type == "tracks":
                self._ensure_row_visible(0)
            return
            
        sec_type, target = sections[current_section_idx]
        
        if sec_type in ("albums", "appears_on"):
            if current_card_idx + 1 < len(target):
                self._ensure_card_visible(target[current_card_idx + 1])
            else:
                if current_section_idx + 1 < len(sections):
                    next_type, next_target = sections[current_section_idx + 1]
                    if next_type in ("albums", "appears_on"):
                        self._ensure_card_visible(next_target[0])
                    elif next_type == "tracks":
                        self._ensure_row_visible(0)
                        
        elif sec_type == "tracks":
            curr_row = self.table.currentIndex().row()
            if curr_row < 0:
                curr_row = 0
            if curr_row + 1 < self.model.rowCount():
                self._ensure_row_visible(curr_row + 1)

    def navigate_up(self) -> None:
        sections, current_section_idx, current_card_idx = self._get_current_focus_info()
        if not sections: return
        
        if current_section_idx == -1:
            sec_type, target = sections[-1]
            if sec_type in ("albums", "appears_on"):
                self._ensure_card_visible(target[-1])
            elif sec_type == "tracks":
                if self.model.rowCount() > 0:
                    self._ensure_row_visible(self.model.rowCount() - 1)
            return

        sec_type, target = sections[current_section_idx]
        
        if sec_type in ("albums", "appears_on"):
            if current_card_idx > 0:
                self._ensure_card_visible(target[current_card_idx - 1])
            else:
                if current_section_idx > 0:
                    prev_type, prev_target = sections[current_section_idx - 1]
                    if prev_type in ("albums", "appears_on"):
                        self._ensure_card_visible(prev_target[-1])
                        
        elif sec_type == "tracks":
            curr_row = self.table.currentIndex().row()
            if curr_row > 0:
                self._ensure_row_visible(curr_row - 1)
            else:
                if current_section_idx > 0:
                    prev_type, prev_target = sections[current_section_idx - 1]
                    if prev_type in ("albums", "appears_on"):
                        self._ensure_card_visible(prev_target[-1])
