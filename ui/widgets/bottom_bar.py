"""
The bottom bar: always visible across every screen, per spec. Shows
currently-playing track info on the left and transport controls on the
right.

Step 3: transport buttons are now wired to a real PlaybackEngine by
MainWindow. This widget itself stays engine-agnostic (it only emits
signals and exposes setters) -- MainWindow owns the connection between
"the user clicked play" and "the engine actually plays something",
which keeps this widget reusable/testable without a real engine
instance.
"""

from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import QWidget, QHBoxLayout, QVBoxLayout, QLabel, QPushButton, QFrame, QProgressBar
from PyQt6.QtGui import QPixmap

from core.models import Track


class BottomBar(QFrame):
    play_pause_clicked = pyqtSignal()
    next_clicked = pyqtSignal()
    previous_clicked = pyqtSignal()
    bar_clicked = pyqtSignal()  # clicking the track info area -> go to Player Screen

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

        self.prev_button.clicked.connect(self.previous_clicked.emit)
        self.play_pause_button.clicked.connect(self.play_pause_clicked.emit)
        self.next_button.clicked.connect(self.next_clicked.emit)

        self._current_track: Track | None = None
        self._is_playing = False

        # Thin progress indicator along the very top edge of the bar.
        # A full click-to-seek progress bar is the Player Screen's job
        # (Step 4, per spec); this is just a glanceable "how far in am
        # I" indicator that requires no interaction.
        self.progress_bar = QProgressBar(self)
        self.progress_bar.setObjectName("bottomBarProgress")
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setFixedHeight(3)
        self.progress_bar.setMinimum(0)
        self.progress_bar.setMaximum(1000)
        self.progress_bar.setValue(0)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        # Pin the thin progress strip to the top edge, full width.
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
            # Album art rendering from embedded tags arrives in Step 4
            # (Player Screen) where we build the shared art-loading path;
            # showing the placeholder note here rather than silently
            # leaving a blank square.
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
        # Clicking the bar (but not directly on a transport button)
        # should navigate to the Player Screen -- wired fully once that
        # screen exists in Step 4.
        super().mousePressEvent(event)
        self.bar_clicked.emit()
