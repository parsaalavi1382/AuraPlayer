"""
ArtistPageView: Dedicated page displaying details for a specific artist,
including stats, albums, "Appears On" tracks, and a full track list.
"""

from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal, QTimer, QRect
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTableView, QHeaderView, QAbstractItemView, QScrollArea, QFrame,
    QSizePolicy, QGridLayout,
)
from PyQt6.QtGui import QFont, QPixmap, QPainter, QPainterPath, QColor, QLinearGradient

from core.library_store import LibraryStore
from core.models import Track
from core.metadata_reader import get_album_art
from ui.models.tracks_table_model import TracksTableModel, COL_TITLE, COL_ARTISTS, COL_ALBUM, COL_GENRE, COL_DURATION
from ui.views.tracks_view import TrackHoverDelegate, HoverEventFilter


class AlbumCard(QWidget):
    clicked = pyqtSignal(str) # album_key

    def __init__(self, album_key: str, album_name: str, track_path: str, parent=None, is_appears_on: bool = False, main_artist: str = ""):
        super().__init__(parent)
        self.album_key = album_key
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        
        # Outer layout
        outer_layout = QVBoxLayout(self)
        outer_layout.setContentsMargins(0, 0, 0, 0)
        outer_layout.setSpacing(0)
        
        # Inner Frame
        self.frame = QFrame()
        self.frame.setObjectName("albumCardFrame")
        self.frame.setStyleSheet("""
            #albumCardFrame {
                border-radius: 8px;
                background-color: transparent;
            }
            #albumCardFrame:hover {
                background-color: rgba(255, 255, 255, 0.08);
            }
        """)
        
        layout = QVBoxLayout(self.frame)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(6)
        
        # Cover Art (Bigger: 150x150)
        self.cover_label = QLabel()
        self.cover_label.setFixedSize(150, 150)
        self.cover_label.setStyleSheet("border-radius: 8px; background-color: var(--surface);")
        
        pixmap = get_album_art(track_path)
        if pixmap and not pixmap.isNull():
            scaled = pixmap.scaled(
                150, 150,
                Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                Qt.TransformationMode.SmoothTransformation,
            )
            self.cover_label.setPixmap(scaled)
        else:
            self.cover_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.cover_label.setFont(QFont("Segoe UI", 32))
            self.cover_label.setText("💿")
            self.cover_label.setStyleSheet("border-radius: 8px; background-color: var(--surface); color: var(--text_secondary);")
            
        layout.addWidget(self.cover_label, alignment=Qt.AlignmentFlag.AlignCenter)
        
        # Album name (No year displayed)
        self.name_label = QLabel()
        self.name_label.setWordWrap(True)
        self.name_label.setFixedWidth(150)
        self.name_label.setAlignment(Qt.AlignmentFlag.AlignLeft)
        self.name_label.setText(album_name)
        self.name_label.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
        self.name_label.setStyleSheet("color: var(--text_primary);")
        layout.addWidget(self.name_label)
        
        # Shows featured artist if it's "Appears on"
        if is_appears_on:
            self.sec_label = QLabel(main_artist)
            self.sec_label.setFont(QFont("Segoe UI", 9, QFont.Weight.Normal))
            self.sec_label.setStyleSheet("color: var(--text_secondary);")
            self.sec_label.setWordWrap(True)
            self.sec_label.setFixedWidth(150)
            self.sec_label.setAlignment(Qt.AlignmentFlag.AlignLeft)
            layout.addWidget(self.sec_label)
        else:
            self.sec_label = None
            
        layout.addStretch()
        outer_layout.addWidget(self.frame)
        
        # Set fixed size for the whole card to make sure it doesn't scale / squeeze
        self.setFixedSize(158, 220 if is_appears_on else 200)
        
    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self.album_key)


