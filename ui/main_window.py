"""
Main window: top bar + tabs (Tracks/Artists/Albums/Playlists) + always-
visible bottom bar, per the Main/Menu Screen spec.

This is the Step 2 deliverable's centerpiece -- the first time the
scanned library data (from Step 1) is visible in the real PyQt6 UI
rather than printed to a console.
"""

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

        # --- Top bar ---
        self.top_bar = TopBar()
        self.top_bar.settings_clicked.connect(self._open_settings)
        self.top_bar.search_clicked.connect(self._on_search_clicked)
        layout.addWidget(self.top_bar)

        # --- Tabs ---
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

        # The empty-state "Open Settings" button (shown when the Tracks
        # tab has no library yet) calls the exact same _open_settings
        # method as the ⚙ gear icon below -- not a separate code path,
        # so the two can never drift apart in behavior.
        self.tracks_view.settings_requested.connect(self._open_settings)

        # --- Bottom bar (always visible) ---
        self.bottom_bar = BottomBar()
        layout.addWidget(self.bottom_bar)

        # --- Volume + output device control ---
        # Per spec this lives on the Player Screen (Step 4), bottom-
        # right, NOT in the Main Menu's bottom bar or top bar. Built and
        # fully wired to the engine now so Step 4 only needs to place it
        # in a layout (self.volume_output_control) -- no rewiring.
        self.volume_output_control = VolumeOutputControl()
        self.volume_output_control.set_volume(self.engine.get_volume())
        self.volume_output_control.set_available_devices(
            self.engine.list_output_devices(), self.engine.current_output_device()
        )
        self.volume_output_control.volume_changed.connect(self.engine.set_volume)
        self.volume_output_control.output_device_selected.connect(self.engine.set_output_device)
        self.engine.volume_changed.connect(self.volume_output_control.set_volume)

        # Navigation/playback signals from views. Artist/Album page
        # navigation isn't built yet (Step 5), so those still surface a
        # stub -- but playback (double-clicking a track, Play All,
        # Shuffle) is real now that the engine exists.
        self.tracks_view.track_double_clicked.connect(self._on_track_double_clicked)
        self.tracks_view.play_all_requested.connect(self._on_play_all_requested)
        self.artists_view.artist_selected.connect(
            lambda name: self._stub_navigate(f'Artist Page: "{name}"')
        )
        self.albums_view.album_selected.connect(
            lambda key: self._stub_navigate(f'Album Page: "{key}"')
        )

        # --- Bottom bar transport wiring ---
        self.bottom_bar.play_pause_clicked.connect(self.engine.toggle_play_pause)
        self.bottom_bar.next_clicked.connect(self.engine.next_track)
        self.bottom_bar.previous_clicked.connect(self.engine.previous_track)

        self.engine.track_changed.connect(self._on_engine_track_changed)
        self.engine.playback_state_changed.connect(self._on_engine_playback_state_changed)
        self.engine.position_changed.connect(self.bottom_bar.set_position)
        self.engine.error_occurred.connect(self._on_engine_error)

        # If a track was restored from a previous session (see
        # PlaybackEngine._restore_initial_state), reflect it in the
        # bottom bar immediately rather than waiting for the next
        # track_changed signal, which won't fire again for a track
        # that's already loaded.
        restored_track = self.engine.get_current_track()
        if restored_track:
            self.bottom_bar.set_current_track(restored_track)
            self.bottom_bar.set_playing(self.engine.is_playing())

        self._scan_worker: ScanWorker | None = None
        self._progress_dialog: ScanProgressDialog | None = None

        # Make sure the Tracks model's missing-file red matches whatever
        # theme was loaded from disk on startup -- not just the dark
        # theme's red, which would otherwise show briefly-but-wrongly
        # until Settings is reopened.
        startup_theme = THEMES.get(self.store.cache.settings.theme, THEMES[DEFAULT_THEME])
        self.tracks_view.model.set_danger_color(startup_theme["danger"])

    # ---------- Settings / scanning ----------

    def _open_settings(self) -> None:
        dialog = SettingsDialog(self.store, self)
        dialog.folders_added.connect(self._start_scan)
        dialog.folder_removed.connect(lambda _f: self._refresh_all_views())
        dialog.theme_changed.connect(self._apply_theme)
        dialog.exec()

    def _apply_theme(self, theme_key: str) -> None:
        """Re-applies the global stylesheet immediately -- no restart,
        no re-opening Settings needed to see the change take effect.
        """
        app = QApplication.instance()
        if app is not None:
            app.setStyleSheet(build_stylesheet(theme_key))
        # The missing-file red in the Tracks table is theme-dependent
        # (each theme defines its own danger color), so push it into
        # the model rather than leave the row painted in the old
        # theme's red after switching.
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

        # The worker mutated cache directly (it's running on the cache
        # object, not through LibraryStore's mutators, since it's off-
        # thread and we don't want to emit Qt signals from a worker
        # thread into widgets directly). Refresh all views now that
        # we're back on the main thread.
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

    # ---------- Playback (real, via PlaybackEngine) ----------

    def _on_track_double_clicked(self, track_path: str) -> None:
        """Double-clicking a track in the Tracks view starts a fresh
        queue of the library's current track order, beginning playback
        at the clicked track -- matches "clicking any track starts
        playback" from the spec. (A full Player Screen to navigate to
        is still Step 4; for now this only starts playback.)
        """
        all_paths = [t.path for t in self.store.all_tracks() if not t.file_missing]
        if track_path not in all_paths:
            return
        self.engine.play_all(all_paths, shuffle=False, start_track_path=track_path)

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

    # ---------- Stubs for not-yet-built screens ----------

    def _stub_navigate(self, where: str) -> None:
        QMessageBox.information(
            self, "Coming in a later step",
            f"This would navigate to {where}.\n\nThat screen is built in Step 4/5."
        )

    def _on_search_clicked(self) -> None:
        QMessageBox.information(
            self, "Coming in Step 9",
            "Search across Tracks/Artists/Albums/Playlists is built in Step 9, "
            "once all four views and their data are stable."
        )
