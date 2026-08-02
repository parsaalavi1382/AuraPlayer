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

import sys

from PyQt6.QtCore import QSize, Qt, QPropertyAnimation, QParallelAnimationGroup, QEasingCurve, QRect, QPoint, QEvent, QTimer
from PyQt6.QtGui import QShortcut, QKeySequence
from PyQt6.QtMultimedia import QMediaDevices
from PyQt6.QtWidgets import QTableView
from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QTabWidget, QTabBar,
    QMessageBox, QApplication, QStackedWidget, QFrame, QPushButton, QLabel,
    QGraphicsOpacityEffect, QTableView,
)

from core.library_store import LibraryStore
from core.playback_engine import PlaybackEngine
from core.metadata_reader import get_album_art, get_track_album_art
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
from ui.views.search_view import SearchOverlay

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
        self.top_bar.search_input.textChanged.connect(self._on_search_text_changed)
        self.top_bar.search_input.escape_pressed.connect(self._on_search_escape)
        self.top_bar.back_clicked.connect(self._on_back_clicked)
        self.top_bar.forward_clicked.connect(self._on_forward_clicked)
        self.top_bar.home_clicked.connect(self._on_home_clicked)
        layout.addWidget(self.top_bar)

        # --- Content Area (Tabs + Side Queue Panel) ---
        content_layout = QHBoxLayout()
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(0)

        # --- Main Tabs ---
        self.tabs = QTabWidget()
        self.tabs.setTabsClosable(False)
        self.tabs.setIconSize(QSize(18, 18))
        
        self._tab_indicator = QFrame(self.tabs.tabBar())
        self._tab_indicator.setObjectName("tabIndicator")
        self._tab_indicator.setFixedHeight(2)
        self._tab_indicator.hide()
        
        from PyQt6.QtCore import QPropertyAnimation, QEasingCurve, QRect
        self._tab_indicator_anim = QPropertyAnimation(self._tab_indicator, b"geometry")
        self._tab_indicator_anim.setDuration(250)
        self._tab_indicator_anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        
        self.tabs.currentChanged.connect(self._on_tab_changed)
        self.tabs.tabBar().setMouseTracking(True)
        self.tabs.tabBar().installEventFilter(self)

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

        self.nav_stack = QStackedWidget()
        self.nav_stack.addWidget(self.tabs)
        self.page_history = []
        self.forward_history = []
        content_layout.addWidget(self.nav_stack, stretch=1)

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

        # --- Search Overlay & Shortcuts ---
        self.search_overlay = SearchOverlay(self.store, self.engine, self)
        self.search_overlay.track_requested.connect(self._on_search_track_requested)
        self.search_overlay.artist_requested.connect(self.open_artist_page)
        self.search_overlay.album_requested.connect(self.open_album_page)
        self.search_overlay.genre_requested.connect(self.open_genre_page)
        self.search_overlay.playlist_requested.connect(self.open_playlist_page)
        self.search_overlay.closed.connect(self._on_search_closed)

        self._search_shortcut = QShortcut(QKeySequence("Ctrl+F"), self)
        self._search_shortcut.activated.connect(self._on_search_clicked)

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
        self.playlists_view.playlist_selected.connect(self.open_playlist_page)

        # --- Favorite wiring ---
        self.bottom_bar.favorite_toggled.connect(self._on_favorite_toggled)
        self.player_screen.favorite_toggled.connect(self._on_favorite_toggled)
        self.store.playlists_changed.connect(self._on_playlists_changed)

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

        # Install application-wide event filter for global keyboard shortcuts & click-outside handling
        app = QApplication.instance()
        if app:
            app.installEventFilter(self)

        # Ensure search input is not focused by default on startup
        QTimer.singleShot(0, lambda: self.setFocus())

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
        if hasattr(self, "search_overlay"):
            self.search_overlay.apply_theme(theme)

        # Tracks table danger color
        self.tracks_view.model.set_danger_color(theme["danger"])

        # Update tab icons and indicator color
        self._update_tab_icons()
        self._update_tab_indicator(animate=False)

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

    def _on_tab_changed(self, index: int) -> None:
        self._update_tab_indicator(index, animate=True)
        self._update_tab_icons()
        widget = self.tabs.widget(index)
        if widget:
            self._animate_nav_transition(widget, mode="fade")

    def _animate_nav_transition(self, target_widget: QWidget, mode: str = "fade") -> None:
        if hasattr(self, "top_bar") and hasattr(self.top_bar, "search_input"):
            self.top_bar.search_input.clearFocus()
        if hasattr(self, "search_overlay"):
            self.search_overlay.hide_search()
        self.setFocus()

        if not target_widget:
            return

        if hasattr(self, "_nav_anim_group") and self._nav_anim_group is not None:
            self._nav_anim_group.stop()

        if hasattr(self, "_nav_anim_target_widget") and self._nav_anim_target_widget:
            try:
                self._nav_anim_target_widget.setGraphicsEffect(None)
                self._nav_anim_target_widget.move(0, 0)
            except Exception:
                pass

        self._nav_anim_target_widget = target_widget

        from PyQt6.QtWidgets import QGraphicsOpacityEffect
        from PyQt6.QtCore import QPropertyAnimation, QParallelAnimationGroup, QEasingCurve, QPoint

        effect = QGraphicsOpacityEffect(target_widget)
        target_widget.setGraphicsEffect(effect)

        anim_group = QParallelAnimationGroup(self)

        fade_anim = QPropertyAnimation(effect, b"opacity", anim_group)
        fade_anim.setStartValue(0.0)
        fade_anim.setEndValue(1.0)

        if mode == "fade":
            fade_anim.setDuration(150)
            anim_group.addAnimation(fade_anim)
        else:
            fade_anim.setDuration(220)
            anim_group.addAnimation(fade_anim)

            offset_x = 25 if mode == "right" else -25
            pos_anim = QPropertyAnimation(target_widget, b"pos", anim_group)
            pos_anim.setDuration(220)
            pos_anim.setEasingCurve(QEasingCurve.Type.OutCubic)
            pos_anim.setStartValue(QPoint(offset_x, 0))
            pos_anim.setEndValue(QPoint(0, 0))
            anim_group.addAnimation(pos_anim)

        def _on_finished():
            if hasattr(self, "_nav_anim_target_widget") and self._nav_anim_target_widget:
                try:
                    self._nav_anim_target_widget.setGraphicsEffect(None)
                    self._nav_anim_target_widget.move(0, 0)
                except Exception:
                    pass

        anim_group.finished.connect(_on_finished)
        self._nav_anim_group = anim_group
        anim_group.start()

    def _update_tab_indicator(self, index: int = -1, animate: bool = True) -> None:
        from PyQt6.QtCore import QRect
        if index < 0:
            index = self.tabs.currentIndex()
        if index < 0 or not hasattr(self, "_tab_indicator"):
            return
            
        bar = self.tabs.tabBar()
        rect = bar.tabRect(index)
        target_rect = QRect(rect.x(), rect.height() - 2, rect.width(), 2)
        
        if animate and self._tab_indicator.isVisible():
            self._tab_indicator_anim.stop()
            self._tab_indicator_anim.setStartValue(self._tab_indicator.geometry())
            self._tab_indicator_anim.setEndValue(target_rect)
            self._tab_indicator_anim.start()
        else:
            self._tab_indicator_anim.stop()
            self._tab_indicator.setGeometry(target_rect)
            self._tab_indicator.show()

    def _update_tab_icons(self, hovered_idx: int = -1) -> None:
        from ui.theme import THEMES, DEFAULT_THEME
        
        theme_key = self.store.cache.settings.theme
        theme = THEMES.get(theme_key, THEMES[DEFAULT_THEME])
        accent = theme.get("accent", "#6C5CE7")
        primary = theme.get("text_primary", "#EDEFF2")
        neutral = theme.get("text_secondary", "#9AA0AC")
        
        if hasattr(self, "_tab_indicator"):
            self._tab_indicator.setStyleSheet(f"background-color: {accent}; border: none;")

        try:
            import qtawesome as qta
        except ImportError:
            return
            
        from ui.svg_icon import svg_icon
        
        icons = [
            ("fa5s.music",),
            ("fa5s.microphone-alt",),
            ("fa5s.tag",),
            ("disc", "asset"),
            ("fa5s.list",)
        ]
        
        current_idx = self.tabs.currentIndex()
        for i, ic in enumerate(icons):
            if i == current_idx:
                color = accent
            elif i == hovered_idx:
                color = primary
            else:
                color = neutral
            if len(ic) > 1 and ic[1] == "asset":
                icon = svg_icon(ic[0], color, 18)
            else:
                icon = qta.icon(ic[0], color=color)
            self.tabs.setTabIcon(i, icon)

    def eventFilter(self, watched, event) -> bool:
        from PyQt6.QtCore import QEvent, Qt
        from PyQt6.QtWidgets import QLineEdit, QAbstractSpinBox
        
        if hasattr(self, "tabs") and watched == self.tabs.tabBar():
            if event.type() in (QEvent.Type.Resize, QEvent.Type.Show):
                self._update_tab_indicator(animate=False)
            elif event.type() in (QEvent.Type.MouseMove, QEvent.Type.HoverMove):
                idx = self.tabs.tabBar().tabAt(event.pos())
                self._update_tab_icons(hovered_idx=idx)
            elif event.type() in (QEvent.Type.Leave, QEvent.Type.HoverLeave):
                self._update_tab_icons(hovered_idx=-1)
                
        # --- Global Keyboard Shortcuts ---
        if event.type() == QEvent.Type.KeyPress:
            key = event.key()
            focus_widget = QApplication.focusWidget()

            # Handle Search Overlay navigation & execution when active
            if hasattr(self, "search_overlay") and self.search_overlay.isVisible():
                if key == Qt.Key.Key_Up:
                    self.search_overlay.navigate_up()
                    return True
                elif key == Qt.Key.Key_Down:
                    self.search_overlay.navigate_down()
                    return True
                elif key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
                    self.search_overlay.execute_selected_row()
                    return True
            
            # Don't intercept other keys if user is actively typing in a text field or spinbox
            if isinstance(focus_widget, (QLineEdit, QAbstractSpinBox)):
                return super().eventFilter(watched, event)

            if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
                if hasattr(self, "search_overlay") and self.search_overlay.isVisible():
                    self.search_overlay.execute_selected_row()
                    return True
                focus_w = QApplication.focusWidget()
                if focus_w and hasattr(focus_w, "clicked") and hasattr(focus_w, "album_key"):
                    focus_w.clicked.emit(focus_w.album_key)
                    return True
                
                table = None
                if isinstance(focus_w, QTableView):
                    table = focus_w
                else:
                    active_view = self._get_active_view()
                    if active_view:
                        if hasattr(active_view, "_get_active_table"):
                            table = active_view._get_active_table()
                        elif hasattr(active_view, "table") and active_view.table:
                            table = active_view.table
                        elif hasattr(active_view, "_tables") and active_view._tables:
                            for t in active_view._tables:
                                if t.hasFocus() or (t.currentIndex().isValid() and t.currentIndex().row() >= 0):
                                    table = t
                                    break
                            if not table and active_view._tables:
                                table = active_view._tables[0]

                if table:
                    curr_idx = table.currentIndex()
                    if not curr_idx.isValid() or curr_idx.row() < 0:
                        model = table.model()
                        if model and model.rowCount() > 0:
                            curr_idx = model.index(0, 0)

                    if curr_idx.isValid() and curr_idx.row() >= 0:
                        table.doubleClicked.emit(curr_idx)
                        table.setFocus()
                        table.setCurrentIndex(curr_idx)
                        table.selectRow(curr_idx.row())
                        active_view = self._get_active_view()
                        if active_view:
                            if hasattr(active_view, "_ensure_row_visible"):
                                try:
                                    import inspect
                                    sig = inspect.signature(active_view._ensure_row_visible)
                                    if len(sig.parameters) == 2:
                                        active_view._ensure_row_visible(table, curr_idx.row())
                                    else:
                                        active_view._ensure_row_visible(curr_idx.row())
                                except Exception:
                                    pass
                        return True
                return False
            elif key == Qt.Key.Key_Space:
                self.engine.toggle_play_pause()
                return True
            elif key in (Qt.Key.Key_MediaPlay, Qt.Key.Key_MediaTogglePlayPause):
                if sys.platform != "win32":
                    self.engine.toggle_play_pause()
                return True
            elif key == Qt.Key.Key_MediaNext:
                if sys.platform != "win32":
                    self.engine.next_track()
                return True
            elif key == Qt.Key.Key_MediaPrevious:
                if sys.platform != "win32":
                    self.engine.prev_track()
                return True
            elif key == Qt.Key.Key_Up:
                active_view = self._get_active_view()
                if active_view:
                    if hasattr(active_view, "navigate_up"):
                        active_view.navigate_up()
                        return True
                    elif hasattr(active_view, "table"):
                        table = active_view.table
                        if table:
                            table.setFocus()
                            model = table.model()
                            rowCount = model.rowCount() if model else 0
                            if rowCount > 0:
                                curr_row = table.currentIndex().row()
                                if curr_row <= 0:
                                    table.setCurrentIndex(model.index(0, 0))
                                else:
                                    table.setCurrentIndex(model.index(curr_row - 1, 0))
                            return True
                return False

            elif key == Qt.Key.Key_Down:
                active_view = self._get_active_view()
                if active_view:
                    if hasattr(active_view, "navigate_down"):
                        active_view.navigate_down()
                        return True
                    elif hasattr(active_view, "table"):
                        table = active_view.table
                        if table:
                            table.setFocus()
                            model = table.model()
                            rowCount = model.rowCount() if model else 0
                            if rowCount > 0:
                                curr_row = table.currentIndex().row()
                                if curr_row < 0:
                                    table.setCurrentIndex(model.index(0, 0))
                                elif curr_row + 1 < rowCount:
                                    table.setCurrentIndex(model.index(curr_row + 1, 0))
                                else:
                                    table.setCurrentIndex(model.index(rowCount - 1, 0))
                            return True
                return False
            elif key == Qt.Key.Key_Right:
                if not event.isAutoRepeat():
                    self.engine.start_seek_forward()
                return True
            elif key == Qt.Key.Key_Left:
                if not event.isAutoRepeat():
                    self.engine.start_seek_back()
                return True

        elif event.type() == QEvent.Type.KeyRelease:
            key = event.key()
            focus_widget = QApplication.focusWidget()
            if isinstance(focus_widget, (QLineEdit, QAbstractSpinBox)):
                return super().eventFilter(watched, event)

            if key == Qt.Key.Key_Right:
                if not event.isAutoRepeat():
                    self.engine.stop_seek()
                return True
            elif key == Qt.Key.Key_Left:
                if not event.isAutoRepeat():
                    self.engine.stop_seek()
                return True

        # --- Mouse Press: Deactivate search when clicking outside ---
        elif event.type() == QEvent.Type.MouseButtonPress:
            if hasattr(self, "top_bar") and hasattr(self.top_bar, "search_input"):
                search_inp = self.top_bar.search_input
                overlay_visible = hasattr(self, "search_overlay") and self.search_overlay.isVisible()
                if search_inp.hasFocus() or overlay_visible:
                    click_pos = event.globalPosition().toPoint() if hasattr(event, "globalPosition") else event.globalPos()
                    
                    in_search_bar = False
                    if hasattr(self.top_bar, "search_bar_frame"):
                        sb_rect = QRect(self.top_bar.search_bar_frame.mapToGlobal(QPoint(0, 0)), self.top_bar.search_bar_frame.size())
                        if sb_rect.contains(click_pos):
                            in_search_bar = True

                    in_search_modal = False
                    if overlay_visible and hasattr(self.search_overlay, "modal_box"):
                        mb_rect = QRect(self.search_overlay.modal_box.mapToGlobal(QPoint(0, 0)), self.search_overlay.modal_box.size())
                        if mb_rect.contains(click_pos):
                            in_search_modal = True

                    if not in_search_bar and not in_search_modal:
                        search_inp.clearFocus()
                        if overlay_visible:
                            self.search_overlay.hide_search()

        return super().eventFilter(watched, event)

    # ------------------------------------------------------------------
    # Playback management
    # ------------------------------------------------------------------

    def _get_active_view(self) -> QWidget | None:
        if hasattr(self, "nav_stack") and self.nav_stack.currentIndex() != 0:
            container = self.nav_stack.currentWidget()
            if container and hasattr(container, "view"):
                return container.view
            return container
        if hasattr(self, "tabs"):
            return self.tabs.currentWidget()
        return None

    def _on_track_double_clicked(self, track_path: str) -> None:
        active_view = self._get_active_view()
        all_paths = []
        
        # If the active view has a standard tracks model (Tracks, Artist, Genre, Playlist, etc.)
        if active_view and hasattr(active_view, "model") and active_view.model:
            model = active_view.model
            all_paths = [
                model.track_at(r).path
                for r in range(model.rowCount())
                if model.track_at(r) and not model.track_at(r).file_missing
            ]
        # If the active view is AlbumPageView which has self.album_tracks
        elif active_view and hasattr(active_view, "album_tracks") and active_view.album_tracks:
            all_paths = [
                t.path
                for t in active_view.album_tracks
                if not t.file_missing
            ]
        # If the active view is PlaylistPageView which has self.playlist_tracks
        elif active_view and hasattr(active_view, "playlist_tracks") and active_view.playlist_tracks:
            all_paths = [
                t.path
                for t in active_view.playlist_tracks
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

        is_fav = self.store.is_track_favorited(track_path) if track_path else False
        self.bottom_bar.set_favorited(is_fav)
        self.player_screen.set_favorited(is_fav)

        if track:
            self._load_and_push_art(track_path)
        else:
            self.player_screen.set_track("No track", "", None)

    def _load_and_push_art(self, track_path: str) -> None:
        """Load album art for track_path (may be None for untagged files)
        and push it to both the bottom bar thumbnail and Player Screen.
        """
        track = self.store.get_track(track_path) if track_path else None
        art = get_track_album_art(track, self.store) if track else get_album_art(track_path)
        self.bottom_bar.set_art(art)
        self.player_screen.set_track(
            track.title if track else "",
            ", ".join(track.artists) if track else "",
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

    def _cleanup_widgets(self, widgets: list) -> None:
        for w in widgets:
            if w and w != self.tabs:
                self.nav_stack.removeWidget(w)
                if hasattr(w, "view") and hasattr(w.view, "disconnect_signals"):
                    try:
                        w.view.disconnect_signals()
                    except Exception:
                        pass
                w.deleteLater()

    def _update_nav_buttons(self) -> None:
        is_main_menu = (self.nav_stack.currentIndex() == 0)
        can_back = bool(self.page_history) or not is_main_menu
        can_forward = bool(self.forward_history)
        can_home = can_back or can_forward
        visible = not is_main_menu
        self.top_bar.update_nav_state(can_back, can_forward, can_home, visible=visible)

    def _show_detail_page(self, view, title: str) -> None:
        current = self.nav_stack.currentWidget()
        if getattr(current, "page_title", "") == title:
            return

        if self.forward_history:
            self._cleanup_widgets(self.forward_history)
            self.forward_history.clear()

        mode = "right"

        if self.nav_stack.currentIndex() != 0 and current is not None:
            self.page_history.append(current)
        elif self.nav_stack.currentIndex() == 0:
            self.page_history.append(self.tabs)

        container = QWidget()
        container.page_title = title
        container.view = view
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(view, stretch=1)

        if hasattr(self, "search_overlay"):
            self.search_overlay.hide_search()

        self.nav_stack.addWidget(container)
        self.nav_stack.setCurrentWidget(container)
        self._update_nav_buttons()
        self._animate_nav_transition(container, mode=mode)

    def _on_back_clicked(self) -> None:
        current = self.nav_stack.currentWidget()
        target_widget = None
        if self.page_history:
            prev_widget = self.page_history.pop()
            if current:
                self.forward_history.append(current)
            self.nav_stack.setCurrentWidget(prev_widget)
            target_widget = prev_widget
        elif self.nav_stack.currentIndex() != 0:
            if current:
                self.forward_history.append(current)
            self.nav_stack.setCurrentIndex(0)
            target_widget = self.tabs
        self._update_nav_buttons()

        if target_widget:
            self._animate_nav_transition(target_widget, mode="left")

    def _on_forward_clicked(self) -> None:
        if not self.forward_history:
            return
        next_widget = self.forward_history.pop()
        current = self.nav_stack.currentWidget()
        if current is not None:
            self.page_history.append(current)
        self.nav_stack.setCurrentWidget(next_widget)
        self._update_nav_buttons()
        self._animate_nav_transition(next_widget, mode="right")

    def _on_home_clicked(self) -> None:
        all_detail_widgets = set(self.page_history + self.forward_history)
        current = self.nav_stack.currentWidget()
        if current and current != self.tabs:
            all_detail_widgets.add(current)
            
        self.page_history.clear()
        self.forward_history.clear()
        self.nav_stack.setCurrentIndex(0)
        
        self._cleanup_widgets(list(all_detail_widgets))
        self._update_nav_buttons()
        self._animate_nav_transition(self.tabs, mode="left")

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

        view = ArtistPageView(name, self.store, self.engine, self)
        view.track_double_clicked.connect(self._on_track_double_clicked)
        view.album_requested.connect(self.open_album_page)
        view.artist_requested.connect(self.open_artist_page)
        view.genre_requested.connect(self.open_genre_page)
        view.play_all_requested.connect(self._on_play_all_requested)

        self.store.tracks_added.connect(view.refresh_from_signal)
        self.store.track_removed.connect(view.refresh_from_signal)
        self.store.track_updated.connect(view.refresh_from_signal)

        self._show_detail_page(view, tab_title)

    def open_album_page(self, key: str) -> None:
        self._close_player_screen()
        all_tracks = self.store.all_tracks()
        album_tracks = [t for t in all_tracks if t.album_key == key]
        if not album_tracks:
            return
        
        album_title = album_tracks[0].album
        tab_title = f"{album_title} | Album"

        view = AlbumPageView(key, self.store, self.engine, self)
        view.track_double_clicked.connect(self._on_track_double_clicked)
        view.artist_requested.connect(self.open_artist_page)
        view.genre_requested.connect(self.open_genre_page)
        view.play_all_requested.connect(self._on_play_all_requested)

        self.store.tracks_added.connect(view.refresh_from_signal)
        self.store.track_removed.connect(view.refresh_from_signal)
        self.store.track_updated.connect(view.refresh_from_signal)

        self._show_detail_page(view, tab_title)

    def open_genre_page(self, name: str) -> None:
        self._close_player_screen()
        tab_title = f"{name} | Genre"

        view = GenrePageView(name, self.store, self.engine, self)
        view.track_double_clicked.connect(self._on_track_double_clicked)
        view.album_requested.connect(self.open_album_page)
        view.artist_requested.connect(self.open_artist_page)
        view.genre_requested.connect(self.open_genre_page)
        view.play_all_requested.connect(self._on_play_all_requested)

        self.store.tracks_added.connect(view.refresh_from_signal)
        self.store.track_removed.connect(view.refresh_from_signal)
        self.store.track_updated.connect(view.refresh_from_signal)

        self._show_detail_page(view, tab_title)

    def _stub_navigate(self, where: str) -> None:
        pass

    def _on_search_clicked(self) -> None:
        self.top_bar.search_input.setFocus()
        self.top_bar.search_input.selectAll()

    def _on_search_text_changed(self, text: str) -> None:
        if hasattr(self, "search_overlay"):
            self.search_overlay.set_query(text)

    def _on_search_escape(self) -> None:
        if hasattr(self, "search_overlay"):
            self.search_overlay.hide_search()
            self.top_bar.search_input.clear()
            self.setFocus()

    def _on_search_closed(self) -> None:
        self.top_bar.search_input.clear()

    def _on_search_track_requested(self, track_path: str) -> None:
        if hasattr(self, "search_overlay"):
            self.search_overlay.hide_search()
        track = self.store.get_track(track_path)
        if track:
            self.open_album_page(track.album_key)

    # ------------------------------------------------------------------
    # Window resize: keep overlay geometry in sync
    # ------------------------------------------------------------------

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        if hasattr(self, "player_screen"):
            self.player_screen.parentResized(
                self.size()
            )
        if hasattr(self, "search_overlay") and self.search_overlay.isVisible():
            self.search_overlay.parentResized(self.size())

    def _on_favorite_toggled(self, track_path: str, favorited: bool) -> None:
        self.store.set_track_favorited(track_path, favorited)
        self.bottom_bar.set_favorited(favorited, animated=True)
        self.player_screen.set_favorited(favorited, animated=True)

    def _on_playlists_changed(self, playlist_id: str) -> None:
        if playlist_id == "smart_favorites":
            current = self.engine.get_current_track()
            if current:
                is_fav = self.store.is_track_favorited(current.path)
                self.bottom_bar.set_favorited(is_fav, animated=True)
                self.player_screen.set_favorited(is_fav, animated=True)

    def open_playlist_page(self, playlist_id: str) -> None:
        self._close_player_screen()
        
        if playlist_id.startswith("smart_"):
            pl_name = {
                "smart_recently_added": "Recently Added",
                "smart_favorites": "Favorites",
                "smart_recently_played": "Recently Played",
                "smart_most_played": "Most Played",
            }.get(playlist_id, "Smart Playlist")
        else:
            pl_obj = self.store.get_playlist(playlist_id)
            if not pl_obj:
                return
            pl_name = pl_obj.name
            
        tab_title = f"{pl_name} | Playlist"
                
        from ui.views.playlist_page_view import PlaylistPageView
        view = PlaylistPageView(playlist_id, self.store, self.engine, self)
        view.track_double_clicked.connect(self._on_track_double_clicked)
        view.artist_requested.connect(self.open_artist_page)
        view.album_requested.connect(self.open_album_page)
        view.genre_requested.connect(self.open_genre_page)
        view.play_all_requested.connect(self._on_play_all_requested)
        view.playlist_deleted.connect(self._on_playlist_deleted_signal)
        
        self._show_detail_page(view, tab_title)

    def _on_playlist_deleted_signal(self, playlist_id: str) -> None:
        from ui.views.playlist_page_view import PlaylistPageView
        to_remove_page = [w for w in self.page_history if hasattr(w, "view") and isinstance(w.view, PlaylistPageView) and w.view.playlist_id == playlist_id]
        to_remove_fwd = [w for w in self.forward_history if hasattr(w, "view") and isinstance(w.view, PlaylistPageView) and w.view.playlist_id == playlist_id]
        self._cleanup_widgets(to_remove_page + to_remove_fwd)
        self.page_history = [w for w in self.page_history if w not in to_remove_page]
        self.forward_history = [w for w in self.forward_history if w not in to_remove_fwd]

        current = self.nav_stack.currentWidget()
        if hasattr(current, "view") and isinstance(current.view, PlaylistPageView) and current.view.playlist_id == playlist_id:
            self._on_back_clicked()
        else:
            self._update_nav_buttons()
