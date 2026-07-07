"""
MainWindow: top-level application window for AuraPlayer.

Step 3+4 additions:
- PlayerScreen overlay (slides up on bottom-bar click, slides down on back)
- SVG icon cache invalidation on theme change
- Album art loaded via get_album_art() when the current track changes and
  pushed to both the bottom bar thumbnail and the Player Screen
- Bottom bar click-zone wiring (title → album stub, artist → artist stub,
  anywhere else → Player Screen)
- PlayerScreen transport signals wired to the same engine methods as the
  bottom bar, so both control surfaces always stay in sync
- Min window size enforced (500×700) while the Player Screen is visible
"""

from __future__ import annotations

from PyQt6.QtCore import QSize, Qt
from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QTabWidget, QTabBar,
    QMessageBox, QApplication,
)

from core.library_store import LibraryStore
from core.playback_engine import PlaybackEngine
from core.metadata_reader import get_album_art
from ui.theme import build_stylesheet, THEMES, DEFAULT_THEME
from ui.svg_icon import clear_cache as clear_icon_cache
from ui.widgets.top_bar import TopBar
from ui.widgets.bottom_bar import BottomBar
from ui.widgets.settings_dialog import SettingsDialog
from ui.widgets.scan_progress_dialog import ScanProgressDialog
from core.sync_manager import SyncManager
from ui.sync_worker import SyncWorker
from ui.views.tracks_view import TracksView
from ui.views.artists_view import ArtistsView
from ui.views.genres_view import GenresView
from ui.views.albums_view import AlbumsView
from ui.views.playlists_view import PlaylistsView
from ui.views.player_screen import PlayerScreen
from ui.views.artist_page_view import ArtistPageView
from ui.views.album_page_view import AlbumPageView
from ui.views.genre_page_view import GenrePageView

_MIN_SIZE_NORMAL = QSize(800, 560)
_MIN_SIZE_PLAYER = QSize(500, 700)


