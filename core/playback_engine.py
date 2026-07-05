"""
PlaybackEngine: AuraPlayer Explicit Macro State Machine Implementation.
Wraps PyQt6's QMediaPlayer/QAudioOutput to provide synchronized UI states,
quantized audio-burst/silent scrubbing based on initial state, gapless handoff,
and rigorous playlist boundary management (stop_end state).
"""

from __future__ import annotations

import random
import os
from typing import Optional

from PyQt6.QtCore import QObject, pyqtSignal, QTimer, QUrl, Qt
from PyQt6.QtMultimedia import QMediaPlayer, QAudioOutput, QMediaDevices, QAudioDevice

# Assuming these exist in your project structure
# from core.library_store import LibraryStore
# from core.models import Track

GAPLESS_HANDOFF_LEAD_MS = 500
POSITION_SAVE_INTERVAL_MS = 1200
SMART_PREV_THRESHOLD_SECONDS = 3.0

class PlaybackEngine(QObject):
    # --- Signals the UI subscribes to ---
    track_changed = pyqtSignal(str)            # new current track path (or "" if none)
    playback_state_changed = pyqtSignal(str)    # "playing" | "paused"
    position_changed = pyqtSignal(float, float)  # position_seconds, duration_seconds
    queue_changed = pyqtSignal()                 # queue contents or order changed
    repeat_mode_changed = pyqtSignal(str)
    shuffle_changed = pyqtSignal(bool)
    volume_changed = pyqtSignal(float)         
    output_device_changed = pyqtSignal(str)        # device description
    error_occurred = pyqtSignal(str, str)           # track path, error message
    seek_hold_tick = pyqtSignal(float, float)        # position_seconds, duration_seconds (during a held seek)

    # ============================================================
    # Seek Configuration
    # ============================================================
    SEEK_CYCLE_INTERVAL_MS = 700  
    SEEK_STEP_MS = 5000        
    AUDIO_BURST_DURATION_MS = 500 

    def __init__(self, store, parent=None):
        super().__init__(parent)
        self.store = store
        state = self.store.cache.player_state

        # --- Dual players for gapless playback ---
        self._player_a = QMediaPlayer(self)
        self._audio_a = QAudioOutput(self)
        self._player_a.setAudioOutput(self._audio_a)

        self._player_b = QMediaPlayer(self)
        self._audio_b = QAudioOutput(self)
        self._player_b.setAudioOutput(self._audio_b)

        self._active = self._player_a
        self._active_output = self._audio_a
        self._standby = self._player_b
        self._standby_output = self._audio_b
        self._standby_output.setVolume(0.0)  # standby is always silent until handoff

        self._duration_seconds: float = 0.0
        self._handoff_armed = False  # prevents firing the gapless handoff twice for one track
        self._pending_restore_position = 0.0

        # Restore volume from last session
        self._volume = state.volume
        self._active_output.setVolume(self._volume)

        # Restore the output device
        if state.output_device_id:
            self._restore_output_device(state.output_device_id)

        self._connect_active_signals()

        # --- Queue / playback state ---
        self._shuffle: bool = state.shuffle
        self._queue: list[str] = list(state.queue)
        self._queue_index: int = state.queue_index
        self._repeat_mode: str = state.repeat_mode
        self._original_queue: list[str] = list(self._queue)

        # --- Continuous position persistence ---
        self._save_timer = QTimer(self)
        self._save_timer.setInterval(POSITION_SAVE_INTERVAL_MS)
        self._save_timer.timeout.connect(self._persist_position)
        self._save_timer.start()

        # --- Explicit Macro State Machine ---
        # States: "stop_initial", "playing", "paused", "scrubbing", "stop_end"
        self._macro_state: str = "stop_initial"

        # --- Internal Seeking State ---
        self._is_seeking: bool = False
        self._seek_direction: int = 0
        self._was_playing_before_seek: bool = False

        # Main timer for the scrubbing loop
        self._seek_timer = QTimer(self)
        self._seek_timer.timeout.connect(self._on_seek_tick)

        # Sub-timer to cut off the audio burst
        self._burst_cutoff_timer = QTimer(self)
        self._burst_cutoff_timer.setSingleShot(True)
        self._burst_cutoff_timer.timeout.connect(self._on_burst_cutoff)

        # Precise gapless scheduler timer
        self._handoff_timer = QTimer(self)
        self._handoff_timer.setSingleShot(True)
        self._handoff_timer.setTimerType(Qt.TimerType.PreciseTimer)
        self._handoff_timer.timeout.connect(self._perform_gapless_handoff)

        # Clean-up timer to stop and mute the old player after a small overlap
        self._old_player_cleanup_timer = QTimer(self)
        self._old_player_cleanup_timer.setSingleShot(True)
        self._old_player_cleanup_timer.timeout.connect(self._cleanup_old_player)

        # Restore the last session's track + position
        self._restore_initial_state(state)

    # ============================================================
    # State Machine Authority (Single Source of Truth)
    # ============================================================
    def _update_macro_state(self, new_state: str) -> None:
        """Central authority to transition between states and sync with UI."""
        self._macro_state = new_state
        
        if new_state == "scrubbing":
            if self._was_playing_before_seek:
                self.playback_state_changed.emit("playing")
            else:
                self.playback_state_changed.emit("paused")
        elif new_state == "playing":
            self.playback_state_changed.emit("playing")
        elif new_state in ("paused", "stop_initial", "stop_end"):
            self.playback_state_changed.emit("paused")

    def _on_playback_state_changed(self, state) -> None:
        """Handles background state updates from QMediaPlayer."""
        if self._macro_state in ("scrubbing", "playing"):
            return

        mapping = {
            QMediaPlayer.PlaybackState.PlayingState: "playing",
            QMediaPlayer.PlaybackState.PausedState: "paused",
            QMediaPlayer.PlaybackState.StoppedState: "stopped",
        }
        self.playback_state_changed.emit(mapping.get(state, "stopped"))

    # ============================================================
    # Restoration
    # ============================================================
    def _restore_output_device(self, device_id: str) -> None:
        for device in QMediaDevices.audioOutputs():
            if bytes(device.id()).decode("utf-8", errors="ignore") == device_id:
                self._active_output.setDevice(device)
                self._standby_output.setDevice(device)
                return

    def _restore_initial_state(self, state) -> None:
        if state.current_track_path and self.store.get_track(state.current_track_path):
            self._set_active_source(state.current_track_path)
            self._pending_restore_position = state.position_seconds
        else:
            self._pending_restore_position = 0.0

    # ============================================================
    # Public transport controls
    # ============================================================
    def play(self) -> None:
        if self._active.source().isEmpty():
            if self._queue:
                self._play_queue_index(self._queue_index if self._queue_index >= 0 else 0)
            return
        self._active.play()
        self._save_timer.start()
        self._update_macro_state("playing")

    def pause(self) -> None:
        self._active.pause()
        self._save_timer.stop()
        self._handoff_timer.stop()
        self._update_macro_state("paused")

    def toggle_play_pause(self) -> None:
        if self._macro_state == "playing":
            self.pause()
        elif self._macro_state == "stop_end":
            if self._queue:
                self._play_queue_index(0)
        else:
            self.play()

    def stop(self) -> None:
        self.force_reset_seek_state()
        self._handoff_timer.stop()
        self._handoff_armed = False
        self._active.stop()
        self._standby.stop()
        self._save_timer.stop()
        self._update_macro_state("stop_initial")
        self.position_changed.emit(0.0, 0.0)

    def seek(self, position_seconds: float) -> None:
        self._active.setPosition(int(position_seconds * 1000))
        self._handoff_armed = True
        self._handoff_timer.stop()

    def next_track(self) -> None:
        if not self._queue:
            return
            
        if self._macro_state == "stop_end":
            self.force_reset_seek_state()
            self._queue_index = 0
            self._persist_queue()
            path = self._queue[0]
            self._set_active_source(path)
            self._active.pause()
            self._save_timer.stop()
            self._update_macro_state("paused")
            self.track_changed.emit(path)
            self._preload_standby()
            return

        next_index = self._compute_next_index(self._queue_index)
        if next_index is not None:
            current_state = self._macro_state
            self.force_reset_seek_state()
            self._queue_index = next_index
            self._persist_queue()
            path = self._queue[next_index]
            self._set_active_source(path)
            
            if current_state in ("playing", "scrubbing"):
                self._active.play()
                self._save_timer.start()
                self._update_macro_state("playing")
            else:
                self._active.pause()
                self._save_timer.stop()
                self._update_macro_state("paused")
                
            self.track_changed.emit(path)
            self._preload_standby()

    def prev_track(self) -> None:
        if not self._queue:
            return
            
        if self._macro_state == "stop_end":
            self.force_reset_seek_state()
            self.seek(0.0)
            self._active.pause()
            self._save_timer.stop()
            self._update_macro_state("paused")
            return

        if self._active.position() > (SMART_PREV_THRESHOLD_SECONDS * 1000):
            self.seek(0.0)
            return

        prev_index = self._compute_prev_index(self._queue_index)
        if prev_index is not None:
            current_state = self._macro_state
            self.force_reset_seek_state()
            self._queue_index = prev_index
            self._persist_queue()
            path = self._queue[prev_index]
            self._set_active_source(path)
            
            if current_state in ("playing", "scrubbing"):
                self._active.play()
                self._save_timer.start()
                self._update_macro_state("playing")
            else:
                self._active.pause()
                self._save_timer.stop()
                self._update_macro_state("paused")
                
            self.track_changed.emit(path)
            self._preload_standby()

    # ============================================================
    # Press-and-hold seek
    # ============================================================
    def start_seek_forward(self) -> None:
        if self._macro_state == "stop_initial" or not self.get_current_track_path():
            return
        self._was_playing_before_seek = (self._macro_state == "playing")
        self._is_seeking = True
        self._seek_direction = 1
        
        self._update_macro_state("scrubbing")
        self._seek_timer.start(self.SEEK_CYCLE_INTERVAL_MS)
        self._on_seek_tick()

    def start_seek_back(self) -> None:
        if self._macro_state == "stop_initial" or not self.get_current_track_path():
            return
        self._was_playing_before_seek = (self._macro_state == "playing")
        self._is_seeking = True
        self._seek_direction = -1
        
        self._update_macro_state("scrubbing")
        self._seek_timer.start(self.SEEK_CYCLE_INTERVAL_MS)
        self._on_seek_tick()

    def _on_seek_tick(self) -> None:
        duration_ms = self._active.duration()
        if duration_ms <= 0:
            return

        current_pos_ms = self._active.position()
        step_ms = self.SEEK_STEP_MS * self._seek_direction
        new_pos_ms = max(0, min(duration_ms, current_pos_ms + step_ms))

        self._active.setPosition(new_pos_ms)
        self.position_changed.emit(new_pos_ms / 1000.0, duration_ms / 1000.0)
        self.seek_hold_tick.emit(new_pos_ms / 1000.0, duration_ms / 1000.0)

        if self._was_playing_before_seek:
            self._active.pause()
            QTimer.singleShot(40, self._force_audio_play_burst)
        else:
            self._active.pause()

    def _force_audio_play_burst(self) -> None:
        if not self._is_seeking or not self._was_playing_before_seek:
            return
        self._active.play()
        self._burst_cutoff_timer.start(self.AUDIO_BURST_DURATION_MS)

    def _on_burst_cutoff(self) -> None:
        if self._is_seeking and self._was_playing_before_seek:
            self._active.pause()

    def stop_seek(self) -> None:
        self._seek_timer.stop()
        self._burst_cutoff_timer.stop()
        self._is_seeking = False
        
        if self._was_playing_before_seek:
            self._active.play()
            self._update_macro_state("playing")
        else:
            self._active.pause()
            self._update_macro_state("paused")
            
        self._persist_position()

    def force_reset_seek_state(self) -> None:
        self._seek_timer.stop()
        self._burst_cutoff_timer.stop()
        self._handoff_timer.stop()
        self._old_player_cleanup_timer.stop()
        self._standby.stop()
        self._standby_output.setVolume(0.0)
        self._is_seeking = False
        self._was_playing_before_seek = False

    # ============================================================
    # Volume / output device
    # ============================================================
    def set_volume(self, volume: float) -> None:
        volume = max(0.0, min(1.0, volume))
        self._volume = volume
        self._active_output.setVolume(volume)
        self.store.cache.player_state.volume = volume
        self.store.cache.save()
        self.volume_changed.emit(volume)

    def get_volume(self) -> float:
        return self._volume

    def list_output_devices(self) -> list[QAudioDevice]:
        return list(QMediaDevices.audioOutputs())

    def set_output_device(self, device: QAudioDevice) -> None:
        self._active_output.setDevice(device)
        self._standby_output.setDevice(device)
        device_id = bytes(device.id()).decode("utf-8", errors="ignore")
        self.store.cache.player_state.output_device_id = device_id
        self.store.cache.save()
        self.output_device_changed.emit(device.description())

    def current_output_device(self) -> QAudioDevice:
        if hasattr(self, '_active_output') and self._active_output:
            return self._active_output.device()
        return QMediaDevices.defaultAudioOutput()

    # ============================================================
    # Repeat / shuffle
    # ============================================================
    def set_repeat_mode(self, mode: str) -> None:
        if mode not in ("off", "all", "one"):
            raise ValueError(f"Invalid repeat mode: {mode!r}")
        self._repeat_mode = mode
        self.store.cache.player_state.repeat_mode = mode
        self.store.cache.save()
        self.repeat_mode_changed.emit(mode)

    def get_repeat_mode(self) -> str:
        return self._repeat_mode

    def set_shuffle(self, enabled: bool) -> None:
        self._shuffle = enabled
        current_path = self.get_current_track_path()
        if enabled:
            # Shuffle the queue, keeping the currently playing track first
            shuffled = list(self._original_queue)
            if current_path is not None and current_path in shuffled:
                shuffled.remove(current_path)
                random.shuffle(shuffled)
                self._queue = [current_path] + shuffled
                self._queue_index = 0
            else:
                random.shuffle(shuffled)
                self._queue = shuffled
                self._queue_index = 0 if self._queue else -1
        else:
            # Restore the original queue order
            self._queue = list(self._original_queue)
            if current_path is not None and current_path in self._queue:
                self._queue_index = self._queue.index(current_path)
            else:
                self._queue_index = 0 if self._queue else -1

        self.store.cache.player_state.shuffle = enabled
        self._persist_queue()
        self.shuffle_changed.emit(enabled)

    def get_shuffle(self) -> bool:
        return self._shuffle
        indices = list(range(len(self._queue)))
        if keep_current_first and 0 <= self._queue_index < len(self._queue):
            current_val = self._queue_index
            other_indices = [idx for idx in indices if idx != current_val]
            random.shuffle(other_indices)
            self._shuffle_order = [current_val] + other_indices
        else:
            random.shuffle(indices)
            self._shuffle_order = indices

    # ============================================================
    # Queue management
    # ============================================================
    def get_queue(self) -> list[str]:
        return list(self._queue)

    def get_queue_index(self) -> int:
        return self._queue_index

    def play_all(self, track_paths: list[str], shuffle: bool = False, start_track_path: Optional[str] = None) -> None:
        seen = set()
        deduped = []
        for p in track_paths:
            if p not in seen:
                seen.add(p)
                deduped.append(p)

        self._original_queue = list(deduped)
        self._shuffle = shuffle
        
        if shuffle:
            shuffled = list(deduped)
            if start_track_path is not None and start_track_path in shuffled:
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
            start_index = 0
            if start_track_path is not None and start_track_path in self._queue:
                start_index = self._queue.index(start_track_path)
            self._queue_index = start_index if self._queue else -1

        self._persist_queue()
        self.queue_changed.emit()
        self.shuffle_changed.emit(shuffle)

        if self._queue and self._queue_index >= 0:
            self._play_queue_index(self._queue_index)
    
    def play_next(self, track_path: str) -> None:
        current_path = self.get_current_track_path()
        self._remove_from_original_queue_silently(track_path)
        self._remove_from_queue_silently(track_path)

        # Insert into original queue after current track
        if current_path is not None and current_path in self._original_queue:
            insert_at_orig = self._original_queue.index(current_path) + 1
        else:
            insert_at_orig = max(0, self._queue_index + 1)
        self._original_queue.insert(insert_at_orig, track_path)

        # Insert into active queue after current track index
        if 0 <= self._queue_index < len(self._queue):
            insert_at_act = self._queue_index + 1
        else:
            insert_at_act = 0
        self._queue.insert(insert_at_act, track_path)

        self._resync_queue_index_to_current_track(fallback_path=current_path)
        self._persist_queue()
        self.queue_changed.emit()

        if current_path is None and len(self._queue) == 1:
            self._play_queue_index(0)

    def add_to_queue(self, track_path: str) -> None:
        current_path = self.get_current_track_path()
        was_empty_or_stopped = current_path is None or self._active.source().isEmpty()

        self._remove_from_original_queue_silently(track_path)
        self._remove_from_queue_silently(track_path)
        self._original_queue.append(track_path)
        self._queue.append(track_path)
        
        self._resync_queue_index_to_current_track(fallback_path=current_path)
        self._persist_queue()
        self.queue_changed.emit()

        if was_empty_or_stopped:
            new_index = self._queue.index(track_path)
            self._play_queue_index(new_index)

    def remove_from_queue(self, track_path: str) -> None:
        was_current = (0 <= self._queue_index < len(self._queue) and self._queue[self._queue_index] == track_path)
        self._remove_from_original_queue_silently(track_path)
        self._remove_from_queue_silently(track_path)
        self._persist_queue()
        self.queue_changed.emit()

        if was_current:
            if self._queue:
                next_index = min(self._queue_index, len(self._queue) - 1)
                self._play_queue_index(next_index)
            else:
                self.stop()
                self._queue_index = -1
                self._set_active_source(None)

    def _remove_from_original_queue_silently(self, track_path: str) -> None:
        if track_path in self._original_queue:
            self._original_queue.remove(track_path)

    def _remove_from_queue_silently(self, track_path: str) -> None:
        if track_path in self._queue:
            self._queue.remove(track_path)

        if was_current:
            if self._queue:
                next_index = min(self._queue_index, len(self._queue) - 1)
                self._play_queue_index(next_index)
            else:
                self.stop()
                self._queue_index = -1
                self._set_active_source(None)

    def reorder_queue(self, new_order: list[str]) -> None:
        if sorted(new_order) != sorted(self._queue):
            raise ValueError("reorder_queue() received a different set of tracks.")
        current_path = self._queue[self._queue_index] if 0 <= self._queue_index < len(self._queue) else None
        self._queue = list(new_order)
        self._original_queue = list(new_order)
        self._resync_queue_index_to_current_track(fallback_path=current_path)
        self._persist_queue()
        self.queue_changed.emit()

    def _remove_from_original_queue_silently(self, track_path: str) -> None:
        if track_path in self._original_queue:
            self._original_queue.remove(track_path)

    def _remove_from_queue_silently(self, track_path: str) -> None:
        if track_path in self._queue:
            self._queue.remove(track_path)

    def _resync_queue_index_to_current_track(self, fallback_path: Optional[str] = None) -> None:
        current_path = fallback_path
        if current_path is None and 0 <= self._queue_index < len(self._queue):
            current_path = self._queue[self._queue_index]
        if current_path is None:
            current_path = self.get_current_track_path()

        if current_path and current_path in self._queue:
            self._queue_index = self._queue.index(current_path)
        elif not self._queue:
            self._queue_index = -1

    # ============================================================
    # Internal playback mechanics
    # ============================================================
    def _set_active_source(self, track_path: Optional[str]) -> None:
        if not track_path:
            self._active.setSource(QUrl())
            return
        self._active.setSource(QUrl.fromLocalFile(track_path))
        self._handoff_armed = True
        self._handoff_timer.stop()

    def _preload_standby(self) -> None:
        next_index = self._compute_next_index(self._queue_index)
        if next_index is not None and next_index < len(self._queue):
            next_path = self._queue[next_index]
            self._standby.setSource(QUrl.fromLocalFile(next_path))
            self._standby.pause()
        else:
            self._standby.setSource(QUrl())
    
    def _play_queue_index(self, index: int) -> None:
        if not (0 <= index < len(self._queue)):
            self.stop()
            return
            
        self.force_reset_seek_state()
        self._queue_index = index
        self._persist_queue()
        path = self._queue[index]
        
        self._update_macro_state("playing")
        
        self._set_active_source(path)
        self._active.play()
        self._save_timer.start()
        
        self.track_changed.emit(path)
        self._preload_standby()

    def _compute_next_index(self, from_index: int) -> Optional[int]:
        if not self._queue:
            return None
        if self._repeat_mode == "one":
            return from_index
        next_index = from_index + 1
        if next_index < len(self._queue):
            return next_index
        if self._repeat_mode == "all":
            return 0
        return None
    
    def _compute_prev_index(self, current: int) -> Optional[int]:
        if not self._queue:
            return None
        if current < 0:
            return len(self._queue) - 1
        prev_idx = current - 1
        if prev_idx < 0:
            if self._repeat_mode == "all":
                return len(self._queue) - 1
            return None
        return prev_idx

    def _disconnect_signals(self, player) -> None:
        for signal, slot in (
            (player.positionChanged, self._on_position_changed),
            (player.durationChanged, self._on_duration_changed),
            (player.mediaStatusChanged, self._on_media_status_changed),
            (player.playbackStateChanged, self._on_playback_state_changed),
            (player.errorOccurred, self._on_error),
        ):
            try:
                signal.disconnect(slot)
            except TypeError:
                pass

    def _perform_gapless_handoff(self) -> None:
        if not self._handoff_armed:
            return
        self._handoff_armed = False

        self.force_reset_seek_state()
        self._handoff_timer.stop()
        self._old_player_cleanup_timer.stop()

        # Cleanly disconnect the old active player signals before swapping
        self._disconnect_signals(self._active)

        # Let the standby player output take the current playback volume
        self._standby_output.setVolume(self._volume)

        # Swap active and standby players and outputs.
        # Note: the old active player keeps playing at its current volume for the brief overlap.
        self._active, self._standby = self._standby, self._active
        self._active_output, self._standby_output = self._standby_output, self._active_output

        self._connect_active_signals()

        if self._macro_state in ("playing", "scrubbing"):
            self._active.play()
            self._update_macro_state("playing")
        else:
            self._active.pause()
            self._update_macro_state("paused")

        self._duration_seconds = self._active.duration() / 1000.0
        self.position_changed.emit(self._active.position() / 1000.0, self._duration_seconds)

        next_index = self._compute_next_index(self._queue_index)
        if next_index is not None:
            self._queue_index = next_index
            self._persist_queue()
            self.track_changed.emit(self._queue[next_index])
            
        self._handoff_armed = True
        
        # Schedule the clean-up (mute and stop) of the old active player (now self._standby) after a short overlap
        self._old_player_cleanup_timer.start(250)

    def _cleanup_old_player(self) -> None:
        self._standby_output.setVolume(0.0)
        self._standby.stop()
        self._preload_standby()

    def _connect_active_signals(self) -> None:
        self._disconnect_signals(self._active)
        player = self._active
        player.positionChanged.connect(self._on_position_changed)
        player.durationChanged.connect(self._on_duration_changed)
        player.mediaStatusChanged.connect(self._on_media_status_changed)
        player.playbackStateChanged.connect(self._on_playback_state_changed)
        player.errorOccurred.connect(self._on_error)

    # ============================================================
    # QMediaPlayer signal handlers
    # ============================================================
    def _on_position_changed(self, position_ms: int) -> None:
        if self._macro_state == "scrubbing":
            return

        duration_ms = self._active.duration()
        if duration_ms > 0:
            time_remaining = duration_ms - position_ms
            
            # Dynamic lookahead scheduling
            next_index = self._compute_next_index(self._queue_index)
            if next_index is not None and self._handoff_armed:
                if time_remaining <= 1500:
                    # Lead-time of 250ms handles the QMediaPlayer start/decode latency and overlap
                    lead_time = 250
                    target_delay = max(0, time_remaining - lead_time)
                    self._handoff_timer.start(int(target_delay))

        self.position_changed.emit(position_ms / 1000.0, duration_ms / 1000.0)

    def _on_duration_changed(self, duration_ms: int) -> None:
        self._duration_seconds = duration_ms / 1000.0

    def _on_media_status_changed(self, status) -> None:
        if status == QMediaPlayer.MediaStatus.LoadedMedia:
            if self._pending_restore_position > 0:
                self.seek(self._pending_restore_position)
                self._pending_restore_position = 0.0
            self._duration_seconds = self._active.duration() / 1000.0
            self.position_changed.emit(self._active.position() / 1000.0, self._duration_seconds)
        elif status == QMediaPlayer.MediaStatus.EndOfMedia:
            next_index = self._compute_next_index(self._queue_index)
            if next_index is None:
                self._update_macro_state("stop_end")
                self._active.stop()
                self._save_timer.stop()
            else:
                self._play_queue_index(next_index)

    def _on_error(self, error, error_string: str) -> None:
        current_path = self.get_current_track_path() or "Unknown Track"
        self.error_occurred.emit(current_path, error_string)
        self.force_reset_seek_state()
        self._update_macro_state("stop_initial")

    # ============================================================
    # Persistence
    # ============================================================
    def _persist_position(self) -> None:
        if self._macro_state in ("playing", "paused"):
            self.store.cache.player_state.position_seconds = self._active.position() / 1000.0
            self.store.cache.player_state.current_track_path = self.get_current_track_path()
            self.store.cache.save()

    def _persist_queue(self) -> None:
        self.store.cache.player_state.queue = list(self._queue)
        self.store.cache.player_state.queue_index = self._queue_index
        self.store.cache.save()

    # ============================================================
    # Queries
    # ============================================================
    def get_current_track_path(self) -> Optional[str]:
        if 0 <= self._queue_index < len(self._queue):
            return self._queue[self._queue_index]
        return None

    def get_current_track(self) -> Optional[Track]:
        path = self.get_current_track_path()
        return self.store.get_track(path) if path else None

    def is_playing(self) -> bool:
        return self._macro_state == "playing"

    def get_position_seconds(self) -> float:
        return self._active.position() / 1000.0

    def get_duration_seconds(self) -> float:
        return self._duration_seconds