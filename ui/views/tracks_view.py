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

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTableView, QPushButton, QMenu,
    QHeaderView, QStackedWidget, QMessageBox, QAbstractItemView,
)
from PyQt6.QtGui import QAction

from core.library_store import LibraryStore
from ui.models.tracks_table_model import TracksTableModel, COL_TITLE, COL_ARTISTS, COL_ALBUM, COL_DURATION
from ui.widgets.empty_state import EmptyStateWidget


class TracksView(QWidget):
    track_double_clicked = pyqtSignal(str)   # track path -> go to Player Screen
    album_requested = pyqtSignal(str)         # album_key -> go to Album page
    artist_requested = pyqtSignal(str)        # artist name -> go to Artist page
    play_all_requested = pyqtSignal(list, bool)  # track paths, shuffle
    settings_requested = pyqtSignal()         # "Open Settings" empty-state button clicked

    def __init__(self, store: LibraryStore, parent=None):
        super().__init__(parent)
        self.store = store

        outer = QVBoxLayout(self)
        outer.setContentsMargins(16, 12, 16, 0)
        outer.setSpacing(8)

        # --- Shuffle / Play All row ---
        action_row = QHBoxLayout()
        self.play_all_btn = QPushButton("▶  Play All")
        self.play_all_btn.setObjectName("accentButton")
        self.shuffle_btn = QPushButton("🔀  Shuffle")
        action_row.addWidget(self.play_all_btn)
        action_row.addWidget(self.shuffle_btn)
        action_row.addStretch()
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

        self.table = QTableView()
        self.model = TracksTableModel(self)
        self.table.setModel(self.model)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        self.table.setShowGrid(False)
        self.table.horizontalHeader().setSectionResizeMode(COL_TITLE, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(COL_ARTISTS, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(COL_ALBUM, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(COL_DURATION, QHeaderView.ResizeMode.ResizeToContents)
        self.table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._show_context_menu)
        self.table.doubleClicked.connect(self._on_row_double_clicked)
        self.stack.addWidget(self.table)

        # --- Wire to store ---
        self.store.tracks_added.connect(self._on_tracks_changed)
        self.store.track_removed.connect(self._on_tracks_changed)
        self.store.track_updated.connect(self._on_tracks_changed)

        self.refresh()

    # ---------- Data refresh ----------

    def refresh(self) -> None:
        tracks = self.store.all_tracks()
        if not tracks:
            self.stack.setCurrentWidget(self.empty_widget)
            return
        self.stack.setCurrentWidget(self.table)
        self.model.set_tracks(tracks)
        self.model.sort_alphabetical(COL_TITLE)  # default sort per spec

    def _on_tracks_changed(self, *_args) -> None:
        self.refresh()

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
        track = self.model.track_at(index.row())
        if not track:
            return

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

        menu.exec(self.table.viewport().mapToGlobal(pos))

    def _on_edit_metadata(self, track) -> None:
        QMessageBox.information(
            self, "Coming in Step 6",
            "Metadata editing (writing changes back to the file) is built in Step 6, "
            "right after the Player Screen and navigation are in place."
        )

    def _on_remove_song(self, track) -> None:
        reply = QMessageBox.question(
            self, "Remove song?",
            f'Remove "{track.title}" from your library?\n\n'
            "This only removes it from the library -- the file itself is not deleted.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            self.store.remove_track(track.path)

    def _on_add_to_playlist(self, track) -> None:
        QMessageBox.information(
            self, "Coming in Step 7",
            "Playlists are built in Step 7. This menu item will let you add this "
            "track to one once playlists exist."
        )
