"""
PlaybackEngine: wraps PyQt6's QMediaPlayer/QAudioOutput to provide
play/pause/seek/volume/output-device control, a unique-by-path queue,
repeat/shuffle modes, gapless playback via a dual-player handoff, and
continuous (~1s) position persistence for restart recovery.

Architecture notes:

- TWO QMediaPlayer/QAudioOutput pairs are kept at all times: `_active`
  (currently audible) and `_standby` (preloaded with the next track,
  silent, ready to take over instantly). At ~95% of the active track's
  duration, playback hands off to `_standby` with no gap, then the
  roles swap and the new standby is loaded with whatever comes next.
  Volume and output device are applied to BOTH players whenever
  changed, so the handoff is inaudible (no volume jump) and device
  selection doesn't silently revert on the next track.

- The queue is a flat list[str] of track paths with a hard invariant:
  no path appears twice. "Play Next" and "Add to Queue" both check for
  an existing occurrence first and MOVE it rather than insert a
  duplicate -- see play_next() / add_to_queue().

- Position is persisted continuously (~1s) via a QTimer-driven callback
  into LibraryStore, NOT by writing the full JSON cache on every tick.
  LibraryStore.save() goes through LibraryCache's atomic write, which
  is correct for discrete events but too heavy to call every second --
  see _persist_position()'s comment for the throttling approach.
"""

from __future__ import annotations

import random
from typing import Optional

from PyQt6.QtCore import QObject, pyqtSignal, QTimer, QUrl
from PyQt6.QtMultimedia import QMediaPlayer, QAudioOutput, QMediaDevices, QAudioDevice

from core.library_store import LibraryStore
from core.models import Track

# Hand off to the preloaded next track when the active one reaches this
# fraction of its total duration -- leaves enough margin for the standby
# player's own brief load latency to resolve before the boundary arrives.
GAPLESS_HANDOFF_FRACTION = 0.95

# How often playback position is pushed into the persisted PlayerState.
POSITION_SAVE_INTERVAL_MS = 1000

# Below this many seconds into a track, "Previous" actually goes to the
# previous track. At or above it, "Previous" restarts the current track
# from 0:00 instead. (FEATURE_BACKLOG.md item #18 -- "smart Prev".)
SMART_PREV_THRESHOLD_SECONDS = 3.0


