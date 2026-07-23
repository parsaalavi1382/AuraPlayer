"""
GenrePageView: Dedicated page displaying details for a specific genre,
reusing the standard Tracks view styling and hover visualizers.
"""

from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal, QTimer
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QTableView,
    QHeaderView, QAbstractItemView,
)
from PyQt6.QtGui import QFont

from core.library_store import LibraryStore
from core.models import Track
from ui.models.tracks_table_model import TracksTableModel, COL_TITLE, COL_ARTISTS, COL_ALBUM, COL_GENRE, COL_DURATION
from ui.views.tracks_view import TrackHoverDelegate, HoverEventFilter
from ui.widgets.adjacent_resize_helper import AdjacentResizeHelper
from ui.widgets.drag_table_view import AuraDragTableView


class GenrePageView(QWidget):
    track_double_clicked = pyqtSignal(str)
    album_requested = pyqtSignal(str)
    artist_requested = pyqtSignal(str)
    genre_requested = pyqtSignal(str)
    play_all_requested = pyqtSignal(list, bool)

    def __init__(self, genre_name: str, store: LibraryStore, engine=None, parent=None):
        super().__init__(parent)
        self.genre_name = genre_name
        self.store = store
        self.engine = engine

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(24, 24, 24, 16)
        main_layout.setSpacing(16)

        # ------------------------------------------------------------------
        # Header Area
        # ------------------------------------------------------------------
        header_layout = QHBoxLayout()
        text_layout = QVBoxLayout()

        self.title_label = QLabel(self.genre_name)
        self.title_label.setFont(QFont("Segoe UI", 28, QFont.Weight.Bold))
        self.title_label.setStyleSheet("color: var(--text_primary);")

        self.stats_label = QLabel()
        self.stats_label.setStyleSheet("color: var(--text_secondary); font-size: 14px;")

        text_layout.addWidget(self.title_label)
        text_layout.addWidget(self.stats_label)
        header_layout.addLayout(text_layout)
        header_layout.addStretch()

        # Transport Buttons specific to the Genre
        buttons_layout = QHBoxLayout()
        self.play_btn = QPushButton("▶  Play Genre")
        self.play_btn.setObjectName("accentButton")
        self.play_btn.clicked.connect(lambda: self._play_genre_tracks(shuffle=False))

        self.shuffle_btn = QPushButton("🔀  Shuffle")
        self.shuffle_btn.clicked.connect(lambda: self._play_genre_tracks(shuffle=True))

        buttons_layout.addWidget(self.play_btn)
        buttons_layout.addWidget(self.shuffle_btn)
        header_layout.addLayout(buttons_layout)
        main_layout.addLayout(header_layout)

        # ------------------------------------------------------------------
        # Track Table Area
        # ------------------------------------------------------------------
        self.table = AuraDragTableView()
        self.model = TracksTableModel(self)
        self.table.setModel(self.model)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(40)
        self.table.setShowGrid(True)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.table.horizontalHeader().setStretchLastSection(False)
        self.table.setColumnWidth(COL_TITLE, 250)
        self.table.setColumnWidth(COL_ARTISTS, 180)
        self.table.setColumnWidth(COL_ALBUM, 180)
        self.table.setColumnWidth(COL_GENRE, 120)
        self.table.setColumnWidth(COL_DURATION, 80)
        self.resize_helper = AdjacentResizeHelper(self.table.horizontalHeader(), self.store, "tracks_table")
        self.table.horizontalHeader().sectionClicked.connect(self._on_header_clicked)
        self.table.doubleClicked.connect(self._on_row_double_clicked)

        # Context menu handler
        self.table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._show_context_menu)

        self.delegate = TrackHoverDelegate(self.table, self)
        self.table.setItemDelegate(self.delegate)
        self.table.setMouseTracking(True)
        self.hover_filter = HoverEventFilter(self.table, self.delegate, self)
        self.table.viewport().installEventFilter(self.hover_filter)

        main_layout.addWidget(self.table, stretch=1)

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

    def apply_theme_colors(self):
        theme_key = self.store.cache.settings.theme
        from ui.theme import THEMES, DEFAULT_THEME, apply_theme_vars
        theme = THEMES.get(theme_key, THEMES[DEFAULT_THEME])
        self.title_label.setStyleSheet(apply_theme_vars("color: var(--text_primary);", theme))
        self.stats_label.setStyleSheet(apply_theme_vars("color: var(--text_secondary); font-size: 14px;", theme))

    def refresh(self) -> None:
        self.apply_theme_colors()
        all_tracks = self.store.all_tracks()
        
        # Match tracks against genre (handle list structure parsed by comma separators case-insensitively)
        genre_tracks = []
        for t in all_tracks:
            if t.genre:
                genres = [g.strip().lower() for g in t.genre.split(",") if g.strip()]
                if self.genre_name.lower() in genres or t.genre.lower() == self.genre_name.lower():
                    genre_tracks.append(t)
            elif self.genre_name.lower() == "unknown genre":
                genre_tracks.append(t)

        self.model.set_tracks(genre_tracks)
        self.model.sort_alphabetical(COL_TITLE)

        self.stats_label.setText(f"Tracks in this genre: {len(genre_tracks)}")

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

        from PyQt6.QtWidgets import QMenu, QMessageBox
        from PyQt6.QtGui import QAction
        from ui.theme import THEMES, DEFAULT_THEME

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
        edit_action = QAction("Edit Metadata", self)
        remove_action = QAction("Remove Song", self)
        add_playlist_action = QAction("Add to Playlist", self)
        menu.addAction(edit_action)
        menu.addAction(remove_action)
        menu.addAction(add_playlist_action)

        edit_action.triggered.connect(lambda: self._on_edit_metadata(track))
        remove_action.triggered.connect(lambda: self._on_remove_song(track))
        add_playlist_action.triggered.connect(lambda: self._on_add_to_playlist(track))

        menu.exec(self.table.viewport().mapToGlobal(pos))

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

    def _on_header_clicked(self, index: int) -> None:
        self.model.sort_alphabetical(index)

    def _play_genre_tracks(self, shuffle: bool) -> None:
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