class AlbumGridWidget(QWidget):
    album_clicked = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        
        # Scroll Area for horizontal layout
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll_area.setStyleSheet("background: transparent; border: none;")
        
        self.container = QWidget()
        self.container.setStyleSheet("background: transparent;")
        self.row_layout = QHBoxLayout(self.container)
        self.row_layout.setContentsMargins(0, 0, 0, 0)
        self.row_layout.setSpacing(8)  # Reduced gap/spacing (items closer together)
        self.row_layout.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        
        self.scroll_area.setWidget(self.container)
        layout.addWidget(self.scroll_area)
        
        self._albums = []
        self._is_appears_on = False

    def set_albums(self, albums, is_appears_on=False):
        self._albums = albums
        self._is_appears_on = is_appears_on
        self.rebuild_grid()

    def rebuild_grid(self, container_width: int = 0):
        # Clear existing layout items
        while self.row_layout.count():
            item = self.row_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
                
        if not self._albums:
            self.setFixedHeight(0)
            return
            
        for key, name, year, track_path, main_artist in self._albums:
            card = AlbumCard(key, name, track_path, is_appears_on=self._is_appears_on, main_artist=main_artist)
            card.clicked.connect(self.album_clicked.emit)
            self.row_layout.addWidget(card)
            
        self.row_layout.addStretch()
        # Set fixed height of this component to show cards and scrollbars beautifully without clipping
        self.setFixedHeight(238 if self._is_appears_on else 216)


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
        
        text_layout = QVBoxLayout()
        text_layout.setSpacing(4)

        # Artist Name
        self.title_label = QLabel(self.artist_name)
        self.title_label.setObjectName("playerScreenTitle")
        self.title_label.setFont(QFont("Segoe UI", 28, QFont.Weight.Bold))
        self.title_label.setStyleSheet("color: var(--text_primary);")
        
        # Track Count
        self.stats_label = QLabel()
        self.stats_label.setObjectName("emptyStateSubtitle")
        self.stats_label.setFont(QFont("Segoe UI", 11))
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
        
        albums_title = QLabel("Albums")
        albums_title.setFont(QFont("Segoe UI", 16, QFont.Weight.Bold))
        albums_title.setStyleSheet("color: var(--text_primary);")
        albums_layout.addWidget(albums_title)
        
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
        
        appears_on_title = QLabel("Appears on")
        appears_on_title.setFont(QFont("Segoe UI", 16, QFont.Weight.Bold))
        appears_on_title.setStyleSheet("color: var(--text_primary);")
        appears_layout.addWidget(appears_on_title)
        
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

        tracks_title = QLabel("Tracks")
        tracks_title.setFont(QFont("Segoe UI", 16, QFont.Weight.Bold))
        tracks_title.setStyleSheet("color: var(--text_primary);")
        tracks_layout.addWidget(tracks_title)

        self.table = QTableView()
        self.model = TracksTableModel(self)
        self.table.setModel(self.model)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(40)
        self.table.setShowGrid(False)
        self.table.horizontalHeader().setSectionResizeMode(COL_TITLE, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(COL_ARTISTS, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(COL_ALBUM, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(COL_GENRE, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(COL_DURATION, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().sectionClicked.connect(self._on_header_clicked)
        self.table.doubleClicked.connect(self._on_row_double_clicked)

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
        self.animation_timer.setInterval(120)
        self.animation_timer.timeout.connect(self._on_animation_tick)

        if self.engine:
            self.engine.playback_state_changed.connect(self._on_playback_changed)
            self.engine.track_changed.connect(self._on_playback_changed)

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

    def _on_header_clicked(self, index: int) -> None:
        self.model.sort_alphabetical(index)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.rebuild_grids_with_current_width()

    def rebuild_grids_with_current_width(self):
        # Determine available width for grids
        width = self.scroll.viewport().width() - 48
        if width <= 100:
            width = self.width() - 48
        if width < 100:
            width = 300
        
        self.albums_grid.rebuild_grid(width)
        self.appears_on_grid.rebuild_grid(width)
        self.resize_table_to_contents()

    def resize_table_to_contents(self) -> None:
        num_rows = self.model.rowCount()
        row_height = self.table.verticalHeader().defaultSectionSize() or 40
        header_height = self.table.horizontalHeader().height() or 30
        if num_rows == 0:
            self.table.setFixedHeight(0)
            return
        total_height = num_rows * row_height + header_height + 4
        self.table.setFixedHeight(total_height)

    def refresh(self) -> None:
        all_tracks = self.store.all_tracks()
        
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
            
        self.albums_grid.set_albums(albums_list, is_appears_on=False)

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
        self.rebuild_grids_with_current_width()

    def _on_row_double_clicked(self, index) -> None:
        track = self.model.track_at(index.row())
        if track:
            if track.file_missing:
                return
            self.track_double_clicked.emit(track.path)

    def _play_artist_tracks(self, shuffle: bool) -> None:
        ordered_tracks = [
            self.model.track_at(row) for row in range(self.model.rowCount())
        ]
        ordered_tracks = [t for t in ordered_tracks if t is not None and not t.file_missing]
        if not ordered_tracks:
            return
        paths = [t.path for t in ordered_tracks]
        self.play_all_requested.emit(paths, shuffle)