class PlaybackEngine(QObject):
    # --- Signals the UI subscribes to ---
    track_changed = pyqtSignal(str)            # new current track path (or "" if none)
    playback_state_changed = pyqtSignal(str)    # "playing" | "paused" | "stopped"
    position_changed = pyqtSignal(float, float)  # position_seconds, duration_seconds
    queue_changed = pyqtSignal()                 # queue contents or order changed
    repeat_mode_changed = pyqtSignal(str)
    shuffle_changed = pyqtSignal(bool)
    volume_changed = pyqtSignal(float)            # 0.0 - 1.0
    output_device_changed = pyqtSignal(str)        # device description
    error_occurred = pyqtSignal(str, str)           # track path, error message

    def __init__(self, store: LibraryStore, parent=None):
        super().__init__(parent)
        self.store = store
        state = self.store.cache.player_state

        # --- Dual players for gapless playback ---
        self._active = QMediaPlayer(self)
        self._active_output = QAudioOutput(self)
        self._active.setAudioOutput(self._active_output)

        self._standby = QMediaPlayer(self)
        self._standby_output = QAudioOutput(self)
        self._standby.setAudioOutput(self._standby_output)
        self._standby_output.setVolume(0.0)  # standby is always silent until handoff

        self._duration_seconds: float = 0.0
        self._handoff_armed = False  # prevents firing the gapless handoff twice for one track
        self._pending_restore_position = 0.0

        # Restore volume from last session instead of a hardcoded default,
        # so the user's volume choice survives a restart like every other
        # piece of player state does.
        self._volume = state.volume
        self._active_output.setVolume(self._volume)

        # Restore the output device by matching the persisted device ID
        # against what's currently available -- a saved ID from a
        # headset that's no longer plugged in simply won't match
        # anything, and we fall back to the system default rather than
        # erroring, since "no matching device" is an expected, common
        # case (not a bug).
        if state.output_device_id:
            self._restore_output_device(state.output_device_id)

        self._connect_active_signals()

        # --- Queue / playback state, restored from the persisted PlayerState ---
        self._queue: list[str] = list(state.queue)
        self._queue_index: int = state.queue_index
        self._repeat_mode: str = state.repeat_mode
        self._shuffle: bool = state.shuffle
        self._shuffle_order: list[int] = []  # indices into _queue, when shuffle is on

        # --- Continuous position persistence ---
        self._save_timer = QTimer(self)
        self._save_timer.setInterval(POSITION_SAVE_INTERVAL_MS)
        self._save_timer.timeout.connect(self._persist_position)

        # Restore the last session's track + position (paused, not
        # auto-playing -- nobody wants music blasting the instant the
        # app opens).
        self._restore_initial_state(state)

    # ============================================================
    # Restoration
    # ============================================================

    def _restore_output_device(self, device_id: str) -> None:
        for device in QMediaDevices.audioOutputs():
            if bytes(device.id()).decode("utf-8", errors="ignore") == device_id:
                self._active_output.setDevice(device)
                self._standby_output.setDevice(device)
                return
        # No match found (device unplugged/changed) -- silently keep
        # whatever Qt's own default output is. Not an error condition.

    def _restore_initial_state(self, state) -> None:
        if state.current_track_path and self.store.get_track(state.current_track_path):
            self._load_into(self._active, state.current_track_path)
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

    def pause(self) -> None:
        self._active.pause()
        self._save_timer.stop()
        self._persist_position()  # capture the exact pause point, not just the last tick

    def toggle_play_pause(self) -> None:
        if self._active.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self.pause()
        else:
            self.play()

    def stop(self) -> None:
        self._active.stop()
        self._save_timer.stop()
        self._persist_position()

    def seek(self, position_seconds: float) -> None:
        self._active.setPosition(int(position_seconds * 1000))
        self._handoff_armed = False  # seeking back from near-the-end un-arms the handoff

    def next_track(self) -> None:
        self._advance(direction=1, user_initiated=True)

    def previous_track(self) -> None:
        """Smart Prev (FEATURE_BACKLOG.md #18): restart the current track
        unless we're within the first few seconds, in which case actually
        go to the previous track -- matches phone/car media control
        conventions.
        """
        if self._active.position() / 1000.0 >= SMART_PREV_THRESHOLD_SECONDS:
            self.seek(0.0)
            if self._active.playbackState() != QMediaPlayer.PlaybackState.PlayingState:
                self.play()
            return
        self._advance(direction=-1, user_initiated=True)

    # ============================================================
    # Volume / output device -- applied to BOTH players (see module docstring)
    # ============================================================

    def set_volume(self, volume: float) -> None:
        volume = max(0.0, min(1.0, volume))
        self._volume = volume
        self._active_output.setVolume(volume)
        # Standby stays silent (0.0) until it becomes active -- only its
        # eventual audible volume needs to match, which happens at
        # _perform_gapless_handoff() time.
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
        return self._active_output.device()

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
        if enabled:
            self._rebuild_shuffle_order(keep_current_first=True)
        self.store.cache.player_state.shuffle = enabled
        self.store.cache.save()
        self.shuffle_changed.emit(enabled)

    def get_shuffle(self) -> bool:
        return self._shuffle

    def _rebuild_shuffle_order(self, keep_current_first: bool = False) -> None:
        indices = list(range(len(self._queue)))
        if keep_current_first and 0 <= self._queue_index < len(indices):
            indices.remove(self._queue_index)
            random.shuffle(indices)
            self._shuffle_order = [self._queue_index] + indices
        else:
            random.shuffle(indices)
            self._shuffle_order = indices

    # ============================================================
    # Queue management -- unique-by-path, with move-on-re-add semantics
    # ============================================================

    def get_queue(self) -> list[str]:
        return list(self._queue)

    def get_queue_index(self) -> int:
        return self._queue_index

    def play_all(
        self, track_paths: list[str], shuffle: bool = False, start_track_path: Optional[str] = None
    ) -> None:
        """Replaces the queue entirely and starts playing from the first
        track, or from `start_track_path` if given (e.g. the user
        double-clicked a specific track within a list -- the queue
        becomes that whole list, but playback starts at the clicked
        one, not necessarily index 0). Shuffle still applies to the
        rest of the queue's order; `start_track_path` simply picks
        where the FIRST-played track is rather than always defaulting
        to the first shuffled position. Per spec, Play All REPLACES the
        queue, never appends.
        """
        # De-dupe defensively even though callers shouldn't pass dupes --
        # the queue's invariant is enforced here, not trusted from callers.
        seen = set()
        deduped = []
        for p in track_paths:
            if p not in seen:
                seen.add(p)
                deduped.append(p)

        self._queue = deduped
        self._shuffle = shuffle
        if shuffle:
            self._rebuild_shuffle_order(keep_current_first=False)
            start_index = self._shuffle_order[0] if self._shuffle_order else 0
        else:
            self._shuffle_order = []
            start_index = 0

        if start_track_path is not None and start_track_path in self._queue:
            start_index = self._queue.index(start_track_path)

        self._queue_index = start_index if self._queue else -1
        self._persist_queue()
        self.queue_changed.emit()
        self.shuffle_changed.emit(shuffle)

        if self._queue:
            self._play_queue_index(self._queue_index)

    def play_next(self, track_path: str) -> None:
        """Insert (or move) `track_path` to play immediately after the
        currently-playing track. If nothing is currently playing, it
        becomes the first item in the queue. Enforces queue uniqueness
        by moving an existing occurrence rather than duplicating it.
        """
        # Capture identity BEFORE any mutation -- once _queue is mutated,
        # self._queue_index may point at the wrong track until resynced,
        # so "what's actually playing" must be read first.
        current_path = self.get_current_track_path()

        self._remove_from_queue_silently(track_path)

        if current_path is not None and current_path in self._queue:
            insert_at = self._queue.index(current_path) + 1
        elif current_path is not None and current_path == track_path:
            # The track being moved WAS the current track and was just
            # removed above -- insert at the front, then resync will
            # find it again as "current" by path.
            insert_at = 0
        elif self._queue_index < 0:
            insert_at = 0
        else:
            insert_at = min(self._queue_index + 1, len(self._queue))

        self._queue.insert(insert_at, track_path)
        self._resync_queue_index_to_current_track(fallback_path=current_path)
        self._persist_queue()
        self.queue_changed.emit()

        if current_path is None and len(self._queue) == 1:
            # Nothing was playing at all -- start now, per spec ("If
            # nothing playing, add as first" implies it should play).
            self._play_queue_index(0)

    def add_to_queue(self, track_path: str) -> None:
        """Add (or move) `track_path` to the END of the queue. If
        nothing is currently playing, starts playing it immediately,
        per spec.
        """
        # Capture identity BEFORE any mutation -- see play_next() comment.
        current_path = self.get_current_track_path()
        was_empty_or_stopped = current_path is None or self._active.source().isEmpty()

        self._remove_from_queue_silently(track_path)
        self._queue.append(track_path)
        self._resync_queue_index_to_current_track(fallback_path=current_path)
        self._persist_queue()
        self.queue_changed.emit()

        if was_empty_or_stopped:
            new_index = self._queue.index(track_path)
            self._play_queue_index(new_index)

    def remove_from_queue(self, track_path: str) -> None:
        """Removes a track from the queue entirely (not just moving it).
        If it's the currently-playing track, advances to the next one
        (or stops, if it was the last one).
        """
        was_current = (
            0 <= self._queue_index < len(self._queue)
            and self._queue[self._queue_index] == track_path
        )
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

    def reorder_queue(self, new_order: list[str]) -> None:
        """Replaces the queue order wholesale (e.g. after a drag-and-drop
        reorder in the Step 8 Queue Panel). Must be a permutation of the
        existing queue -- raises if paths don't match, rather than
        silently dropping/duplicating tracks.
        """
        if sorted(new_order) != sorted(self._queue):
            raise ValueError(
                "reorder_queue() received a different set of tracks than "
                "the current queue -- this must be a pure reorder."
            )
        current_path = (
            self._queue[self._queue_index] if 0 <= self._queue_index < len(self._queue) else None
        )
        self._queue = list(new_order)
        self._resync_queue_index_to_current_track(fallback_path=current_path)
        self._persist_queue()
        self.queue_changed.emit()

    def _remove_from_queue_silently(self, track_path: str) -> None:
        """Removes track_path from _queue if present, without emitting
        queue_changed or persisting -- callers that need to make a
        second mutation (insert/append) right after call this first,
        then do their own single persist+emit at the end.
        """
        if track_path in self._queue:
            self._queue.remove(track_path)

    def _resync_queue_index_to_current_track(self, fallback_path: Optional[str] = None) -> None:
        """After mutating _queue, recompute _queue_index by finding the
        actual current track's path in the new list.

        `fallback_path` should be the track path captured via
        get_current_track_path() BEFORE _queue was mutated -- callers
        must capture this first, since reading _queue_index AFTER a
        mutation can point at the wrong track (the index is stale, but
        the list under it has already changed). When fallback_path is
        given, it's trusted directly; the stale-index read below only
        runs as a last resort if no caller-supplied identity exists.
        """
        current_path = fallback_path
        if current_path is None and 0 <= self._queue_index < len(self._queue):
            current_path = self._queue[self._queue_index]
        if current_path is None:
            current_path = self.get_current_track_path()

        if current_path and current_path in self._queue:
            self._queue_index = self._queue.index(current_path)
        elif not self._queue:
            self._queue_index = -1
        # else: leave _queue_index as-is if we can't determine it --
        # better than guessing wrong and skipping playback unexpectedly.

    # ============================================================
    # Internal playback mechanics
    # ============================================================

    def _play_queue_index(self, index: int) -> None:
        if not (0 <= index < len(self._queue)):
            self.stop()
            return
        self._queue_index = index
        self._persist_queue()
        path = self._queue[index]
        self._set_active_source(path)
        self._active.play()
        self._save_timer.start()
        self.track_changed.emit(path)
        self._preload_standby()

    def _set_active_source(self, path: Optional[str]) -> None:
        self._handoff_armed = False
        if path is None:
            self._active.setSource(QUrl())
            return
        self._load_into(self._active, path)

    def _load_into(self, player: QMediaPlayer, path: str) -> None:
        player.setSource(QUrl.fromLocalFile(path))

    def _preload_standby(self) -> None:
        """Loads whatever track would play next into the standby player,
        muted, so the gapless handoff has zero load latency at the
        boundary. Recomputes the "next" track the same way _advance()
        would, without actually advancing anything.
        """
        next_index = self._compute_next_index(self._queue_index)
        if next_index is None:
            self._standby.setSource(QUrl())
            return
        next_path = self._queue[next_index]
        self._load_into(self._standby, next_path)
        self._standby.pause()  # loaded and primed, but not making sound (volume is 0)

    def _compute_next_index(self, from_index: int) -> Optional[int]:
        """Pure function: given the current queue index, what's the next
        index to play, accounting for shuffle/repeat? Returns None if
        playback should stop (repeat=off, at the end of a non-shuffled
        queue). Shared by _advance() (real navigation) and
        _preload_standby() (lookahead only) so they can never disagree
        about what "next" means.
        """
        if not self._queue:
            return None

        if self._repeat_mode == "one":
            return from_index

        if self._shuffle and self._shuffle_order:
            try:
                pos_in_shuffle = self._shuffle_order.index(from_index)
            except ValueError:
                pos_in_shuffle = -1
            next_pos = pos_in_shuffle + 1
            if next_pos < len(self._shuffle_order):
                return self._shuffle_order[next_pos]
            if self._repeat_mode == "all":
                return self._shuffle_order[0]
            return None

        next_index = from_index + 1
        if next_index < len(self._queue):
            return next_index
        if self._repeat_mode == "all":
            return 0
        return None

    def _compute_previous_index(self, from_index: int) -> Optional[int]:
        if not self._queue:
            return None
        if self._shuffle and self._shuffle_order:
            try:
                pos_in_shuffle = self._shuffle_order.index(from_index)
            except ValueError:
                return None
            prev_pos = pos_in_shuffle - 1
            if prev_pos >= 0:
                return self._shuffle_order[prev_pos]
            return None
        prev_index = from_index - 1
        if prev_index >= 0:
            return prev_index
        if self._repeat_mode == "all":
            return len(self._queue) - 1
        return None

    def _advance(self, direction: int, user_initiated: bool) -> None:
        if direction > 0:
            next_index = self._compute_next_index(self._queue_index)
        else:
            next_index = self._compute_previous_index(self._queue_index)

        if next_index is None:
            self.stop()
            return
        self._play_queue_index(next_index)

    def _perform_gapless_handoff(self) -> None:
        """Swaps standby -> active with no audible gap: unmute standby
        to the real volume, mute the old active, swap references, then
        kick off preloading the NEW standby's "next" track.
        """
        self._standby_output.setVolume(self._volume)
        self._active_output.setVolume(0.0)

        self._active, self._standby = self._standby, self._active
        self._active_output, self._standby_output = self._standby_output, self._active_output

        # Re-wire signals to whichever player is now active -- Qt
        # connections are per-instance, so the old active's connections
        # are harmless leftovers (it's now silent standby) and the new
        # active needs fresh ones.
        self._connect_active_signals()

        next_index = self._compute_next_index(self._queue_index)
        if next_index is not None:
            self._queue_index = next_index
            self._persist_queue()
            self.track_changed.emit(self._queue[next_index])
        self._handoff_armed = False
        self._preload_standby()

    def _connect_active_signals(self) -> None:
        # Disconnect-then-reconnect defensively -- safe even if called
        # multiple times, since a TypeError from disconnecting a signal
        # with no existing connections is caught and ignored.
        player = self._active
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
            signal.connect(slot)

    # ============================================================
    # QMediaPlayer signal handlers
    # ============================================================

    def _on_position_changed(self, position_ms: int) -> None:
        position_seconds = position_ms / 1000.0
        self.position_changed.emit(position_seconds, self._duration_seconds)

        if (
            not self._handoff_armed
            and self._duration_seconds > 0
            and position_seconds >= self._duration_seconds * GAPLESS_HANDOFF_FRACTION
        ):
            self._handoff_armed = True
            self._perform_gapless_handoff()

    def _on_duration_changed(self, duration_ms: int) -> None:
        self._duration_seconds = duration_ms / 1000.0

    def _on_media_status_changed(self, status) -> None:
        if status == QMediaPlayer.MediaStatus.LoadedMedia:
            # Restore a saved position once, right after the track that
            # was active at last shutdown finishes loading.
            if self._pending_restore_position > 0:
                self._active.setPosition(int(self._pending_restore_position * 1000))
                self._pending_restore_position = 0.0
        elif status == QMediaPlayer.MediaStatus.EndOfMedia:
            # Fallback for tracks too short for the 95% handoff timer to
            # have fired yet (e.g. very short tracks), or if gapless
            # handoff didn't trigger for any reason -- still advance.
            if not self._handoff_armed:
                self._advance(direction=1, user_initiated=False)

    def _on_playback_state_changed(self, state) -> None:
        mapping = {
            QMediaPlayer.PlaybackState.PlayingState: "playing",
            QMediaPlayer.PlaybackState.PausedState: "paused",
            QMediaPlayer.PlaybackState.StoppedState: "stopped",
        }
        self.playback_state_changed.emit(mapping.get(state, "stopped"))

    def _on_error(self, error, error_string: str) -> None:
        path = self.get_current_track_path() or ""
        self.error_occurred.emit(path, error_string)

    # ============================================================
    # Persistence
    # ============================================================

    def _persist_position(self) -> None:
        """Called on the ~1s timer AND on every pause/stop, so the saved
        position is never more than ~1s stale even across a crash, and
        is exact on a clean pause/stop. This writes through LibraryCache's
        existing atomic save() -- at a 1s cadence that's a real, if
        small, amount of disk I/O during playback. Acceptable for a
        local single-user JSON cache at this scale; if this ever needs
        to scale to much more frequent writes, the fix is debouncing the
        actual disk write (e.g. write every Nth tick) while still
        updating the in-memory PlayerState every tick -- not changing
        what gets persisted.
        """
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
        return self._active.playbackState() == QMediaPlayer.PlaybackState.PlayingState

    def get_position_seconds(self) -> float:
        return self._active.position() / 1000.0

    def get_duration_seconds(self) -> float:
        return self._duration_seconds
