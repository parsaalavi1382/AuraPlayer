from __future__ import annotations

import random
import os
import threading
import array
from typing import Optional

from PyQt6.QtCore import QObject, pyqtSignal, QTimer
import miniaudio

try:
    import audioop
    HAS_AUDIOOP = True
except ImportError:
    HAS_AUDIOOP = False

from utils.gapless_metadata import get_audio_specs

POSITION_SAVE_INTERVAL_MS = 1200
SMART_PREV_THRESHOLD_SECONDS = 3.0


class AudioStreamWrapper:
    """
    A custom wrapper to bridge pyminiaudio's generator-based streaming
    with an object-oriented File API required for our Gapless Engine.
    Optimized for low-latency memory allocation.
    """
    def __init__(self, filepath: str, volume: float = 1.0):
        self.filepath = filepath
        self.volume = volume
        
        # Force a consistent sample rate and channel count for seamless gapless playback
        self.sample_rate = 44100
        self.nchannels = 2
        
        info = miniaudio.get_file_info(filepath)
        self.duration = info.duration
        self.current_frame = 0
        self._buffer = b""
        self._generator = self._create_generator(0)

    def _create_generator(self, seek_frame: int):
        return miniaudio.stream_file(
            self.filepath,
            sample_rate=self.sample_rate,
            nchannels=self.nchannels,
            output_format=miniaudio.SampleFormat.SIGNED16,
            seek_frame=seek_frame
        )

    def read_frames(self, num_frames: int) -> bytes:
        bytes_needed = num_frames * 4 # 16-bit stereo = 4 bytes per frame
        
        # Optimized memory buffer building (eliminates UI lag caused by string concatenation)
        chunks = [self._buffer]
        current_len = len(self._buffer)
        
        while current_len < bytes_needed:
            try:
                chunk = next(self._generator)
                c_bytes = chunk.tobytes()
                chunks.append(c_bytes)
                current_len += len(c_bytes)
            except StopIteration:
                break
                
        full_buffer = b"".join(chunks)
        chunk_bytes = full_buffer[:bytes_needed]
        self._buffer = full_buffer[bytes_needed:]
        
        self.current_frame += len(chunk_bytes) // 4
        
        # Apply software volume scaling
        if self.volume != 1.0 and chunk_bytes:
            if HAS_AUDIOOP:
                chunk_bytes = audioop.mul(chunk_bytes, 2, self.volume)
            else:
                samples = array.array('h', chunk_bytes)
                vol = self.volume
                for i in range(len(samples)):
                    samples[i] = int(samples[i] * vol)
                chunk_bytes = samples.tobytes()
                
        return chunk_bytes

    def seek_to_pcm_frame(self, target_frame: int):
        self.current_frame = max(0, target_frame)
        self._buffer = b""
        self._generator = self._create_generator(self.current_frame)