class MainWindow(QMainWindow):
    def __init__(self, store: LibraryStore):
        super().__init__()
        self.store = store
        self.engine = PlaybackEngine(store)
        self.setWindowTitle("AuraPlayer")
        
        import os
        import sys
        from utils.paths import get_resource_path
        # For PySide6, simply use: from PySide6.QtGui import QIcon
        from PyQt6.QtGui import QIcon
        
        # Windows taskbar icon fix: prevent grouping with python.exe and load distinct icon
        if sys.platform == 'win32':
            try:
                import ctypes
                myappid = 'parsaalavi.auraplayer.musicplayer.1.0'
                ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(myappid)
            except Exception:
                pass

        # Multi-size high-resolution icon registration for crisp rendering on High-DPI/4K screens
        icon = QIcon()
        ico_path = get_resource_path("assets", "logo.ico")
        icns_path = get_resource_path("assets", "logo.icns")
        png_path = get_resource_path("assets", "logo.png")
        
        if sys.platform == "win32" and os.path.exists(ico_path):
            icon = QIcon(ico_path)
        elif sys.platform == "darwin" and os.path.exists(icns_path):
            icon = QIcon(icns_path)
        elif os.path.exists(png_path):
            icon = QIcon(png_path)
            
        self.setWindowIcon(icon)

        self.resize(1000, 680)
        self.setMinimumSize(_MIN_SIZE_NORMAL)

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

        # --- Content Area (Tabs + Side Queue Panel) ---
        content_layout = QHBoxLayout()
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(0)

        # --- Main Tabs ---
        self.tabs = QTabWidget()
        self.tabs.setTabsClosable(True)
        self.tabs.tabCloseRequested.connect(self._on_tab_close_requested)

        self.tracks_view = TracksView(self.store, self.engine)
        self.artists_view = ArtistsView(self.store)
        self.genres_view = GenresView(self.store)
        self.albums_view = AlbumsView(self.store)
        self.playlists_view = PlaylistsView(self.store)

        self.tabs.addTab(self.tracks_view, "Tracks")
        self.tabs.addTab(self.artists_view, "Artists")
        self.tabs.addTab(self.genres_view, "Genres")
        self.tabs.addTab(self.albums_view, "Albums")
        self.tabs.addTab(self.playlists_view, "Playlists")
        content_layout.addWidget(self.tabs, stretch=1)

        from ui.widgets.queue_panel import QueuePanel
        self.main_queue_panel = QueuePanel(self.store, self.engine)
        self.main_queue_panel.setMinimumWidth(0)
        self.main_queue_panel.setMaximumWidth(0)
        content_layout.addWidget(self.main_queue_panel)

        layout.addLayout(content_layout, stretch=1)

        from PyQt6.QtCore import QPropertyAnimation, QEasingCurve
        self._main_queue_active = False
        self._main_queue_anim = QPropertyAnimation(self.main_queue_panel, b"maximumWidth")
        self._main_queue_anim.setDuration(320)
        self._main_queue_anim.setEasingCurve(QEasingCurve.Type.InOutQuad)
        self._main_queue_anim.finished.connect(self._on_main_queue_anim_finished)

        self.main_queue_panel.close_requested.connect(self._toggle_main_queue)

        # Hide close buttons on permanent tabs (indices 0 to 4)
        tab_bar = self.tabs.tabBar()
        for i in range(5):
            tab_bar.setTabButton(i, QTabBar.ButtonPosition.RightSide, None)

        self.tracks_view.settings_requested.connect(self._open_settings)

        # --- Bottom Persistent Transport Bar ---
        self.bottom_bar = BottomBar()
        layout.addWidget(self.bottom_bar)

        self.bottom_bar.queue_clicked.connect(self._toggle_main_queue)

        # --- Player Screen Overlay (child of MainWindow, not central) ---
        self.player_screen = PlayerScreen(self)

        # --- Volume & Output Device Controls (wired to PlayerScreen & BottomBar) ---
        self.player_screen.set_volume(self.engine.get_volume())
        self.player_screen.set_available_devices(
            self.engine.list_output_devices(), self.engine.current_output_device(), self.engine.is_using_default_device()
        )
        self.player_screen.volume_changed.connect(self.engine.set_volume)
        self.player_screen.output_device_selected.connect(self.engine.set_output_device)
        self.engine.volume_changed.connect(self.player_screen.set_volume)

        self.bottom_bar.set_volume(self.engine.get_volume())
        self.bottom_bar.set_available_devices(
            self.engine.list_output_devices(), self.engine.current_output_device(), self.engine.is_using_default_device()
        )
        self.bottom_bar.volume_changed.connect(self.engine.set_volume)
        self.bottom_bar.output_device_selected.connect(self.engine.set_output_device)
        self.engine.volume_changed.connect(self.bottom_bar.set_volume)

        # Monitor device updates to keep headphone menu fresh
        from PyQt6.QtMultimedia import QMediaDevices
        self._media_devices = QMediaDevices(self)
        self._media_devices.audioOutputsChanged.connect(self._on_audio_devices_changed)
        self.engine.output_device_changed.connect(self._on_audio_devices_changed)

        # --- Apply initial theme (must happen before wiring icons) ---
        startup_theme_key = self.store.cache.settings.theme
        self._apply_theme(startup_theme_key, save=False)

        # --- Engine signals → UI ---
        self.engine.track_changed.connect(self._on_engine_track_changed)
        self.engine.playback_state_changed.connect(self._on_engine_playback_state_changed)
        self.engine.position_changed.connect(self._on_engine_position_changed)
        self.engine.error_occurred.connect(self._on_engine_error)

        # --- Bottom bar transport wiring ---
        self.bottom_bar.play_pause_clicked.connect(self.engine.toggle_play_pause)
        self.bottom_bar.next_clicked.connect(self.engine.next_track)
        # self.bottom_bar.previous_clicked.connect(self.engine.previous_track)
        
        # Traceback (most recent call last):
        # File "d:\Apps\AuraPlayer\main.py", line 43, in <module>
        #     main()
        #     ~~~~^^
        # File "d:\Apps\AuraPlayer\main.py", line 36, in main
        #     window = MainWindow(store)
        # File "d:\Apps\AuraPlayer\ui\main_window.py", line 111, in __init__
        #     self.bottom_bar.previous_clicked.connect(self.engine.previous_track)
        #                                             ^^^^^^^^^^^^^^^^^^^^^^^^^^
        # AttributeError: 'PlaybackEngine' object has no attribute 'previous_track'. Did you mean: 'prev_track'
        
        self.bottom_bar.previous_clicked.connect(self.engine.prev_track)
        self.bottom_bar.next_hold_started.connect(self.engine.start_seek_forward)
        self.bottom_bar.next_hold_stopped.connect(self.engine.stop_seek)
        self.bottom_bar.prev_hold_started.connect(self.engine.start_seek_back)
        self.bottom_bar.prev_hold_stopped.connect(self.engine.stop_seek)

        # --- Bottom bar click-zone wiring ---
        self.bottom_bar.bar_clicked.connect(self._open_player_screen)
        self.bottom_bar.title_clicked.connect(self._on_bottom_bar_title_clicked)
        self.bottom_bar.artist_clicked.connect(self.open_artist_page)
        self.bottom_bar.shuffle_clicked.connect(
            lambda: self.engine.set_shuffle(not self.engine.get_shuffle())
        )
        self.bottom_bar.repeat_clicked.connect(self._cycle_repeat_mode)
        self.bottom_bar.lyric_clicked.connect(self._on_bottom_bar_lyric_clicked)
        self.bottom_bar.seek_requested.connect(self.engine.seek)

        # --- Player Screen wiring ---
        self.player_screen.back_clicked.connect(self._close_player_screen)
        self.player_screen.play_pause_clicked.connect(self.engine.toggle_play_pause)
        self.player_screen.next_clicked.connect(self.engine.next_track)
        # self.player_screen.previous_clicked.connect(self.engine.previous_track)
        self.player_screen.previous_clicked.connect(self.engine.prev_track)
        self.player_screen.next_hold_started.connect(self.engine.start_seek_forward)
        self.player_screen.next_hold_stopped.connect(self.engine.stop_seek)
        self.player_screen.prev_hold_started.connect(self.engine.start_seek_back)
        self.player_screen.prev_hold_stopped.connect(self.engine.stop_seek)
        self.player_screen.seek_requested.connect(self.engine.seek)
        self.player_screen.shuffle_clicked.connect(
            lambda: self.engine.set_shuffle(not self.engine.get_shuffle())
        )
        self.player_screen.repeat_clicked.connect(self._cycle_repeat_mode)
        self.player_screen.title_clicked.connect(self._on_bottom_bar_title_clicked)
        self.player_screen.artist_clicked.connect(self.open_artist_page)

        # Queue panel navigation links
        self.main_queue_panel.album_requested.connect(self.open_album_page)
        self.main_queue_panel.artist_requested.connect(self.open_artist_page)
        self.player_screen._queue_panel.album_requested.connect(self.open_album_page)
        self.player_screen._queue_panel.artist_requested.connect(self.open_artist_page)

        # Keep Player Screen and Bottom Bar in sync with engine mode state
        self.engine.shuffle_changed.connect(self.player_screen.set_shuffle)
        self.engine.repeat_mode_changed.connect(self.player_screen.set_repeat_mode)
        self.engine.shuffle_changed.connect(self.bottom_bar.set_shuffle)
        self.engine.repeat_mode_changed.connect(self.bottom_bar.set_repeat_mode)

        # Initialize button states to match engine
        self.player_screen.set_shuffle(self.engine.get_shuffle())
        self.player_screen.set_repeat_mode(self.engine.get_repeat_mode())
        self.bottom_bar.set_shuffle(self.engine.get_shuffle())
        self.bottom_bar.set_repeat_mode(self.engine.get_repeat_mode())

        # --- TracksView play signals ---
        self.tracks_view.track_double_clicked.connect(self._on_track_double_clicked)
        self.tracks_view.play_all_requested.connect(self._on_play_all_requested)
        self.tracks_view.artist_requested.connect(self.open_artist_page)
        self.tracks_view.album_requested.connect(self.open_album_page)
        self.tracks_view.genre_requested.connect(self.open_genre_page)

        # --- Artist / Genre / Album navigation from tab views ---
        self.artists_view.artist_selected.connect(self.open_artist_page)
        self.genres_view.genre_selected.connect(self.open_genre_page)
        self.albums_view.album_selected.connect(self.open_album_page)
        self.albums_view.artist_selected.connect(self.open_artist_page)

        # --- Restore session state into UI ---
        self.player_screen.set_shuffle(self.engine.get_shuffle())
        self.player_screen.set_repeat_mode(self.engine.get_repeat_mode())

        restored_track = self.engine.get_current_track()
        if restored_track:
            self.bottom_bar.set_current_track(restored_track)
            self.bottom_bar.set_playing(self.engine.is_playing())
            self._load_and_push_art(restored_track.path)
            self.player_screen.set_playing(self.engine.is_playing())

        self._sync_worker: SyncWorker | None = None
        self._progress_dialog: ScanProgressDialog | None = None

        # --- Sync setup ---
        import os
        from PyQt6.QtCore import QTimer
        cache_dir = os.path.dirname(self.store.cache.cache_path)
        self.sync_manager = SyncManager(self.store, cache_dir)

        # Setup background auto-sync timer (every 30 seconds)
        self.sync_timer = QTimer(self)
        self.sync_timer.setInterval(30000)  # 30 seconds
        self.sync_timer.timeout.connect(self._run_background_sync)
        self.sync_timer.start()

        # Trigger startup sync shortly after window loads
        QTimer.singleShot(100, self._run_startup_sync)

    # ------------------------------------------------------------------
    # Theme application
    # ------------------------------------------------------------------

    def _apply_theme(self, theme_key: str, save: bool = True) -> None:
        app = QApplication.instance()
        if app is not None:
            app.setStyleSheet(build_stylesheet(theme_key))

        theme = THEMES.get(theme_key, THEMES[DEFAULT_THEME])

        # Invalidate SVG icon cache so next icon request re-renders in
        # the new palette. Must happen BEFORE calling apply_theme() on
        # any widget that immediately re-renders icons.
        clear_icon_cache()

        # Push new colors to widgets that own SVG icons
        self.top_bar.apply_theme(theme)
        self.bottom_bar.apply_theme(theme)
        self.player_screen.apply_theme(theme)
        self.main_queue_panel.apply_theme(theme)

        # Tracks table danger color
        self.tracks_view.model.set_danger_color(theme["danger"])

        # Refresh all permanent views and dynamic tab views to pick up new colors
        for i in range(self.tabs.count()):
            widget = self.tabs.widget(i)
            if widget and hasattr(widget, "refresh"):
                try:
                    widget.refresh()
                except Exception:
                    pass
        self._refresh_all_views()

        if save:
            self.store.cache.settings.theme = theme_key
            self.store.cache.save()

    # ------------------------------------------------------------------
    # Settings & scanning / syncing
    # ------------------------------------------------------------------

    def _open_settings(self) -> None:
        dialog = SettingsDialog(self.store, self)
        dialog.folders_added.connect(lambda f: self._start_sync(f, is_initial=True))
        dialog.folder_removed.connect(lambda _f: self._refresh_all_views())
        dialog.sync_requested.connect(lambda: self._start_sync(list(self.store.cache.settings.music_folders), is_initial=True))
        dialog.theme_changed.connect(self._apply_theme)
        dialog.exec()

    def check_missing_folders(self) -> bool:
        """
        Checks if any of the configured folders are missing.
        Prompts the user with Delete/Resync options.
        Returns True if we can proceed with sync, or False if we should cancel.
        """
        import os
        folders = list(self.store.cache.settings.music_folders)
        for folder in folders:
            while not os.path.isdir(folder):
                # Ensure the folder is still in settings (might have been deleted in previous loop iteration)
                if folder not in self.store.cache.settings.music_folders:
                    break

                msg_box = QMessageBox(self)
                msg_box.setWindowTitle("Folder is missing")
                msg_box.setText(
                    f"The music folder is missing:\n{folder}\n\n"
                    "It may have been moved, deleted, or is currently unreachable."
                )
                delete_btn = msg_box.addButton("Delete (Remove from Library)", QMessageBox.ButtonRole.DestructiveRole)
                resync_btn = msg_box.addButton("Resync (Try Again)", QMessageBox.ButtonRole.AcceptRole)
                cancel_btn = msg_box.addButton("Cancel", QMessageBox.ButtonRole.RejectRole)
                
                msg_box.exec()
                
                clicked = msg_box.clickedButton()
                if clicked == delete_btn:
                    self.store.remove_folder(folder)
                    self._refresh_all_views()
                    break
                elif clicked == resync_btn:
                    # Continue the while loop to check path again
                    continue
                else:
                    # Cancel
                    return False
        return True

    def _start_sync(self, folders: list[str], is_initial: bool = False) -> None:
        """
        Starts a sync operation.
        If is_initial is True, it locks the app using a modal ScanProgressDialog.
        Otherwise, it runs silently in the background.
        """
        if self._sync_worker is not None and self._sync_worker.isRunning():
            return

        if not self.check_missing_folders():
            return

        if is_initial:
            self._progress_dialog = ScanProgressDialog(self)
            self._progress_dialog.setModal(True)  # Lock the app!
            self._progress_dialog.setWindowTitle("Scanning music folders...")
            self._progress_dialog.show()

        self._sync_worker = SyncWorker(self.sync_manager, folders, self)
        
        if is_initial:
            self._sync_worker.progress.connect(self._progress_dialog.update_progress)
            self._sync_worker.finished_sync.connect(self._on_initial_sync_finished)
        else:
            self._sync_worker.finished_sync.connect(self._on_background_sync_finished)
            
        self._sync_worker.start()

    def _on_initial_sync_finished(self, summary: dict) -> None:
        if self._progress_dialog:
            self._progress_dialog.close()
            self._progress_dialog = None
        self._refresh_all_views()
        msg = (
            f"Scan complete.\n\n"
            f"Added tracks: {summary['added']}\n"
            f"Deleted tracks: {summary['deleted']}\n"
            f"Updated tracks: {summary['edited']}"
        )
        QMessageBox.information(self, "Scan complete", msg)

    def _on_background_sync_finished(self, summary: dict) -> None:
        if summary["added"] > 0 or summary["deleted"] > 0 or summary["edited"] > 0:
            self._refresh_all_views()

    def _run_startup_sync(self) -> None:
        folders = list(self.store.cache.settings.music_folders)
        if folders:
            self._start_sync(folders, is_initial=False)

    def _run_background_sync(self) -> None:
        folders = list(self.store.cache.settings.music_folders)
        if folders:
            self._start_sync(folders, is_initial=False)

    def _refresh_all_views(self) -> None:
        self.tracks_view.refresh()
        self.artists_view.refresh()
        self.albums_view.refresh()
        self.playlists_view.refresh()

    # ------------------------------------------------------------------
    # Playback management
    # ------------------------------------------------------------------

    def _on_track_double_clicked(self, track_path: str) -> None:
        current_widget = self.tabs.currentWidget()
        all_paths = []
        
        # If the active tab has a standard tracks model (Tracks, Artist, Genre, etc.)
        if current_widget and hasattr(current_widget, "model") and current_widget.model:
            model = current_widget.model
            all_paths = [
                model.track_at(r).path
                for r in range(model.rowCount())
                if model.track_at(r) and not model.track_at(r).file_missing
            ]
        # If the active tab is AlbumPageView which has multiple tables and self.album_tracks
        elif current_widget and hasattr(current_widget, "album_tracks") and current_widget.album_tracks:
            all_paths = [
                t.path
                for t in current_widget.album_tracks
                if not t.file_missing
            ]
            
        if not all_paths or track_path not in all_paths:
            # Fallback to Tracks view model
            model = self.tracks_view.model
            all_paths = [
                model.track_at(r).path
                for r in range(model.rowCount())
                if model.track_at(r) and not model.track_at(r).file_missing
            ]
            
        if track_path not in all_paths:
            return
            
        self.engine.play_all(
            all_paths,
            shuffle=self.engine.get_shuffle(),
            start_track_path=track_path,
        )

    def _on_play_all_requested(self, paths: list[str], shuffle: bool) -> None:
        self.engine.play_all(paths, shuffle=shuffle)

    def _cycle_repeat_mode(self) -> None:
        cycle = {"off": "all", "all": "one", "one": "off"}
        self.engine.set_repeat_mode(cycle[self.engine.get_repeat_mode()])

    # ------------------------------------------------------------------
    # Engine signal handlers
    # ------------------------------------------------------------------

    def _on_engine_track_changed(self, track_path: str) -> None:
        track = self.store.get_track(track_path) if track_path else None
        self.bottom_bar.set_current_track(track)
        self.bottom_bar.set_playing(self.engine.is_playing())
        self.tracks_view.model.set_currently_playing(track_path or None)

        if track:
            self._load_and_push_art(track_path)
        else:
            self.player_screen.set_track("No track", "", None)

    def _load_and_push_art(self, track_path: str) -> None:
        """Load album art for track_path (may be None for untagged files)
        and push it to both the bottom bar thumbnail and Player Screen.
        This is a synchronous read on the main thread -- acceptable for
        single-track art loads at track-change time. If art loading ever
        becomes a bottleneck for very large embedded images, move to a
        QThread; at MAX_ARTWORK_SIZE=300 the decode is typically <5ms.
        """
        art = get_album_art(track_path)
        self.bottom_bar.set_art(art)
        self.player_screen.set_track(
            self.store.get_track(track_path).title if self.store.get_track(track_path) else "",
            ", ".join(self.store.get_track(track_path).artists)
            if self.store.get_track(track_path) else "",
            art,
            track_path,
        )

    def _on_engine_playback_state_changed(self, state: str) -> None:
        is_playing = state == "playing"
        self.bottom_bar.set_playing(is_playing)
        self.player_screen.set_playing(is_playing)

    def _on_engine_position_changed(self, position_seconds: float, duration_seconds: float) -> None:
        self.bottom_bar.set_position(position_seconds, duration_seconds)
        self.player_screen.set_position(position_seconds, duration_seconds)

    def _on_engine_error(self, track_path: str, message: str) -> None:
        track = self.store.get_track(track_path) if track_path else None
        name = track.title if track else (track_path or "the current track")
        QMessageBox.warning(
            self, "Playback error",
            f'Could not play "{name}".\n\n{message}',
        )

    def _on_audio_devices_changed(self) -> None:
        devices = self.engine.list_output_devices()
        current = self.engine.current_output_device()
        is_default = self.engine.is_using_default_device()
        self.player_screen.set_available_devices(devices, current, is_default)
        self.bottom_bar.set_available_devices(devices, current, is_default)

    # ------------------------------------------------------------------
    # Player Screen open / close
    # ------------------------------------------------------------------

    def _open_player_screen(self) -> None:
        """Open the Player Screen overlay. Only opens if there is a current
        track, so tapping the empty bottom bar before any music is loaded
        doesn't show a blank screen.
        """
        if not self.engine.get_current_track():
            return
        self.setMinimumSize(_MIN_SIZE_PLAYER)
        self.player_screen.show_player()

    def _close_player_screen(self) -> None:
        self.player_screen.hide_player()
        self.setMinimumSize(_MIN_SIZE_NORMAL)

    def _toggle_main_queue(self) -> None:
        self._main_queue_active = not self._main_queue_active
        self.bottom_bar.set_queue_active(self._main_queue_active)
        target_w = int(self.width() * 0.35) if self._main_queue_active else 0
        if self._main_queue_active:
            self.main_queue_panel.refresh()
        else:
            self.main_queue_panel.setMinimumWidth(0)

        self._main_queue_anim.stop()
        self._main_queue_anim.setStartValue(self.main_queue_panel.maximumWidth())
        self._main_queue_anim.setEndValue(target_w)
        self._main_queue_anim.start()

    def _on_main_queue_anim_finished(self) -> None:
        if self._main_queue_active:
            w = max(self.main_queue_panel._min_width, min(self.main_queue_panel.width(), self.main_queue_panel._max_width))
            self.main_queue_panel.setMinimumWidth(w)
            self.main_queue_panel.setMaximumWidth(w)
        else:
            self.main_queue_panel.setMinimumWidth(0)
            self.main_queue_panel.setMaximumWidth(0)

    # ------------------------------------------------------------------
    # Navigation and Dynamic Pages
    # ------------------------------------------------------------------

    def _on_tab_close_requested(self, index: int) -> None:
        if index >= 5:  # permanent tabs are indices 0-4
            widget = self.tabs.widget(index)
            self.tabs.removeTab(index)
            if widget:
                if hasattr(widget, "disconnect_signals"):
                    try:
                        widget.disconnect_signals()
                    except Exception:
                        pass
                widget.deleteLater()

    def _on_bottom_bar_title_clicked(self) -> None:
        track = self.engine.get_current_track()
        if track:
            self._close_player_screen()
            self.open_album_page(track.album_key)

    def _on_bottom_bar_lyric_clicked(self) -> None:
        self._open_player_screen()
        self.player_screen.set_lyrics_active(True)

    def open_artist_page(self, name: str) -> None:
        self._close_player_screen()
        tab_title = f"{name} | Artist"

        for index in range(self.tabs.count()):
            if self.tabs.tabText(index) == tab_title:
                self.tabs.setCurrentIndex(index)
                return

        view = ArtistPageView(name, self.store, self.engine, self)
        view.track_double_clicked.connect(self._on_track_double_clicked)
        view.album_requested.connect(self.open_album_page)
        view.artist_requested.connect(self.open_artist_page)
        view.genre_requested.connect(self.open_genre_page)
        view.play_all_requested.connect(self._on_play_all_requested)

        # Refresh dynamically when tracks change
        self.store.tracks_added.connect(view.refresh_from_signal)
        self.store.track_removed.connect(view.refresh_from_signal)
        self.store.track_updated.connect(view.refresh_from_signal)

        idx = self.tabs.addTab(view, tab_title)
        self.tabs.setCurrentIndex(idx)

    def open_album_page(self, key: str) -> None:
        self._close_player_screen()
        all_tracks = self.store.all_tracks()
        album_tracks = [t for t in all_tracks if t.album_key == key]
        if not album_tracks:
            return
        
        album_title = album_tracks[0].album
        tab_title = f"{album_title} | Album"

        for index in range(self.tabs.count()):
            if self.tabs.tabText(index) == tab_title:
                self.tabs.setCurrentIndex(index)
                return

        view = AlbumPageView(key, self.store, self.engine, self)
        view.track_double_clicked.connect(self._on_track_double_clicked)
        view.artist_requested.connect(self.open_artist_page)
        view.genre_requested.connect(self.open_genre_page)
        view.play_all_requested.connect(self._on_play_all_requested)

        # Refresh dynamically when tracks change
        self.store.tracks_added.connect(view.refresh_from_signal)
        self.store.track_removed.connect(view.refresh_from_signal)
        self.store.track_updated.connect(view.refresh_from_signal)

        idx = self.tabs.addTab(view, tab_title)
        self.tabs.setCurrentIndex(idx)

    def open_genre_page(self, name: str) -> None:
        self._close_player_screen()
        tab_title = f"{name} | Genre"

        for index in range(self.tabs.count()):
            if self.tabs.tabText(index) == tab_title:
                self.tabs.setCurrentIndex(index)
                return

        view = GenrePageView(name, self.store, self.engine, self)
        view.track_double_clicked.connect(self._on_track_double_clicked)
        view.album_requested.connect(self.open_album_page)
        view.artist_requested.connect(self.open_artist_page)
        view.genre_requested.connect(self.open_genre_page)
        view.play_all_requested.connect(self._on_play_all_requested)

        # Refresh dynamically when tracks change
        self.store.tracks_added.connect(view.refresh_from_signal)
        self.store.track_removed.connect(view.refresh_from_signal)
        self.store.track_updated.connect(view.refresh_from_signal)

        idx = self.tabs.addTab(view, tab_title)
        self.tabs.setCurrentIndex(idx)

    def _stub_navigate(self, where: str) -> None:
        pass

    def _on_search_clicked(self) -> None:
        QMessageBox.information(
            self, "Coming in Step 9",
            "Global search lands in Step 9.",
        )

    # ------------------------------------------------------------------
    # Window resize: keep overlay geometry in sync
    # ------------------------------------------------------------------

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        if hasattr(self, "player_screen"):
            self.player_screen.parentResized(
                self.size()
            )
