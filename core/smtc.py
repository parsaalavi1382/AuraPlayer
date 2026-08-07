import sys
import os
import logging
from PyQt6.QtCore import QObject, pyqtSignal

class SMTCIntegration(QObject):
    """
    Windows System Media Transport Controls (SMTC) integration.
    Allows AuraPlayer to respond to global headset media keys (Play/Pause/Next/Prev)
    even when minimized, while playing nicely with Windows OS routing (e.g. Spotify).
    """
    play_requested = pyqtSignal()
    pause_requested = pyqtSignal()
    next_requested = pyqtSignal()
    prev_requested = pyqtSignal()
    stop_requested = pyqtSignal()

    def __init__(self, engine, parent=None):
        super().__init__(parent)
        self.engine = engine
        self._player = None
        self._smtc = None
        self._updater = None
        
        # Wire signals to engine on the main thread
        self.play_requested.connect(self.engine.play)
        self.pause_requested.connect(self.engine.pause)
        self.next_requested.connect(self.engine.next_track)
        self.prev_requested.connect(self.engine.prev_track)
        self.stop_requested.connect(self.engine.stop)

        if sys.platform != "win32":
            return

        try:
            from winrt.windows.media.playback import MediaPlayer
            from winrt.windows.media import SystemMediaTransportControlsButton
            from winrt.windows.media import MediaPlaybackType
            
            self._player = MediaPlayer()
            self._smtc = self._player.system_media_transport_controls
            
            self._smtc.is_play_enabled = True
            self._smtc.is_pause_enabled = True
            self._smtc.is_next_enabled = True
            self._smtc.is_previous_enabled = True
            self._smtc.is_stop_enabled = True
            
            self._smtc.add_button_pressed(self._on_button_pressed)
            self._ButtonEnum = SystemMediaTransportControlsButton
            
            self._updater = self._smtc.display_updater
            self._updater.type = MediaPlaybackType.MUSIC
            self._updater.update()
            
            logging.info("SMTC initialized successfully.")
        except Exception as e:
            logging.warning(f"Failed to initialize SMTC: {e}")

    def _on_button_pressed(self, sender, args):
        # This fires on a background COM thread.
        # Emit signals to safely transition to the main UI thread.
        try:
            btn = args.button
            if btn == self._ButtonEnum.PLAY:
                self.play_requested.emit()
            elif btn == self._ButtonEnum.PAUSE:
                self.pause_requested.emit()
            elif btn == self._ButtonEnum.NEXT:
                self.next_requested.emit()
            elif btn == self._ButtonEnum.PREVIOUS:
                self.prev_requested.emit()
            elif btn == self._ButtonEnum.STOP:
                self.stop_requested.emit()
        except Exception as e:
            logging.warning(f"Error handling SMTC button press: {e}")

    def update_metadata(self, title: str, artist: str, album: str = "", track_path: str = ""):
        if not self._updater:
            return
        from PyQt6.QtCore import QTimer
        QTimer.singleShot(250, lambda: self._do_update_metadata(title, artist, album, track_path))

    def _do_update_metadata(self, title: str, artist: str, album: str, track_path: str):
        if sys.platform != "win32" or not self._updater:
            return

        try:
            props = self._updater.music_properties
            props.title = title
            props.artist = artist
            props.album_artist = artist
            props.album_title = album
            self._updater.update()
            
            import threading
            threading.Thread(target=self._update_thumbnail_bg, args=(track_path, title), daemon=True).start()
        except Exception as e:
            logging.warning(f"SMTC metadata update failed: {e}")

    def _update_thumbnail_bg(self, track_path: str, title: str):
        if sys.platform != "win32" or not self._updater:
            return
        try:
            from core.metadata_reader import _extract_raw_art_bytes
            from utils.paths import get_writable_data_path
            import asyncio
            
            raw_bytes = _extract_raw_art_bytes(track_path) if track_path else None
            
            if raw_bytes:
                target_image_path = get_writable_data_path("smtc_cover.jpg")
                try:
                    with open(target_image_path, "wb") as f:
                        f.write(raw_bytes)
                except Exception as e:
                    logging.warning(f"Failed writing SMTC cover file: {e}")
            else:
                if getattr(sys, 'frozen', False):
                    base_dir = sys._MEIPASS
                else:
                    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
                target_image_path = os.path.join(base_dir, "assets", "logo.png")
            
            abs_path = os.path.abspath(target_image_path)
            
            if os.path.exists(target_image_path):
                from winrt.windows.storage import StorageFile
                from winrt.windows.storage.streams import RandomAccessStreamReference
                
                async def _get_thumb():
                    try:
                        file = await StorageFile.get_file_from_path_async(abs_path)
                        return RandomAccessStreamReference.create_from_file(file)
                    except Exception as e:
                        logging.warning(f"StorageFile failed: {e}")
                        return None
                        
                thumb = asyncio.run(_get_thumb())
                if thumb:
                    self._updater.thumbnail = thumb
                else:
                    self._updater.thumbnail = None
            else:
                self._updater.thumbnail = None
                
            self._updater.update()
            logging.info(f"SMTC background cover updated for: {title}")
        except Exception as e:
            logging.warning(f"SMTC background thumbnail update failed: {e}")
    
    def update_playback_status(self, is_playing: bool, is_stopped: bool = False):
        if not self._smtc:
            return
        try:
            from winrt.windows.media import MediaPlaybackStatus
            if is_stopped:
                self._smtc.playback_status = MediaPlaybackStatus.STOPPED
            elif is_playing:
                self._smtc.playback_status = MediaPlaybackStatus.PLAYING
            else:
                self._smtc.playback_status = MediaPlaybackStatus.PAUSED
        except Exception as e:
            logging.warning(f"SMTC status update failed: {e}")