class PlaybackEngine(QObject):
    # ============================================================
    # Signals (UI Subscribers)
    # ============================================================
    track_changed = pyqtSignal(str)            
    playback_state_changed = pyqtSignal(str)    
    position_changed = pyqtSignal(float, float)  
    queue_changed = pyqtSignal()                 
    repeat_mode_changed = pyqtSignal(str)
    shuffle_changed = pyqtSignal(bool)
    volume_changed = pyqtSignal(float)            
    output_device_changed = pyqtSignal(str)        
    error_occurred = pyqtSignal(str, str)           
    audio_quality_changed = pyqtSignal(dict) 

    def __init__(self, store, parent=None):
        super().__init__(parent)
        self.store = store
        state = self.store.cache.player_state

        self._device: Optional[miniaudio.PlaybackDevice] = None
        self._current_file: Optional[AudioStreamWrapper] = None
        self._next_file: Optional[AudioStreamWrapper] = None
        self._lock = threading.Lock() 

        self._volume = state.volume  
        self._macro_state: str = "stop_initial"

        self._is_seeking: bool = False
        self._seek_direction: int = 0
        self._was_playing_before_seek: bool = False
        self._seek_timer = QTimer(self)
        self._seek_timer.timeout.connect(self._on_seek_tick)

        self._shuffle: bool = state.shuffle
        self._queue: list[str] = list(state.queue)
        self._queue_index: int = state.queue_index
        self._repeat_mode: str = state.repeat_mode
        self._original_queue: list[str] = list(self._queue)

        # UI Progress Sync Timer (Only updates UI, no longer controls state)
        self._progress_timer = QTimer(self)
        self._progress_timer.setInterval(100) 
        self._progress_timer.timeout.connect(self._on_progress_tick)

        self._save_timer = QTimer(self)
        self._save_timer.setInterval(POSITION_SAVE_INTERVAL_MS)
        self._save_timer.timeout.connect(self._persist_position)

        self._initialize_audio_device()
        self._restore_initial_state(state)

    # ============================================================
    # Background Tasks (Lag Prevention)
    # ============================================================
    def _emit_specs_async(self, filepath: str) -> None:
        """Fetches metadata on a background thread to prevent GUI freezing."""
        def task():
            specs = get_audio_specs(filepath)
            # PyQt signals are thread-safe and will sync back to the main thread smoothly
            self.audio_quality_changed.emit(specs)
        threading.Thread(target=task, daemon=True).start()

    # ============================================================
    # Low-Level Audio Hardware Interface
    # ============================================================
    def _initialize_audio_device(self) -> None:
        try:
            self._device = miniaudio.PlaybackDevice()
            generator = self._audio_stream_callback()
            next(generator) # Prime the generator
            self._device.start(generator)
        except Exception as e:
            self.error_occurred.emit("Engine Init", f"Failed to initialize audio device: {str(e)}")

    def _audio_stream_callback(self):
        required_frames = yield b"" 
        while True:
            with self._lock:
                if self._macro_state != "playing" or self._current_file is None:
                    required_frames = yield b"\x00" * (required_frames * 4) 
                    continue

                data = self._current_file.read_frames(required_frames)
                
                # Zero-Latency Gapless Handoff
                if len(data) == 0:
                    if self._next_file is not None:
                        # Seamlessly swap to the next preloaded track
                        self._current_file = self._next_file
                        self._next_file = None
                        
                        QTimer.singleShot(0, self._on_track_seamless_advanced)
                        data = self._current_file.read_frames(required_frames)
                    else:
                        # End of playlist (No next file available)
                        QTimer.singleShot(0, self._on_playlist_finished)
                        required_frames = yield b"\x00" * (required_frames * 4)
                        continue
                        
                if len(data) == 0:
                    required_frames = yield b"\x00" * (required_frames * 4)
                else:
                    required_frames = yield data

    def _on_track_seamless_advanced(self) -> None:
        """Called automatically by the hardware thread when a track seamlessly finishes."""
        next_index = self._compute_next_index(self._queue_index)
        if next_index is not None:
            self._queue_index = next_index
            self._persist_queue()
            path = self._queue[next_index]
            
            self._emit_specs_async(path)
            self.track_changed.emit(path)
            
            # Start preloading the next track in the background immediately
            self._preload_next_track()

    def _on_playlist_finished(self) -> None:
        """Called by the hardware thread when the final track in the queue ends."""
        if self._macro_state != "stop_end":
            self.stop()
            self._update_macro_state("stop_end")

    def _preload_next_track(self) -> None:
        """Preloads the next track on a background thread to prevent UI micro-stutters."""
        def task():
            with self._lock:
                next_index = self._compute_next_index(self._queue_index)
                if next_index is not None and next_index < len(self._queue):
                    try:
                        next_path = self._queue[next_index]
                        self._next_file = AudioStreamWrapper(next_path, self._volume)
                    except Exception:
                        self._next_file = None
                else:
                    self._next_file = None
        threading.Thread(target=task, daemon=True).start()

    def _load_track(self, filepath: str) -> bool:
        with self._lock:
            try:
                if not os.path.exists(filepath):
                    return False
                self._current_file = AudioStreamWrapper(filepath, self._volume)
                return True
            except Exception as e:
                self.error_occurred.emit(filepath, f"Codec Decoding Error: {str(e)}")
                return False

    # ============================================================
    # State & Persistence Management
    # ============================================================
    def _restore_initial_state(self, state) -> None:
        if state.current_track_path and os.path.exists(state.current_track_path):
            self._load_track(state.current_track_path)
            if state.position_seconds > 0:
                self.seek(state.position_seconds)
        self._update_macro_state("stop_initial")

    def _update_macro_state(self, new_state: str) -> None:
        self._macro_state = new_state
        if new_state == "scrubbing":
            self.playback_state_changed.emit("playing" if self._was_playing_before_seek else "paused")
        elif new_state == "playing":
            self.playback_state_changed.emit("playing")
        elif new_state in ("paused", "stop_initial", "stop_end"):
            self.playback_state_changed.emit("paused")

    def _on_progress_tick(self) -> None:
        """Strictly updates the UI progress bar. Does NOT alter playback state."""
        if self._current_file and self._macro_state == "playing":
            pos = self.get_position_seconds()
            dur = self.get_duration_seconds()
            if dur > 0:
                self.position_changed.emit(pos, dur)

    # ============================================================
    # Public Transport Controls
    # ============================================================
    def play(self) -> None:
        if self._current_file is None and self._queue:
            self._play_queue_index(self._queue_index if self._queue_index >= 0 else 0)
            return
        self._update_macro_state("playing")
        self._progress_timer.start()
        self._save_timer.start()

    def pause(self) -> None:
        self._update_macro_state("paused")
        self._progress_timer.stop()
        self._save_timer.stop()

    def toggle_play_pause(self) -> None:
        if self._macro_state == "playing":
            self.pause()
        elif self._macro_state == "stop_end":
            if self._queue:
                self._play_queue_index(0)
        else:
            self.play()

    def stop(self) -> None:
        self._progress_timer.stop()
        self._save_timer.stop()
        with self._lock:
            self._current_file = None
            self._next_file = None
        self._update_macro_state("stop_initial")
        self.position_changed.emit(0.0, 0.0)

    def seek(self, position_seconds: float) -> None:
        with self._lock:
            if self._current_file:
                try:
                    target_frame = int(position_seconds * self._current_file.sample_rate)
                    self._current_file.seek_to_pcm_frame(target_frame)
                except Exception:
                    pass
        self.position_changed.emit(self.get_position_seconds(), self.get_duration_seconds())

    def next_track(self) -> None:
        if not self._queue: return
        next_index = self._compute_next_index(self._queue_index)
        if next_index is not None:
            self._play_queue_index(next_index)
        else:
            self.stop()
            self._update_macro_state("stop_end")

    def prev_track(self) -> None:
        if not self._queue: return
        if self.get_position_seconds() > SMART_PREV_THRESHOLD_SECONDS:
            self.seek(0.0)
            return
        prev_index = self._compute_prev_index(self._queue_index)
        if prev_index is not None:
            self._play_queue_index(prev_index)

    def _play_queue_index(self, index: int) -> None:
        if not (0 <= index < len(self._queue)):
            self.stop()
            return
            
        self._queue_index = index
        self._persist_queue()
        path = self._queue[index]
        
        if self._load_track(path):
            self._emit_specs_async(path)
            self.track_changed.emit(path)
            self._preload_next_track()
            
            self._update_macro_state("playing")
            self._progress_timer.start()
            self._save_timer.start()
        else:
            self.next_track()

    # ============================================================
    # Press-and-Hold Seek (Scrubbing)
    # ============================================================
    def start_seek_forward(self) -> None:
        if self._macro_state == "stop_initial" or not self.get_current_track_path():
            return
        self._is_seeking = True
        self._seek_direction = 1
        self._was_playing_before_seek = (self._macro_state == "playing")
        self._update_macro_state("scrubbing")
        self._seek_timer.start(700)
        self._on_seek_tick()

    def start_seek_back(self) -> None:
        if self._macro_state == "stop_initial" or not self.get_current_track_path():
            return
        self._is_seeking = True
        self._seek_direction = -1
        self._was_playing_before_seek = (self._macro_state == "playing")
        self._update_macro_state("scrubbing")
        self._seek_timer.start(700)
        self._on_seek_tick()

    def _on_seek_tick(self) -> None:
        dur = self.get_duration_seconds()
        if dur <= 0: return
        pos = self.get_position_seconds()
        new_pos = max(0.0, min(dur, pos + (5.0 * self._seek_direction)))
        self.seek(new_pos)

    def stop_seek(self) -> None:
        self._seek_timer.stop()
        self._is_seeking = False
        if getattr(self, '_was_playing_before_seek', False):
            self.play()
        else:
            self.pause()

    # ============================================================
    # Audio Volume Properties
    # ============================================================
    def set_volume(self, volume: float) -> None:
        volume = max(0.0, min(1.0, volume))
        self._volume = volume
        with self._lock:
            if self._current_file:
                self._current_file.volume = volume
        self.store.cache.player_state.volume = volume
        self.store.cache.save()
        self.volume_changed.emit(volume)

    def get_volume(self) -> float:
        return self._volume

    # ============================================================
    # Playlist Queue & Shuffling Core
    # ============================================================
    def set_repeat_mode(self, mode: str) -> None:
        if mode not in ("off", "all", "one"):
            raise ValueError(f"Invalid repeat mode: {mode!r}")
        self._repeat_mode = mode
        self.store.cache.player_state.repeat_mode = mode
        self.store.cache.save()
        self.repeat_mode_changed.emit(mode)
        self._preload_next_track() 

    def get_repeat_mode(self) -> str:
        return self._repeat_mode

    def set_shuffle(self, enabled: bool) -> None:
        self._shuffle = enabled
        current_path = self.get_current_track_path()
        if enabled:
            shuffled = list(self._original_queue)
            if current_path in shuffled:
                shuffled.remove(current_path)
                random.shuffle(shuffled)
                self._queue = [current_path] + shuffled
                self._queue_index = 0
            else:
                random.shuffle(shuffled)
                self._queue = shuffled
                self._queue_index = 0 if self._queue else -1
        else:
            self._queue = list(self._original_queue)
            self._queue_index = self._queue.index(current_path) if current_path in self._queue else 0

        self.store.cache.player_state.shuffle = enabled
        self._persist_queue()
        self.shuffle_changed.emit(enabled)
        self._preload_next_track()

    def get_shuffle(self) -> bool:
        return self._shuffle

    def get_queue(self) -> list[str]:
        return list(self._queue)

    def get_queue_index(self) -> int:
        return self._queue_index

    def play_all(self, track_paths: list[str], shuffle: bool = False, start_track_path: Optional[str] = None) -> None:
        seen = set()
        deduped = [x for x in track_paths if not (x in seen or seen.add(x))]
        self._original_queue = list(deduped)
        self._shuffle = shuffle
        
        if shuffle:
            shuffled = list(deduped)
            if start_track_path in shuffled:
                shuffled.remove(start_track_path)
                random.shuffle(shuffled)
                self._queue = [start_track_path] + shuffled
                self._queue_index = 0
            else:
                random.shuffle(shuffled)
                self._queue = shuffled
                self._queue_index = 0 if self._queue else -1
        else:
            self._queue = list(deduped)
            self._queue_index = self._queue.index(start_track_path) if start_track_path in self._queue else 0

        self._persist_queue()
        self.queue_changed.emit()
        self.shuffle_changed.emit(shuffle)
        if self._queue and self._queue_index >= 0:
            self._play_queue_index(self._queue_index)

    # ============================================================
    # Queries & Helpers
    # ============================================================
    def _compute_next_index(self, from_index: int) -> Optional[int]:
        if not self._queue: return None
        if self._repeat_mode == "one": return from_index
        next_index = from_index + 1
        if next_index < len(self._queue): return next_index
        return 0 if self._repeat_mode == "all" else None
    
    def _compute_prev_index(self, current: int) -> Optional[int]:
        if not self._queue: return None
        prev_idx = current - 1
        if prev_idx >= 0: return prev_idx
        return len(self._queue) - 1 if self._repeat_mode == "all" else None

    def get_current_track_path(self) -> Optional[str]:
        return self._queue[self._queue_index] if 0 <= self._queue_index < len(self._queue) else None
        
    def get_current_track(self):
        path = self.get_current_track_path()
        return self.store.get_track(path) if path else None

    def is_playing(self) -> bool:
        return self._macro_state == "playing"

    def get_position_seconds(self) -> float:
        with self._lock:
            if self._current_file and self._current_file.sample_rate > 0:
                return self._current_file.current_frame / self._current_file.sample_rate
            return 0.0

    def get_duration_seconds(self) -> float:
        with self._lock:
            if self._current_file:
                return self._current_file.duration
            return 0.0

    def _persist_position(self) -> None:
        if self._macro_state in ("playing", "paused"):
            self.store.cache.player_state.position_seconds = self.get_position_seconds()
            self.store.cache.player_state.current_track_path = self.get_current_track_path()
            self.store.cache.save()

    def _persist_queue(self) -> None:
        self.store.cache.player_state.queue = list(self._queue)
        self.store.cache.player_state.queue_index = self._queue_index
        self.store.cache.save()

    def list_output_devices(self): return []
    def set_output_device(self, device): pass
    def current_output_device(self): return None