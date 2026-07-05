"""
BottomBar: always-visible mini-player bar at the bottom of MainWindow.
"""

from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal, QTimer
from PyQt6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QLabel, QPushButton,
    QFrame, QSizePolicy, QSlider, QMenu,
)
from PyQt6.QtGui import QPixmap, QAction
from ui.widgets.clickable_label import ClickableLabel
from ui.widgets.seek_bar import SeekBar
from ui.svg_icon import svg_icon

from core.models import Track

_ICON_SIZE = 20   # transport button icon size in the mini-bar (slightly smaller than player screen)


class BottomBar(QFrame):
    play_pause_clicked = pyqtSignal()
    next_clicked = pyqtSignal()
    previous_clicked = pyqtSignal()

    # Clicked anywhere on the bar EXCEPT transport buttons and right controls → open Player Screen
    bar_clicked = pyqtSignal()

    # Sub-navigation from the track-info area
    title_clicked = pyqtSignal()    # → album page stub
    artist_clicked = pyqtSignal(str)   # → artist page stub

    # Press-and-hold seek signals (wired to engine in MainWindow)
    next_hold_started = pyqtSignal()
    next_hold_stopped = pyqtSignal()
    prev_hold_started = pyqtSignal()
    prev_hold_stopped = pyqtSignal()

    # New signals for bottom bar controls
    shuffle_clicked = pyqtSignal()
    repeat_clicked = pyqtSignal()
    lyric_clicked = pyqtSignal()
    queue_clicked = pyqtSignal()
    output_device_selected = pyqtSignal(object)
    volume_changed = pyqtSignal(float)

    seek_requested = pyqtSignal(float)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("bottomBar")
        self.setFixedHeight(92)  # Spacious height for center buttons + seek bar

        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(16, 8, 16, 8)
        main_layout.setSpacing(12)

        # Left: art thumbnail (بزرگ‌تر شدن سایز کاور آلبوم به 64)
        self.art_label = QLabel()
        self.art_label.setObjectName("bottomBarArt")
        self.art_label.setFixedSize(64, 64)
        self.art_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.art_label.setText("♪")
        main_layout.addWidget(self.art_label)

        # Track info (تغییر به QVBoxLayout برای زیر هم قرار گرفتن، اما با فاصله صفر)
        text_layout = QVBoxLayout()
        text_layout.setSpacing(0)  # حذف کامل فاصله عمودی بین تایتل و آرتیست
        text_layout.setContentsMargins(0, 0, 0, 0)
        text_layout.setAlignment(Qt.AlignmentFlag.AlignVCenter) # قرارگیری کل پکیج متنی در مرکز عمودی

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

        main_layout.addLayout(text_layout)
        main_layout.addStretch()  # Perfectly balances and centers the middle widget

        # --- Center container (controls + seek bar) ---
        self.center_widget = QWidget(self)
        self.center_widget.setFixedWidth(400)
        center_layout = QVBoxLayout(self.center_widget)
        center_layout.setContentsMargins(0, 0, 0, 0)
        center_layout.setSpacing(4)  # Smart distance between buttons and progress bar

        # Transport controls row
        self.transport_layout = QHBoxLayout()
        self.transport_layout.setSpacing(8)
        self.transport_layout.setContentsMargins(0, 0, 0, 0)
        self.transport_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.shuffle_button = self._icon_btn("shuffle", size=_ICON_SIZE)
        self.shuffle_button.setCheckable(True)
        self.shuffle_button.clicked.connect(self._on_shuffle_clicked)
        self.transport_layout.addWidget(self.shuffle_button)

        self.prev_button = self._icon_btn("prev", size=_ICON_SIZE)
        self.prev_button.setProperty("transport", True)
        self.transport_layout.addWidget(self.prev_button)

        self.play_pause_button = self._icon_btn("play", size=_ICON_SIZE + 4)
        self.play_pause_button.setProperty("transport", True)
        self.play_pause_button.clicked.connect(self.play_pause_clicked.emit)
        self.transport_layout.addWidget(self.play_pause_button)

        self.next_button = self._icon_btn("next", size=_ICON_SIZE)
        self.next_button.setProperty("transport", True)
        self.transport_layout.addWidget(self.next_button)

        self.repeat_button = self._icon_btn("repeat", size=_ICON_SIZE)
        self.repeat_button.clicked.connect(self._on_repeat_clicked)
        self.transport_layout.addWidget(self.repeat_button)

        center_layout.addLayout(self.transport_layout)

        # Interactive Seek Bar underneath transport controls
        self.seek_bar = SeekBar(self)
        self.seek_bar.seek_requested.connect(self.seek_requested.emit)
        center_layout.addWidget(self.seek_bar)

        main_layout.addWidget(self.center_widget)
        main_layout.addStretch()  # Perfectly balances and centers the middle widget

        # --- Right container (toggles + volume) ---
        self.right_widget = QWidget(self)
        self.right_widget.setFixedWidth(280)
        right_main_layout = QHBoxLayout(self.right_widget)
        right_main_layout.setContentsMargins(0, 0, 0, 0)
        right_main_layout.setSpacing(0)

        self.right_layout = QVBoxLayout()
        self.right_layout.setSpacing(4)
        self.right_layout.setContentsMargins(0, 0, 0, 0)
        self.right_layout.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

        # Row 1: lyric, heart, queue, device (headphone)
        self.right_buttons_layout = QHBoxLayout()
        self.right_buttons_layout.setSpacing(8)
        self.right_buttons_layout.setAlignment(Qt.AlignmentFlag.AlignRight)

        self._lyrics_btn = self._icon_btn("lyric", size=_ICON_SIZE)
        self._lyrics_btn.clicked.connect(self._on_lyrics_clicked)
        self.right_buttons_layout.addWidget(self._lyrics_btn)

        self._heart_btn = self._icon_btn("heart", size=_ICON_SIZE)
        self._heart_btn.setCheckable(True)
        self._heart_btn.clicked.connect(self._on_heart_clicked)
        self.right_buttons_layout.addWidget(self._heart_btn)

        self._queue_btn = self._icon_btn("queue", size=_ICON_SIZE)
        self._queue_btn.setCheckable(True)
        self._queue_btn.clicked.connect(self._on_queue_clicked)
        self.right_buttons_layout.addWidget(self._queue_btn)

        self._headphone_btn = self._icon_btn("headphone", size=_ICON_SIZE)
        self._headphone_btn.clicked.connect(self._on_headphone_clicked)
        self.right_buttons_layout.addWidget(self._headphone_btn)

        self.right_layout.addLayout(self.right_buttons_layout)

        # Row 2: volume controller (volume slider + mute button)
        self.volume_layout = QHBoxLayout()
        self.volume_layout.setSpacing(6)
        self.volume_layout.setAlignment(Qt.AlignmentFlag.AlignRight)

        self._volume_slider = QSlider(Qt.Orientation.Horizontal)
        self._volume_slider.setObjectName("volumeSlider")
        self._volume_slider.setStyleSheet("background: transparent; border: none;")  # Transparent background
        self._volume_slider.setMinimum(0)
        self._volume_slider.setMaximum(100)
        self._volume_slider.setFixedWidth(100)
        self._volume_slider.setValue(50)
        self._volume_slider.valueChanged.connect(self._on_volume_slider_changed)
        self.volume_layout.addWidget(self._volume_slider)

        self._mute_btn = self._icon_btn("Speaker_Icon", size=_ICON_SIZE)
        self._mute_btn.clicked.connect(self._on_mute_clicked)
        self.volume_layout.addWidget(self._mute_btn)

        self.right_layout.addLayout(self.volume_layout)
        right_main_layout.addLayout(self.right_layout)

        main_layout.addWidget(self.right_widget)

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

        # --- Internal state ---
        self._theme: dict = {}
        self._current_track: Track | None = None
        self._is_playing = False
        self._shuffle_on = False
        self._repeat_mode = "off"
        self._volume = 0.5
        self._muted = False
        self._prev_volume = 0.5
        self._devices: list[object] = []
        self._current_device: object | None = None
        self._queue_active = False

    def _icon_btn(self, asset: str, size: int = _ICON_SIZE) -> QPushButton:
        btn = QPushButton()
        btn.setObjectName("iconButton")
        btn.setFixedSize(size + 16, size + 16)
        btn.setFlat(True)
        return btn

    def apply_theme(self, theme: dict) -> None:
        """Re-render transport button SVG icons for the given theme."""
        self._theme = theme
        text_primary = theme.get("text_primary", "#EDEFF2")
        text_secondary = theme.get("text_secondary", "#9AA0AC")
        
        self.prev_button.setIcon(svg_icon("prev", text_primary, _ICON_SIZE))
        asset = "pause" if self._is_playing else "play"
        self.play_pause_button.setIcon(svg_icon(asset, text_primary, _ICON_SIZE + 4))
        self.next_button.setIcon(svg_icon("next", text_primary, _ICON_SIZE))

        heart_color = "#E05C5C" if self._heart_btn.isChecked() else text_secondary
        self._heart_btn.setIcon(svg_icon("heart", heart_color, _ICON_SIZE, filled=self._heart_btn.isChecked()))

        self._refresh_mode_icons()
        self._update_toggle_styles()
        self._headphone_btn.setIcon(svg_icon("headphone", text_secondary, _ICON_SIZE))
        self._update_volume_icon()

        accent = theme.get("accent", "#6C5CE7")
        groove_bg = theme.get("border", "#2E323C")
        self.seek_bar.set_colors(accent, groove_bg, "#FFFFFF", text_secondary)

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

    def _on_shuffle_clicked(self) -> None:
        self.shuffle_clicked.emit()

    def _on_repeat_clicked(self) -> None:
        self.repeat_clicked.emit()

    def _on_lyrics_clicked(self) -> None:
        self.lyric_clicked.emit()

    def _on_heart_clicked(self) -> None:
        active = self._heart_btn.isChecked()
        if self._theme:
            color = "#E05C5C" if active else self._theme.get("text_secondary", "#9AA0AC")
            self._heart_btn.setIcon(svg_icon("heart", color, _ICON_SIZE, filled=active))

    def _on_queue_clicked(self) -> None:
        self.queue_clicked.emit()

    def _on_headphone_clicked(self) -> None:
        if not self._devices:
            return

        menu = QMenu(self)
        if self._theme:
            bg = self._theme.get("surface", "#1C1F26")
            text = self._theme.get("text_primary", "#EDEFF2")
            border = self._theme.get("border", "#2E323C")
            accent = self._theme.get("accent", "#6C5CE7")
            menu.setStyleSheet(f"""
                QMenu {{
                    background-color: {bg};
                    color: {text};
                    border: 1px solid {border};
                    border-radius: 8px;
                    padding: 4px;
                }}
                QMenu::item {{
                    padding: 6px 12px;
                    border-radius: 4px;
                }}
                QMenu::item:selected {{
                    background-color: {accent};
                    color: {text};
                }}
            """)

        for device in self._devices:
            desc = device.description()
            if device.isDefault():
                desc += " (default)"

            action = QAction(desc, menu)
            if self._current_device and bytes(device.id()) == bytes(self._current_device.id()):
                action.setCheckable(True)
                action.setChecked(True)

            action.triggered.connect(lambda checked, d=device: self.output_device_selected.emit(d))
            menu.addAction(action)

        menu.exec(self._headphone_btn.mapToGlobal(self._headphone_btn.rect().bottomLeft()))

    def _on_volume_slider_changed(self, value: int) -> None:
        vol = value / 100.0
        self._volume = vol
        if vol > 0.0:
            self._muted = False
            self._prev_volume = vol
        self._update_volume_icon()
        self.volume_changed.emit(vol)

    def _on_mute_clicked(self) -> None:
        if self._volume > 0.0:
            self._muted = True
            self._prev_volume = self._volume
            self.volume_changed.emit(0.0)
        else:
            self._muted = False
            target_vol = self._prev_volume if self._prev_volume > 0.0 else 0.5
            self.volume_changed.emit(target_vol)

    def _update_volume_icon(self) -> None:
        if not self._theme:
            return
        text_primary = self._theme.get("text_primary", "#EDEFF2")
        if self._volume == 0.0 or self._muted:
            self._mute_btn.setIcon(svg_icon("Mute", text_primary, _ICON_SIZE))
        else:
            self._mute_btn.setIcon(svg_icon("Speaker_Icon", text_primary, _ICON_SIZE))

    def _refresh_mode_icons(self) -> None:
        if not self._theme:
            return
        accent = self._theme.get("accent", "#6C5CE7")
        secondary = self._theme.get("text_secondary", "#9AA0AC")

        sh_color = accent if self._shuffle_on else secondary
        self.shuffle_button.setIcon(
            svg_icon("shuffle", sh_color, _ICON_SIZE, slash=not self._shuffle_on)
        )

        if self._repeat_mode == "off":
            self.repeat_button.setIcon(svg_icon("repeat", secondary, _ICON_SIZE, slash=True))
        elif self._repeat_mode == "all":
            self.repeat_button.setIcon(svg_icon("repeat", accent, _ICON_SIZE))
        else:  # "one"
            self.repeat_button.setIcon(svg_icon("repeat", accent, _ICON_SIZE, repeat_one=True))

    def _update_toggle_styles(self) -> None:
        if not self._theme:
            return
        secondary = self._theme.get("text_secondary", "#9AA0AC")
        accent = self._theme.get("accent", "#6C5CE7")

        self._lyrics_btn.setIcon(svg_icon("lyric", secondary, _ICON_SIZE))
        q_color = accent if self._queue_active else secondary
        self._queue_btn.setIcon(svg_icon("queue", q_color, _ICON_SIZE))

    def mousePressEvent(self, event) -> None:
        super().mousePressEvent(event)
        self.bar_clicked.emit()

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
            self.seek_bar.set_position(0.0, 0.0)
        else:
            self.title_label.setText(track.title)
            self._populate_artists(track.artists)
            self.art_label.setText("♪")

    def set_art(self, pixmap: "QPixmap | None") -> None:
        """Set the album art thumbnail."""
        if pixmap and not pixmap.isNull():
            # حفظ سایز جدید کاور (64x64)
            scaled = pixmap.scaled(
                64, 64,
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
        asset = "pause" if is_playing else "play"
        color = "#EDEFF2"
        if self._theme:
            color = self._theme.get("text_primary", "#EDEFF2")
        self.play_pause_button.setIcon(svg_icon(asset, color, _ICON_SIZE + 4))

    def set_position(self, position_seconds: float, duration_seconds: float) -> None:
        self.seek_bar.set_position(position_seconds, duration_seconds)

    def set_shuffle(self, enabled: bool) -> None:
        self._shuffle_on = enabled
        self.shuffle_button.setChecked(enabled)
        self._refresh_mode_icons()

    def set_repeat_mode(self, mode: str) -> None:
        self._repeat_mode = mode
        self._refresh_mode_icons()

    def set_volume(self, volume: float) -> None:
        self._volume = volume
        if volume > 0.0:
            self._prev_volume = volume
            self._muted = False
        else:
            self._muted = True

        self._volume_slider.blockSignals(True)
        self._volume_slider.setValue(int(round(volume * 100)))
        self._volume_slider.blockSignals(False)
        self._update_volume_icon()

    def set_queue_active(self, active: bool) -> None:
        self._queue_active = active
        self._queue_btn.setChecked(active)
        self._update_toggle_styles()

    def set_available_devices(self, devices: list[object], current: object | None) -> None:
        self._devices = list(devices)
        self._current_device = current