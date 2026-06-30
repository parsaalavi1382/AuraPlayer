"""
The bottom bar: always visible across every screen, per spec. Shows
currently-playing track info on the left and transport controls on the
right.

Step 3/4: Transport buttons handle both single clicks (skip track) and
long-press gestures (continuous seeking via QTimer).
"""

from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal, QTimer
from PyQt6.QtWidgets import QWidget, QHBoxLayout, QVBoxLayout, QLabel, QPushButton, QFrame, QProgressBar
from PyQt6.QtGui import QPixmap

from core.models import Track


class BottomBar(QFrame):
    play_pause_clicked = pyqtSignal()
    next_clicked = pyqtSignal()
    previous_clicked = pyqtSignal()
    bar_clicked = pyqtSignal()

    # Signals for continuous seek communication
    next_hold_started = pyqtSignal()
    next_hold_stopped = pyqtSignal()
    prev_hold_started = pyqtSignal()
    prev_hold_stopped = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("bottomBar")
        self.setFixedHeight(64)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 8, 16, 8)
        layout.setSpacing(12)

        # --- Left: art + title + artist ---
        self.art_label = QLabel()
        self.art_label.setObjectName("bottomBarArt")
        self.art_label.setFixedSize(48, 48)
        self.art_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.art_label.setText("♪")
        layout.addWidget(self.art_label)

        text_layout = QVBoxLayout()
        text_layout.setSpacing(2)
        self.title_label = QLabel("No track playing")
        self.title_label.setStyleSheet("font-weight: 600;")
        self.artist_label = QLabel("")
        self.artist_label.setObjectName("bottomBarArtist")
        text_layout.addWidget(self.title_label)
        text_layout.addWidget(self.artist_label)
        layout.addLayout(text_layout)
        layout.addStretch()

        # --- Right: transport controls ---
        self.prev_button = QPushButton("⏮")
        self.play_pause_button = QPushButton("▶")
        self.next_button = QPushButton("⏭")
        for btn in (self.prev_button, self.play_pause_button, self.next_button):
            btn.setObjectName("iconButton")
            btn.setFixedSize(36, 36)
            layout.addWidget(btn)

        self.play_pause_button.clicked.connect(self.play_pause_clicked.emit)

        # Next button hold mechanics
        self.next_hold_timer = QTimer(self)
        self.next_hold_timer.setSingleShot(True)
        self.next_hold_timer.timeout.connect(self._on_next_hold_timeout)
        self._next_is_holding = False

        self.next_button.pressed.connect(self._on_next_pressed)
        self.next_button.released.connect(self._on_next_released)

        # Previous button hold mechanics
        self.prev_hold_timer = QTimer(self)
        self.prev_hold_timer.setSingleShot(True)
        self.prev_hold_timer.timeout.connect(self._on_prev_hold_timeout)
        self._prev_is_holding = False

        self.prev_button.pressed.connect(self._on_prev_pressed)
        self.prev_button.released.connect(self._on_prev_released)

        self._current_track: Track | None = None
        self._is_playing = False

        # Thin progress indicator along the very top edge of the bar
        self.progress_bar = QProgressBar(self)
        self.progress_bar.setObjectName("bottomBarProgress")
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setFixedHeight(3)
        self.progress_bar.setMinimum(0)
        self.progress_bar.setMaximum(1000)
        self.progress_bar.setValue(0)

    def _on_next_pressed(self) -> None:
        self._next_is_holding = False
        self.next_hold_timer.start(400)

    def _on_next_hold_timeout(self) -> None:
        self._next_is_holding = True
        self.next_hold_started.emit()

    def _on_next_released(self) -> None:
        self.next_hold_timer.stop()
        if self._next_is_holding:
            self._next_is_holding = False
            self.next_hold_stopped.emit()
        else:
            self.next_clicked.emit()

    def _on_prev_pressed(self) -> None:
        self._prev_is_holding = False
        self.prev_hold_timer.start(400)

    def _on_prev_hold_timeout(self) -> None:
        self._prev_is_holding = True
        self.prev_hold_started.emit()

    def _on_prev_released(self) -> None:
        self.prev_hold_timer.stop()
        if self._prev_is_holding:
            self._prev_is_holding = False
            self.prev_hold_stopped.emit()
        else:
            self.previous_clicked.emit()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self.progress_bar.setGeometry(0, 0, self.width(), 3)

    def set_current_track(self, track: Track | None) -> None:
        self._current_track = track
        if track is None:
            self.title_label.setText("No track playing")
            self.artist_label.setText("")
            self.art_label.setPixmap(QPixmap())
            self.art_label.setText("♪")
            self.progress_bar.setValue(0)
        else:
            self.title_label.setText(track.title)
            self.artist_label.setText(", ".join(track.artists))
            self.art_label.setText("♪")

    def set_playing(self, is_playing: bool) -> None:
        self._is_playing = is_playing
        self.play_pause_button.setText("⏸" if is_playing else "▶")

    def set_position(self, position_seconds: float, duration_seconds: float) -> None:
        if duration_seconds <= 0:
            self.progress_bar.setValue(0)
            return
        fraction = max(0.0, min(1.0, position_seconds / duration_seconds))
        self.progress_bar.setValue(int(fraction * 1000))

    def mousePressEvent(self, event):
        super().mousePressEvent(event)
        self.bar_clicked.emit()