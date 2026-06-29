"""
Playlists tab: Step 2 scope is the tab existing with a correct empty
state, wired to the real (currently-empty) playlists collection in
LibraryStore. Creating playlists, the cover-image picker, drag-reorder,
and the "Remove from Playlist" vs "Remove Song" distinction are all
Step 7 per the roadmap.
"""

from __future__ import annotations

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QStackedWidget, QListView

from core.library_store import LibraryStore
from ui.models.playlists_list_model import PlaylistsListModel
from ui.widgets.empty_state import EmptyStateWidget


class PlaylistsView(QWidget):
    playlist_selected = pyqtSignal(str)  # playlist id

    def __init__(self, store: LibraryStore, parent=None):
        super().__init__(parent)
        self.store = store

        outer = QVBoxLayout(self)
        outer.setContentsMargins(16, 12, 16, 0)

        self.stack = QStackedWidget()
        outer.addWidget(self.stack)

        self.empty_widget = EmptyStateWidget(
            title="No playlists yet.",
            subtitle="Playlist creation is coming in Step 7 of the build.",
        )
        self.stack.addWidget(self.empty_widget)

        self.model = PlaylistsListModel(self)
        self.list_view = QListView()
        self.list_view.setModel(self.model)
        self.stack.addWidget(self.list_view)

        self.store.playlists_changed.connect(self._on_playlists_changed)
        self.refresh()

    def refresh(self) -> None:
        playlists = self.store.all_playlists()
        if not playlists:
            self.stack.setCurrentWidget(self.empty_widget)
            return
        self.stack.setCurrentWidget(self.list_view)
        self.model.set_playlists(playlists)
        self.model.sort_alphabetical()

    def _on_playlists_changed(self, *_args) -> None:
        self.refresh()
