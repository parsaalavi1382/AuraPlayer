from __future__ import annotations

from PyQt6.QtWidgets import QMainWindow, QWidget, QVBoxLayout, QTabWidget, QMessageBox, QApplication

from core.library_store import LibraryStore
from core.playback_engine import PlaybackEngine
from ui.theme import build_stylesheet, THEMES, DEFAULT_THEME
from ui.widgets.top_bar import TopBar
from ui.widgets.bottom_bar import BottomBar
from ui.widgets.volume_output_control import VolumeOutputControl
from ui.widgets.settings_dialog import SettingsDialog
from ui.widgets.scan_progress_dialog import ScanProgressDialog
from ui.scan_worker import ScanWorker
from ui.views.tracks_view import TracksView
from ui.views.artists_view import ArtistsView
from ui.views.albums_view import AlbumsView
from ui.views.playlists_view import PlaylistsView


class MainWindow(QMainWindow):
    def __init__(self, store: LibraryStore):
        super().__init__()
        self.store = store
        self.engine = PlaybackEngine(store)
        self.setWindowTitle("AuraPlayer")
        self.resize(1000, 680)

        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # --- Top Bar ---
        self.top_bar = TopBar()
        self.top_bar.settings_clicked.connect(self._open_settings)
        self.top_bar.search_clicked.connect(self._on_search_clicked)
        layout.addWidget(self.top_bar)

        # --- Main Tabs ---
        self.tabs = QTabWidget()
        self.tracks_view = TracksView(self.store)
        self.artists_view = ArtistsView(self.store)
        self.albums_view = AlbumsView(self.store)
        self.playlists_view = PlaylistsView(self.store)

        self.tabs.addTab(self.tracks_view, "Tracks")
        self.tabs.addTab(self.artists_view, "Artists")
        self.tabs.addTab(self.albums_view, "Albums")
        self.tabs.addTab(self.playlists_view, "Playlists")
        layout.addWidget(self.tabs, stretch=1)

        self.tracks_view.settings_requested.connect(self._open_settings)

        # --- Bottom Persistent Transport Bar ---
        self.bottom_bar = BottomBar()
        layout.addWidget(self.bottom_bar)

        # --- Volume & Output Device Controls ---
        self.volume_output_control = VolumeOutputControl()
        self.volume_output_control.set_volume(self.engine.get_volume())
        self.volume_output_control.set_available_devices(
            self.engine.list_output_devices(), self.engine.current_output_device()
        )
        self.volume_output_control.volume_changed.connect(self.engine.set_volume)
        self.volume_output_control.output_device_selected.connect(self.engine.set_output_device)
        self.engine.volume_changed.connect(self.volume_output_control.set_volume)

        # --- Signals & Navigation ---
        self.tracks_view.track_double_clicked.connect(self._on_track_double_clicked)
        self.tracks_view.play_all_requested.connect(self._on_play_all_requested)
        self.artists_view.artist_selected.connect(
            lambda name: self._stub_navigate(f'Artist Page: "{name}"')
        )
        self.albums_view.album_selected.connect(
            lambda key: self._stub_navigate(f'Album Page: "{key}"')
        )

        # --- Transport Control Wiring ---
        self.bottom_bar.play_pause_clicked.connect(self.engine.toggle_play_pause)
        self.bottom_bar.next_clicked.connect(self.engine.next_track)
        self.bottom_bar.previous_clicked.connect(self.engine.prev_track)

        # --- Continuous Press-and-Hold Seek Wiring ---
        self.bottom_bar.next_hold_started.connect(self.engine.start_seek_forward)
        self.bottom_bar.next_hold_stopped.connect(self.engine.stop_seek)
        self.bottom_bar.prev_hold_started.connect(self.engine.start_seek_back)
        self.bottom_bar.prev_hold_stopped.connect(self.engine.stop_seek)

        self.engine.track_changed.connect(self._on_engine_track_changed)
        self.engine.playback_state_changed.connect(self._on_engine_playback_state_changed)
        self.engine.position_changed.connect(self.bottom_bar.set_position)
        self.engine.error_occurred.connect(self._on_engine_error)

        # --- Restore Session State ---
        restored_track = self.engine.get_current_track()
        if restored_track:
            self.bottom_bar.set_current_track(restored_track)
            self.bottom_bar.set_playing(self.engine.is_playing())

        self._scan_worker: ScanWorker | None = None
        self._progress_dialog: ScanProgressDialog | None = None

        startup_theme = THEMES.get(self.store.cache.settings.theme, THEMES[DEFAULT_THEME])
        self.tracks_view.model.set_danger_color(startup_theme["danger"])

    # ---------- Settings & Library Scanning ----------

    def _open_settings(self) -> None:
        dialog = SettingsDialog(self.store, self)
        dialog.folders_added.connect(self._start_scan)
        dialog.folder_removed.connect(lambda _f: self._refresh_all_views())
        dialog.theme_changed.connect(self._apply_theme)
        dialog.exec()

    def _apply_theme(self, theme_key: str) -> None:
        app = QApplication.instance()
        if app is not None:
            app.setStyleSheet(build_stylesheet(theme_key))
        theme = THEMES.get(theme_key, THEMES[DEFAULT_THEME])
        self.tracks_view.model.set_danger_color(theme["danger"])

    def _start_scan(self, folders: list[str]) -> None:
        self._progress_dialog = ScanProgressDialog(self)
        self._scan_worker = ScanWorker(self.store.cache, folders, self)
        self._scan_worker.progress.connect(self._progress_dialog.update_progress)
        self._scan_worker.finished_scan.connect(self._on_scan_finished)
        self._progress_dialog.show()
        self._scan_worker.start()

    def _on_scan_finished(self, summary: dict) -> None:
        if self._progress_dialog:
            self._progress_dialog.close()
            self._progress_dialog = None

        self._refresh_all_views()
        msg = f"Scan complete.\n\nNew tracks: {summary['added']}\nAlready in library: {summary['skipped']}"
        if summary["missing"]:
            msg += f"\nMissing files flagged: {len(summary['missing'])}"
        QMessageBox.information(self, "Scan complete", msg)

    def _refresh_all_views(self) -> None:
        self.tracks_view.refresh()
        self.artists_view.refresh()
        self.albums_view.refresh()
        self.playlists_view.refresh()

    # ---------- Playback Management ----------

    def _on_track_double_clicked(self, track_path: str) -> None:
        """Handles manual track selection from the visible table list view."""
        model = self.tracks_view.model
        ordered_tracks = [model.track_at(row) for row in range(model.rowCount())]
        all_paths = [t.path for t in ordered_tracks if t is not None and not t.file_missing]
        
        if track_path not in all_paths:
            return
            
        current_shuffle = self.engine.get_shuffle()
        self.engine.play_all(
            all_paths, 
            shuffle=current_shuffle, 
            start_track_path=track_path
        )

    def _on_play_all_requested(self, paths: list[str], shuffle: bool) -> None:
        self.engine.play_all(paths, shuffle=shuffle)

    def _on_engine_track_changed(self, track_path: str) -> None:
        track = self.store.get_track(track_path) if track_path else None
        self.bottom_bar.set_current_track(track)
        self.bottom_bar.set_playing(self.engine.is_playing())
        self.tracks_view.model.set_currently_playing(track_path or None)

    def _on_engine_playback_state_changed(self, state: str) -> None:
        self.bottom_bar.set_playing(state == "playing")

    def _on_engine_error(self, track_path: str, message: str) -> None:
        track = self.store.get_track(track_path) if track_path else None
        name = track.title if track else (track_path or "the current track")
        QMessageBox.warning(
            self, "Playback error",
            f'Could not play "{name}".\n\n{message}'
        )

    # ---------- Navigation UI Stubs ----------

    def _stub_navigate(self, where: str) -> None:
        QMessageBox.information(
            self, "Coming in a later step",
            f"This would navigate to {where}.\n\nThat screen is built in Step 4/5."
        )

    def _on_search_clicked(self) -> None:
        QMessageBox.information(
            self, "Coming in Step 9",
            "Global database search functionality lands in Step 9."
        )