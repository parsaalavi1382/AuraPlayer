"""
BottomBar: always-visible mini-player bar at the bottom of MainWindow.

Step 3+4 update:
- Emoji transport buttons replaced with SVG icons via ui.svg_icon.
- Click-zone discrimination:
    • Clicking the track TITLE label → title_clicked signal (→ Album page stub)
    • Clicking the ARTIST label → artist_clicked signal (→ Artist page stub)
    • Clicking anywhere ELSE on the bar (except the transport buttons
      themselves) → bar_clicked signal (→ opens Player Screen)
  Transport buttons (prev / play-pause / next) consume their own mouse
  events and do NOT bubble up to bar_clicked.
- Press-and-hold seek wiring (Next/Prev held → engine seek) is unchanged
  from Step 3; only the icon rendering changed.
"""

from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal, QTimer
from PyQt6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QLabel, QPushButton,
    QFrame, QProgressBar, QSizePolicy,
)
from PyQt6.QtGui import QPixmap
from ui.widgets.clickable_label import ClickableLabel

from core.models import Track

_ICON_SIZE = 20   # transport button icon size in the mini-bar (slightly smaller than player screen)


class BottomBar(QFrame):
    play_pause_clicked = pyqtSignal()
    next_clicked = pyqtSignal()
    previous_clicked = pyqtSignal()

    # Clicked anywhere on the bar EXCEPT transport buttons → open Player Screen
    bar_clicked = pyqtSignal()

    # Sub-navigation from the track-info area
    title_clicked = pyqtSignal()    # → album page stub
    artist_clicked = pyqtSignal(str)   # → artist page stub

    # Press-and-hold seek signals (wired to engine in MainWindow)
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

        # --- Left: art thumbnail ---
        self.art_label = QLabel()
        self.art_label.setObjectName("bottomBarArt")
        self.art_label.setFixedSize(48, 48)
        self.art_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.art_label.setText("♪")
        layout.addWidget(self.art_label)

        # --- Track info (title + artist, each a clickable label) ---
        text_layout = QVBoxLayout()
        text_layout.setSpacing(2)
        text_layout.setContentsMargins(0, 0, 0, 0)

        self.title_label = ClickableLabel("No track playing", self)
        self.title_label.setObjectName("bottomBarTitle")
        self.title_label.clicked.connect(self.title_clicked.emit)
        text_layout.addWidget(self.title_label)

        self.artist_container = QWidget(self)
        self.artist_container.setObjectName("bottomBarArtistContainer")
        self.artist_layout = QHBoxLayout(self.artist_container)
        self.artist_layout.setContentsMargins(0, 0, 0, 0)
        self.artist_layout.setSpacing(0)
        text_layout.addWidget(self.artist_container)

        layout.addLayout(text_layout)
        layout.addStretch()

        # --- Right: transport controls ---
        # Each button is flagged so bar_clicked (mousePressEvent on the
        # bar frame itself) is NOT triggered when these are pressed -- Qt
        # routes button press events directly to the button, so they do
        # not propagate to the parent frame's mousePressEvent naturally.
        # The explicit setObjectName("transportBtn") is used only as a
        # documentation marker; no special filtering needed.
        self.prev_button = QPushButton()
        self.prev_button.setObjectName("iconButton")
        self.prev_button.setFixedSize(36, 36)
        self.prev_button.setFlat(True)
        self.prev_button.setProperty("transport", True)

        self.play_pause_button = QPushButton()
        self.play_pause_button.setObjectName("iconButton")
        self.play_pause_button.setFixedSize(36, 36)
        self.play_pause_button.setFlat(True)
        self.play_pause_button.setProperty("transport", True)

        self.next_button = QPushButton()
        self.next_button.setObjectName("iconButton")
        self.next_button.setFixedSize(36, 36)
        self.next_button.setFlat(True)
        self.next_button.setProperty("transport", True)

        for btn in (self.prev_button, self.play_pause_button, self.next_button):
            layout.addWidget(btn)

        self.play_pause_button.clicked.connect(self.play_pause_clicked.emit)

        # --- Press-and-hold timers ---
        self._next_hold_timer = QTimer(self)
        self._next_hold_timer.setSingleShot(True)
        self._next_hold_timer.timeout.connect(self._on_next_hold_timeout)
        self._next_is_holding = False

        self.next_button.pressed.connect(self._on_next_pressed)
        self.next_button.released.connect(self._on_next_released)

        self._prev_hold_timer = QTimer(self)
        self._prev_hold_timer.setSingleShot(True)
        self._prev_hold_timer.timeout.connect(self._on_prev_hold_timeout)
        self._prev_is_holding = False

        self.prev_button.pressed.connect(self._on_prev_pressed)
        self.prev_button.released.connect(self._on_prev_released)

        self._current_track: Track | None = None
        self._is_playing = False

        # --- Thin progress strip along the very top edge ---
        self.progress_bar = QProgressBar(self)
        self.progress_bar.setObjectName("bottomBarProgress")
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setFixedHeight(3)
        self.progress_bar.setMinimum(0)
        self.progress_bar.setMaximum(1000)
        self.progress_bar.setValue(0)

    # ------------------------------------------------------------------
    # SVG icon theming — called by MainWindow._apply_theme()
    # ------------------------------------------------------------------

    def apply_theme(self, theme: dict) -> None:
        """Re-render transport button SVG icons for the given theme."""
        from ui.svg_icon import svg_icon
        text_primary = theme.get("text_primary", "#EDEFF2")
        asset = "pause" if self._is_playing else "play"
        self.prev_button.setIcon(svg_icon("prev", text_primary, _ICON_SIZE))
        self.play_pause_button.setIcon(svg_icon(asset, text_primary, _ICON_SIZE))
        self.next_button.setIcon(svg_icon("next", text_primary, _ICON_SIZE))

    # ------------------------------------------------------------------
    # Hold-seek mechanics
    # ------------------------------------------------------------------

    def _on_next_pressed(self) -> None:
        self._next_is_holding = False
        self._next_hold_timer.start(400)

    def _on_next_hold_timeout(self) -> None:
        self._next_is_holding = True
        self.next_hold_started.emit()

    def _on_next_released(self) -> None:
        self._next_hold_timer.stop()
        if self._next_is_holding:
            self._next_is_holding = False
            self.next_hold_stopped.emit()
        else:
            self.next_clicked.emit()

    def _on_prev_pressed(self) -> None:
        self._prev_is_holding = False
        self._prev_hold_timer.start(400)

    def _on_prev_hold_timeout(self) -> None:
        self._prev_is_holding = True
        self.prev_hold_started.emit()

    def _on_prev_released(self) -> None:
        self._prev_hold_timer.stop()
        if self._prev_is_holding:
            self._prev_is_holding = False
            self.prev_hold_stopped.emit()
        else:
            self.previous_clicked.emit()

    # ------------------------------------------------------------------
    # Click-zone handlers
    # ------------------------------------------------------------------

    def mousePressEvent(self, event) -> None:
        """Any click on the bar frame itself (not a child widget that
        consumed the event) → open the Player Screen.

        Because Qt child widgets (labels, buttons) consume their own
        press events and do not propagate to the parent frame, the title
        and artist labels' dedicated handlers above fire for those zones,
        and the transport buttons fire their own clicked/pressed signals.
        This handler therefore fires cleanly only for the remaining
        clickable areas: album art, empty space, progress strip edge.
        """
        super().mousePressEvent(event)
        self.bar_clicked.emit()

    # ------------------------------------------------------------------
    # Resize: keep the progress strip pinned to the very top edge
    # ------------------------------------------------------------------

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self.progress_bar.setGeometry(0, 0, self.width(), 3)

    # ------------------------------------------------------------------
    # State setters called by MainWindow
    # ------------------------------------------------------------------

    def _clear_artist_layout(self) -> None:
        while self.artist_layout.count() > 0:
            item = self.artist_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

    def _populate_artists(self, artists: list[str]) -> None:
        self._clear_artist_layout()
        if not artists:
            return
        for i, artist in enumerate(artists):
            lbl = ClickableLabel(artist, self)
            lbl.setObjectName("bottomBarArtist")
            lbl.clicked.connect(lambda a=artist: self.artist_clicked.emit(a))
            self.artist_layout.addWidget(lbl)
            
            if i < len(artists) - 1:
                comma = QLabel(", ", self)
                comma.setObjectName("bottomBarArtist")
                self.artist_layout.addWidget(comma)
        self.artist_layout.addStretch()

    def set_current_track(self, track: Track | None) -> None:
        self._current_track = track
        if track is None:
            self.title_label.setText("No track playing")
            self._clear_artist_layout()
            self.art_label.setPixmap(QPixmap())
            self.art_label.setText("♪")
            self.progress_bar.setValue(0)
        else:
            self.title_label.setText(track.title)
            self._populate_artists(track.artists)
            self.art_label.setText("♪")   # art pixmap set separately via set_art()

    def set_art(self, pixmap: "QPixmap | None") -> None:
        """Set the album art thumbnail. Called from MainWindow when
        get_album_art() resolves for the current track.
        """
        if pixmap and not pixmap.isNull():
            scaled = pixmap.scaled(
                48, 48,
                Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                Qt.TransformationMode.SmoothTransformation,
            )
            self.art_label.setPixmap(scaled)
            self.art_label.setText("")
        else:
            self.art_label.setPixmap(QPixmap())
            self.art_label.setText("♪")

    def set_playing(self, is_playing: bool) -> None:
        self._is_playing = is_playing
        from ui.svg_icon import svg_icon
        # Determine current icon color from the last known theme if available,
        # otherwise fall back to a sensible default.
        color = "#EDEFF2"
        asset = "pause" if is_playing else "play"
        self.play_pause_button.setIcon(svg_icon(asset, color, _ICON_SIZE))

    def set_position(self, position_seconds: float, duration_seconds: float) -> None:
        if duration_seconds <= 0:
            self.progress_bar.setValue(0)
            return
        fraction = max(0.0, min(1.0, position_seconds / duration_seconds))
        self.progress_bar.setValue(int(fraction * 1000))
