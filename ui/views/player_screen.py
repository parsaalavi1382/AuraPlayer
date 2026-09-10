"""
PlayerScreen: the full-screen player overlay that slides up from the
bottom bar when the user taps anywhere on the mini-player.

Layout (top to bottom):
  ┌─────────────────────────────────┐
  │  [←back]        [♥] [⋮]        │  top bar
  ├─────────────────────────────────┤
  │                                 │
  │         [album art / lyrics]    │  center content area
  │         (art fades → lyrics)    │
  │                                 │
  ├─────────────────────────────────┤
  │  Track Title                    │  track info
  │  Artist Name                    │
  ├─────────────────────────────────┤
  │  ←──────────────────────────→   │  seek bar
  ├─────────────────────────────────┤
  │     ⏮  ⏪  ▶/⏸  ⏩  ⏭          │  transport controls
  ├─────────────────────────────────┤
  │     [🎵lyrics] [queue]          │  panel toggles
  └─────────────────────────────────┘

Queue panel slides in from the right over the center area when active,
pushing art/lyrics to the left. This is implemented as a horizontal
QStackedWidget-like split: a QSplitter with zero user-resize (fixed
proportions via QPropertyAnimation on the right panel width).

The widget is a child of MainWindow, positioned to exactly cover the
central widget. Slide-up is driven by a QPropertyAnimation on the
widget's y-position (from main_window.height() down to 0).

Minimum window constraint: MainWindow enforces 500×700 while this
widget is visible.
"""

from __future__ import annotations

import io
from PIL import Image, ImageFilter

from PyQt6.QtCore import (
    Qt, pyqtSignal, QPropertyAnimation, QEasingCurve,
    QRect, QSize, QBuffer, QIODevice, QRunnable, QObject, QThreadPool,
)
from PyQt6.QtGui import QPixmap, QColor, QFont, QAction, QPainter, QBrush, QPen
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QGraphicsOpacityEffect, QSizePolicy, QFrame, QSlider, QMenu,
)

from ui.svg_icon import svg_pixmap, svg_icon
from ui.widgets.seek_bar import SeekBar
from ui.widgets.clickable_label import ClickableLabel
from ui.widgets.queue_panel import QueuePanel
from ui.widgets.lyrics_panel import LyricsPanel
from ui.widgets.hover_bold_button import HoverBoldButton
from ui.widgets.lottie_icon_button import LottieIconButton
from utils.paths import get_resource_path
from ui.widgets.aspect_label import AspectLabel
import os

# Animation durations in ms
_SLIDE_MS = 320          # slide-up / slide-down
_FADE_MS = 220           # art ↔ lyrics / queue cross-fade
_ICON_SIZE = 24          # transport icon px
_ICON_SIZE_MAIN = 28     # play/pause icon px (slightly larger)
_ART_SIZE = 400          # album art square, px


def generate_blurred_background(art_pixmap: QPixmap, target_w: int, target_h: int, bg_color_hex: str = "#14161A") -> QPixmap | None:
    if not art_pixmap or art_pixmap.isNull():
        return None
    try:
        small_pix = art_pixmap.scaled(128, 128, Qt.AspectRatioMode.IgnoreAspectRatio, Qt.TransformationMode.SmoothTransformation)
        buf = QBuffer()
        buf.open(QIODevice.OpenModeFlag.ReadWrite)
        small_pix.save(buf, "PNG")
        raw_bytes = buf.data().data()
        if not raw_bytes:
            return None

        pil_img = Image.open(io.BytesIO(raw_bytes)).convert("RGBA")
        blurred_img = pil_img.filter(ImageFilter.GaussianBlur(radius=18)).resize((target_w, target_h), Image.Resampling.BILINEAR)

        out_buf = io.BytesIO()
        blurred_img.save(out_buf, format="PNG")
        out_pix = QPixmap()
        out_pix.loadFromData(out_buf.getvalue())

        if out_pix.isNull():
            return None

        # Apply theme-aware overlay
        painter = QPainter(out_pix)
        bg_qcolor = QColor(bg_color_hex)
        tint_color = QColor(bg_qcolor.red(), bg_qcolor.green(), bg_qcolor.blue(), 115)
        painter.setBrush(QBrush(tint_color))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRect(0, 0, target_w, target_h)
        painter.end()

        return out_pix
    except Exception:
        return None


class _BlurWorkerSignals(QObject):
    finished = pyqtSignal(int, object)  # (request_id, QPixmap)


class _BlurWorker(QRunnable):
    def __init__(self, request_id: int, art_pixmap: QPixmap, target_w: int, target_h: int, bg_color_hex: str):
        super().__init__()
        self.request_id = request_id
        self.art_pixmap = art_pixmap
        self.target_w = target_w
        self.target_h = target_h
        self.bg_color_hex = bg_color_hex
        self.signals = _BlurWorkerSignals()

    def run(self):
        pixmap = generate_blurred_background(self.art_pixmap, self.target_w, self.target_h, self.bg_color_hex)
        self.signals.finished.emit(self.request_id, pixmap)


class _PlaceholderPanel(QFrame):
    """Generic placeholder used for Lyrics and Queue panels until
    Step 8 implements real content. Shows a centered label with a
    step reference so the user knows it isn't a bug.
    """

    def __init__(self, text: str, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        label = QLabel(text)
        label.setObjectName("emptyStateSubtitle")
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        label.setWordWrap(True)
        layout.addWidget(label)


class PlayerScreen(QFrame):
    """Full-screen overlay player. Parented directly to MainWindow;
    call show_player() / hide_player() to animate in/out.

    Signals emitted upward to MainWindow for engine wiring:
    """

    # Transport
    play_pause_clicked = pyqtSignal()
    next_clicked = pyqtSignal()
    previous_clicked = pyqtSignal()
    next_hold_started = pyqtSignal()
    next_hold_stopped = pyqtSignal()
    prev_hold_started = pyqtSignal()
    prev_hold_stopped = pyqtSignal()
    seek_requested = pyqtSignal(float)   # seconds

    # Navigation
    back_clicked = pyqtSignal()
    title_clicked = pyqtSignal()         # → album page stub
    artist_clicked = pyqtSignal(str)        # → artist page stub

    # Mode toggles (engine wiring happens in MainWindow)
    shuffle_clicked = pyqtSignal()
    repeat_clicked = pyqtSignal()

    # Volume and output devices
    volume_changed = pyqtSignal(float)
    output_device_selected = pyqtSignal(object)
    favorite_toggled = pyqtSignal(str, bool)

    def __init__(self, parent: QWidget):
        super().__init__(parent)
        self.store = parent.store
        self.engine = parent.engine

        self.setObjectName("playerScreen")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setFrameShape(QFrame.Shape.NoFrame)
        # Covers the parent exactly; resizeEvent keeps this in sync.
        self.setGeometry(parent.rect())
        self.hide()

        # Internal state
        self._theme: dict = {}
        self._is_playing = False
        self._shuffle_on = False
        self._repeat_mode = "off"   # "off" | "all" | "one"
        self._lyrics_active = False
        self._queue_active = False
        self._duration = 0.0
        self._current_path: str | None = None
        self._art_pixmap: QPixmap | None = None
        self._has_custom_art = False
        self._last_art_pixmap: QPixmap | None = None
        self._blur_request_id = 0
        self._active_bg_layer = 1

        self._volume = 0.5
        self._muted = False
        self._prev_volume = 0.5
        self._devices: list[object] = []
        self._current_device: object | None = None
        self._is_default = True

        # Dual background labels for full-bleed blurred artwork crossfading
        self._bg_label_1 = AspectLabel(self)
        self._bg_label_1.setObjectName("playerBgLayer1")
        self._bg_label_1.setScaledContents(True)
        self._bg_label_1.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._bg_label_1.setGeometry(self.rect())
        self._bg_label_1.lower()

        self._bg_label_2 = AspectLabel(self)
        self._bg_label_2.setObjectName("playerBgLayer2")
        self._bg_label_2.setScaledContents(True)
        self._bg_label_2.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._bg_label_2.setGeometry(self.rect())
        self._bg_label_2.lower()

        self._bg_opacity_1 = QGraphicsOpacityEffect(self._bg_label_1)
        self._bg_label_1.setGraphicsEffect(self._bg_opacity_1)
        self._bg_opacity_1.setOpacity(0.0)

        self._bg_opacity_2 = QGraphicsOpacityEffect(self._bg_label_2)
        self._bg_label_2.setGraphicsEffect(self._bg_opacity_2)
        self._bg_opacity_2.setOpacity(0.0)

        self._bg_fade_1 = QPropertyAnimation(self._bg_opacity_1, b"opacity")
        self._bg_fade_1.setDuration(_FADE_MS)

        self._bg_fade_2 = QPropertyAnimation(self._bg_opacity_2, b"opacity")
        self._bg_fade_2.setDuration(_FADE_MS)

        self._build_ui()

        # Wire close signal for queue panel
        self._queue_panel.close_requested.connect(self._on_queue_close_requested)

        # Slide animation (y from parent.height() → 0 to open, reverse to close)
        self._slide_anim = QPropertyAnimation(self, b"geometry")
        self._slide_anim.setDuration(_SLIDE_MS)
        self._slide_anim.setEasingCurve(QEasingCurve.Type.OutCubic)

        # Lyrics opacity effect
        self._lyrics_opacity = QGraphicsOpacityEffect(self._lyrics_panel)
        self._lyrics_panel.setGraphicsEffect(self._lyrics_opacity)
        self._lyrics_opacity.setOpacity(0.0)

        self._lyrics_fade = QPropertyAnimation(self._lyrics_opacity, b"opacity")
        self._lyrics_fade.setDuration(_FADE_MS)

        # Art opacity effect
        self._art_opacity = QGraphicsOpacityEffect(self._art_container)
        self._art_container.setGraphicsEffect(self._art_opacity)
        self._art_opacity.setOpacity(1.0)

        self._art_fade = QPropertyAnimation(self._art_opacity, b"opacity")
        self._art_fade.setDuration(_FADE_MS)

        # Queue panel slide animation (width: 0 → panel_target_w)
        self._queue_anim = QPropertyAnimation(self._queue_panel, b"maximumWidth")
        self._queue_anim.setDuration(_FADE_MS)
        self._queue_anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._queue_anim.finished.connect(self._on_queue_anim_finished)

        self._art_shift_anim = QPropertyAnimation(self._content_area, b"maximumWidth")
        self._art_shift_anim.setDuration(_FADE_MS)
        self._art_shift_anim.setEasingCurve(QEasingCurve.Type.OutCubic)

        # Listen to resize events of _content_area to keep _lyrics_panel positioned correctly
        self._content_area.installEventFilter(self)

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── Top bar ──────────────────────────────────────────────────
        top_bar = QHBoxLayout()
        top_bar.setContentsMargins(16, 12, 16, 8)

        self._back_btn = self._icon_btn("back", size=_ICON_SIZE)
        self._back_btn.clicked.connect(self.back_clicked.emit)
        top_bar.addWidget(self._back_btn)
        top_bar.addStretch()

        # Art + lyrics stacked in the same space
        self._content_area = QWidget()
        content_layout = QVBoxLayout(self._content_area)
        content_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        content_layout.setContentsMargins(24, 8, 24, 8)

        # Art container
        self._art_container = QWidget()
        art_inner = QVBoxLayout(self._art_container)
        art_inner.setAlignment(Qt.AlignmentFlag.AlignCenter)
        art_inner.setContentsMargins(0, 0, 0, 0)

        self._art_label = AspectLabel()
        self._art_label.setFixedSize(_ART_SIZE, _ART_SIZE)
        self._art_label.setScaledContents(True)
        self._art_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._art_label.setObjectName("playerArt")
        art_inner.addWidget(self._art_label)
        content_layout.addWidget(self._art_container, alignment=Qt.AlignmentFlag.AlignCenter)

        # Lyrics panel (absolute-positioned over content area, initially invisible)
        self._lyrics_panel = LyricsPanel(
            self.store,
            self.engine,
            parent=self._content_area,
        )
        self._lyrics_panel.setGeometry(self._content_area.rect().adjusted(24, 12, -24, -12))

        # Queue panel (starts at width=0, slides in from the right)
        self._queue_panel = QueuePanel(
            self.store,
            self.engine,
        )
        self._queue_panel.setMinimumWidth(0)
        self._queue_panel.setMaximumWidth(0)

        # Left area groups the top bar and content area (art/lyrics)
        left_area = QVBoxLayout()
        left_area.setContentsMargins(0, 0, 0, 0)
        left_area.setSpacing(0)
        left_area.addLayout(top_bar)
        left_area.addWidget(self._content_area, stretch=1)

        # Top half groups left area and queue panel horizontally so queue panel spans full height
        top_half = QHBoxLayout()
        top_half.setContentsMargins(0, 0, 0, 0)
        top_half.setSpacing(0)
        top_half.addLayout(left_area, stretch=1)
        top_half.addWidget(self._queue_panel)

        root.addLayout(top_half, stretch=1)

        # ── Track info ────────────────────────────────────────────────
        info_area = QVBoxLayout()
        info_area.setContentsMargins(24, 8, 24, 4)
        info_area.setSpacing(2)

        self._title_label = ClickableLabel("No track", self)
        self._title_label.setObjectName("playerTitle")
        self._title_label.setFont(QFont("Segoe UI", 16, QFont.Weight.Bold))
        self._title_label.clicked.connect(self.title_clicked.emit)
        self._title_label.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._title_label.customContextMenuRequested.connect(self._show_title_context_menu)
        info_area.addWidget(self._title_label)

        self.artist_container = QWidget(self)
        self.artist_container.setObjectName("playerArtistContainer")
        self.artist_layout = QHBoxLayout(self.artist_container)
        self.artist_layout.setContentsMargins(0, 0, 0, 0)
        self.artist_layout.setSpacing(0)
        info_area.addWidget(self.artist_container)

        root.addLayout(info_area)

        # ── Seek bar ─────────────────────────────────────────────────
        seek_wrap = QHBoxLayout()
        seek_wrap.setContentsMargins(24, 4, 24, 4)
        self._seek_bar = SeekBar()
        self._seek_bar.seek_requested.connect(self.seek_requested.emit)
        seek_wrap.addWidget(self._seek_bar)
        root.addLayout(seek_wrap)

        # ── Transport controls ────────────────────────────────────────
        transport = QHBoxLayout()
        transport.setContentsMargins(16, 8, 16, 8)
        transport.setSpacing(8)
        transport.addStretch()

        shuffle_lottie_path = get_resource_path("assets", "lottie", "shuffle.json")
        self._shuffle_btn = LottieIconButton(shuffle_lottie_path, size=18)
        self._shuffle_btn.set_speed(2.5)
        self._shuffle_btn.setCheckable(True)
        self._shuffle_btn.clicked.connect(self._on_shuffle_clicked)
        transport.addWidget(self._shuffle_btn)

        self._prev_btn = self._icon_btn("prev", size=_ICON_SIZE)
        self._prev_btn.pressed.connect(self._on_prev_pressed)
        self._prev_btn.released.connect(self._on_prev_released)
        transport.addWidget(self._prev_btn)

        lottie_path = get_resource_path("assets", "lottie", "play_pause.json")
        
        # NOTE: Change the size here for ONLY the play/pause Lottie animation in the player screen (e.g. 28 to 36)
        lottie_size = 34
        
        self._play_pause_btn = LottieIconButton(lottie_path, size=lottie_size)
        
        # NOTE: Change the speed here for ONLY the play/pause Lottie animation in the player screen
        self._play_pause_btn.set_speed(2.5)
        
        self._play_pause_btn.clicked.connect(self.play_pause_clicked.emit)
        transport.addWidget(self._play_pause_btn)

        self._next_btn = self._icon_btn("next", size=_ICON_SIZE)
        self._next_btn.pressed.connect(self._on_next_pressed)
        self._next_btn.released.connect(self._on_next_released)
        transport.addWidget(self._next_btn)

        self._repeat_btn = LottieIconButton(get_resource_path("assets", "lottie", "repeat.json"), size=_ICON_SIZE)
        self._repeat_btn.set_speed(2.5)
        self._repeat_btn.clicked.connect(self._on_repeat_clicked)
        transport.addWidget(self._repeat_btn)

        transport.addStretch()

        root.addLayout(transport)

        # ── Panel toggles (Lyrics / Queue) + Volume Controls ──────────
        toggles = QHBoxLayout()
        toggles.setContentsMargins(24, 4, 24, 16)
        toggles.setSpacing(12)

        # Left spacer to center the central controls perfectly (mirrors right volume width: 110 + 12 + 40 = 162)
        left_spacer = QWidget()
        left_spacer.setFixedWidth(162)
        toggles.addWidget(left_spacer)

        toggles.addStretch()

        self._lyrics_btn = self._icon_btn("lyric", size=_ICON_SIZE)
        self._lyrics_btn.setCheckable(True)
        self._lyrics_btn.clicked.connect(self._on_lyrics_clicked)
        toggles.addWidget(self._lyrics_btn)

        heart_lottie_path = get_resource_path("assets", "lottie", "heart.json")
        self._heart_btn = LottieIconButton(heart_lottie_path, size=_ICON_SIZE)
        self._heart_btn.set_speed(1.5)
        self._heart_btn.setCheckable(True)
        self._heart_btn.clicked.connect(self._on_heart_clicked)
        toggles.addWidget(self._heart_btn)

        self._queue_btn = self._icon_btn("queue", size=_ICON_SIZE)
        self._queue_btn.setCheckable(True)
        self._queue_btn.clicked.connect(self._on_queue_clicked)
        toggles.addWidget(self._queue_btn)

        self._headphone_btn = self._icon_btn("headphone", size=_ICON_SIZE)
        self._headphone_btn.clicked.connect(self._on_headphone_clicked)
        toggles.addWidget(self._headphone_btn)

        toggles.addStretch()

        # Volume controls
        self._volume_slider = QSlider(Qt.Orientation.Horizontal)
        self._volume_slider.setMinimum(0)
        self._volume_slider.setMaximum(100)
        self._volume_slider.setFixedWidth(110)
        self._volume_slider.setValue(50)
        self._volume_slider.valueChanged.connect(self._on_volume_slider_changed)
        toggles.addWidget(self._volume_slider)

        mute_lottie_path = get_resource_path("assets", "lottie", "Sound_mute.json")
        self._mute_btn = LottieIconButton(mute_lottie_path, size=_ICON_SIZE)
        self._mute_btn.set_state_frames(10, 23)
        self._mute_btn.set_speed(1.5)  # <-- You can change SPEED here
        self._mute_btn.clicked.connect(self._on_mute_clicked)
        toggles.addWidget(self._mute_btn)

        root.addLayout(toggles)

        # Press-and-hold seek timer wiring
        from PyQt6.QtCore import QTimer
        self._next_hold_timer = QTimer(self)
        self._next_hold_timer.setSingleShot(True)
        self._next_hold_timer.timeout.connect(self._on_next_hold_timeout)
        self._next_is_holding = False

        self._prev_hold_timer = QTimer(self)
        self._prev_hold_timer.setSingleShot(True)
        self._prev_hold_timer.timeout.connect(self._on_prev_hold_timeout)
        self._prev_is_holding = False

    def _icon_btn(self, asset: str, size: int = _ICON_SIZE) -> QPushButton:
        btn = HoverBoldButton()
        btn.setObjectName("iconButton")
        btn.setFixedSize(size + 16, size + 16)
        btn.setFlat(True)
        # Icon will be set by apply_theme(); placeholder until then
        return btn

    # ------------------------------------------------------------------
    # Hold-seek wiring (mirrors bottom bar pattern)
    # ------------------------------------------------------------------

    def _on_next_pressed(self) -> None:
        self._next_is_holding = False
        self._next_hold_timer.start(400)

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

    def _on_prev_released(self) -> None:
        self._prev_hold_timer.stop()
        if self._prev_is_holding:
            self._prev_is_holding = False
            self.prev_hold_stopped.emit()
        else:
            self.previous_clicked.emit()

    def _on_next_hold_timeout(self) -> None:
        self._next_is_holding = True
        self.next_hold_started.emit()

    def _on_prev_hold_timeout(self) -> None:
        self._prev_is_holding = True
        self.prev_hold_started.emit()

    # ------------------------------------------------------------------
    # Toggle handlers
    # ------------------------------------------------------------------

    def _on_heart_clicked(self) -> None:
        active = self._heart_btn.isChecked()
        if self._theme:
            color = "#E05C5C" if active else self._theme.get("text_secondary", "#9AA0AC")
            target_frame = self._heart_btn._total_frames - 1 if active else 0
            self._heart_btn.play_to(target_frame, None, animated=True)
        if self._current_path:
            self.favorite_toggled.emit(self._current_path, active)

    def set_favorited(self, favorited: bool, animated: bool = False) -> None:
        self._heart_btn.setChecked(favorited)
        text_secondary = self._theme.get("text_secondary", "#9AA0AC") if self._theme else "#9AA0AC"
        target_frame = self._heart_btn._total_frames - 1 if favorited else 0
        self._heart_btn.play_to(target_frame, None, animated=animated)

    def _on_shuffle_clicked(self) -> None:
        self.shuffle_clicked.emit()

    def _on_repeat_clicked(self) -> None:
        self.repeat_clicked.emit()

    def _on_queue_close_requested(self) -> None:
        self._queue_btn.setChecked(False)
        self._on_queue_clicked()

    def _on_lyrics_clicked(self) -> None:
        self._lyrics_active = self._lyrics_btn.isChecked()
        self._update_lyrics_state()
        self._update_toggle_styles()

    def _on_queue_clicked(self) -> None:
        self._queue_active = self._queue_btn.isChecked()
        self._update_queue_state()
        self._update_toggle_styles()

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

        from PyQt6.QtMultimedia import QMediaDevices
        default_dev = QMediaDevices.defaultAudioOutput()
        default_desc = default_dev.description() + " (default)"

        default_action = QAction(default_desc, menu)
        default_action.setCheckable(True)
        if self._is_default:
            default_action.setChecked(True)
        default_action.triggered.connect(lambda checked: self.output_device_selected.emit(None))
        menu.addAction(default_action)
        menu.addSeparator()

        for device in self._devices:
            desc = device.description()

            action = QAction(desc, menu)
            action.setCheckable(True)
            if not self._is_default and self._current_device and bytes(device.id()) == bytes(self._current_device.id()):
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
        
        if isinstance(self._mute_btn, LottieIconButton):
            self._mute_btn.set_colors(text_primary, text_primary)
            if self._volume == 0.0 or self._muted:
                self._mute_btn.set_state(1, animated=True)
            else:
                self._mute_btn.set_state(0, animated=True)

    # ------------------------------------------------------------------
    # Lyrics / Queue panel animation
    # ------------------------------------------------------------------

    def _on_queue_anim_finished(self) -> None:
        if self._queue_active:
            w = max(self._queue_panel._min_width, min(self._queue_panel.width(), self._queue_panel._max_width))
            self._queue_panel.setMinimumWidth(w)
            self._queue_panel.setMaximumWidth(w)
        else:
            self._queue_panel.setMinimumWidth(0)
            self._queue_panel.setMaximumWidth(0)

    def _update_lyrics_state(self) -> None:
        """Fade art ↔ lyrics based on _lyrics_active."""
        if self._lyrics_active:
            # Fade art out
            self._art_fade.stop()
            self._art_fade.setStartValue(self._art_opacity.opacity())
            self._art_fade.setEndValue(0.0)
            self._art_fade.start()
            # Fade lyrics in
            rect = self._content_area.rect()
            self._lyrics_panel.setGeometry(rect.adjusted(24, 12, -24, -12))
            self._lyrics_panel.raise_()
            self._lyrics_panel.show()
            self._lyrics_fade.stop()
            self._lyrics_fade.setStartValue(self._lyrics_opacity.opacity())
            self._lyrics_fade.setEndValue(1.0)
            self._lyrics_fade.start()
        else:
            # Fade lyrics out
            self._lyrics_fade.stop()
            self._lyrics_fade.setStartValue(self._lyrics_opacity.opacity())
            self._lyrics_fade.setEndValue(0.0)
            self._lyrics_fade.start()
            # Fade art back in
            self._art_fade.stop()
            self._art_fade.setStartValue(self._art_opacity.opacity())
            self._art_fade.setEndValue(1.0)
            self._art_fade.start()

    def _update_queue_state(self) -> None:
        """Slide the queue panel in/out from the right."""
        target_w = int(self.width() * 0.40) if self._queue_active else 0
        if self._queue_active:
            self._queue_panel.refresh()
        else:
            self._queue_panel.setMinimumWidth(0)

        self._queue_anim.stop()
        self._queue_anim.setStartValue(self._queue_panel.maximumWidth())
        self._queue_anim.setEndValue(target_w)
        self._queue_anim.start()

    def _update_toggle_styles(self) -> None:
        """Apply active/inactive visual styles to Lyrics and Queue buttons."""
        if not self._theme:
            return
        accent = self._theme.get("accent", "#6C5CE7")
        secondary = self._theme.get("text_secondary", "#9AA0AC")
        surface = self._theme.get("surface", "#1C1F26")

        self._heart_btn.set_native_colors({"#7A869B": secondary})

        # Queue: grayed (secondary) when inactive, theme color when active
        q_color = accent if self._queue_active else secondary
        self._queue_btn.setIcon(svg_icon("queue", q_color, _ICON_SIZE))

        # Lyrics: transparent bg in both active and inactive states
        l_color = accent if self._lyrics_active else secondary
        self._lyrics_btn.setIcon(svg_icon("lyric", l_color, _ICON_SIZE))
        self._lyrics_btn.setStyleSheet("background: transparent; background-color: transparent; border: none;")

    # ------------------------------------------------------------------
    # Public setters (called by MainWindow as engine signals arrive)
    # ------------------------------------------------------------------

    def _clear_artist_layout(self) -> None:
        while self.artist_layout.count() > 0:
            item = self.artist_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

    def _populate_artists(self, artists: str) -> None:
        self._clear_artist_layout()
        if not artists:
            return
        
        # Split on commas (e.g. "Artist A, Artist B")
        artist_list = [a.strip() for a in artists.split(",") if a.strip()]
        for i, artist in enumerate(artist_list):
            lbl = ClickableLabel(artist, self)
            lbl.setObjectName("playerArtist")
            lbl.clicked.connect(lambda a=artist: self.artist_clicked.emit(a))
            self.artist_layout.addWidget(lbl)
            
            if i < len(artist_list) - 1:
                comma = QLabel(", ", self)
                comma.setObjectName("playerArtistComma")
                self.artist_layout.addWidget(comma)
                
        self.artist_layout.addStretch()

    def set_track(self, title: str, artists: str, art: "QPixmap | None", path: str | None = None) -> None:
        self._current_path = path
        self._title_label.setText(title)
        self._populate_artists(artists)
        self._art_label.setText("")

        # Compare new art with current art cacheKey to prevent unnecessary transitions between identical covers
        new_key = art.cacheKey() if (art and not art.isNull()) else None
        last_key = getattr(self, "_last_art_cache_key", None)
        art_changed = (new_key != last_key) or (new_key is None and last_key is not None)

        self._last_art_pixmap = art
        self._last_art_cache_key = new_key

        if art and not art.isNull():
            self._art_label.setPixmap(art)
            self._has_custom_art = True
            if art_changed:
                self._update_blurred_background(art)
        else:
            self._has_custom_art = False
            from ui.svg_icon import get_default_cover
            theme_dict = self._theme if self._theme else {}
            self._art_label.setPixmap(get_default_cover(_ART_SIZE, theme_dict, corner_radius=16.0))
            if art_changed:
                self._clear_blurred_background()

        # Load lyrics on track change
        self._lyrics_panel.load_track_lyrics(path or "")

    def _show_title_context_menu(self, pos) -> None:
        if not self._current_path or not self.store:
            return
        track = self.store.get_track(self._current_path)
        if not track:
            return
        from ui.context_menu import build_track_context_menu
        menu = build_track_context_menu(
            parent=self,
            track=track,
            store=self.store,
            engine=self.engine,
        )
        menu.exec(self._title_label.mapToGlobal(pos))

    def _update_blurred_background(self, art: QPixmap) -> None:
        self._blur_request_id += 1
        req_id = self._blur_request_id
        w = max(self.width(), 400)
        h = max(self.height(), 400)
        bg_hex = self._theme.get("bg", "#14161A") if self._theme else "#14161A"

        worker = _BlurWorker(req_id, art, w, h, bg_hex)
        worker.signals.finished.connect(self._on_blur_finished)
        QThreadPool.globalInstance().start(worker)

    def _clear_blurred_background(self) -> None:
        self._blur_request_id += 1
        self._bg_fade_1.stop()
        self._bg_fade_1.setStartValue(self._bg_opacity_1.opacity())
        self._bg_fade_1.setEndValue(0.0)
        self._bg_fade_1.start()

        self._bg_fade_2.stop()
        self._bg_fade_2.setStartValue(self._bg_opacity_2.opacity())
        self._bg_fade_2.setEndValue(0.0)
        self._bg_fade_2.start()

    def _on_blur_finished(self, request_id: int, pixmap: object) -> None:
        if request_id != self._blur_request_id:
            return
        if not pixmap or not isinstance(pixmap, QPixmap) or pixmap.isNull():
            self._clear_blurred_background()
            return

        w, h = self.width(), self.height()
        if self._active_bg_layer == 1:
            self._bg_label_2.setPixmap(pixmap)
            self._bg_label_2.setGeometry(0, 0, w, h)
            self._bg_label_2.lower()

            self._bg_fade_1.stop()
            self._bg_fade_1.setStartValue(self._bg_opacity_1.opacity())
            self._bg_fade_1.setEndValue(0.0)
            self._bg_fade_1.start()

            self._bg_fade_2.stop()
            self._bg_fade_2.setStartValue(self._bg_opacity_2.opacity())
            self._bg_fade_2.setEndValue(1.0)
            self._bg_fade_2.start()

            self._active_bg_layer = 2
        else:
            self._bg_label_1.setPixmap(pixmap)
            self._bg_label_1.setGeometry(0, 0, w, h)
            self._bg_label_1.lower()

            self._bg_fade_2.stop()
            self._bg_fade_2.setStartValue(self._bg_opacity_2.opacity())
            self._bg_fade_2.setEndValue(0.0)
            self._bg_fade_2.start()

            self._bg_fade_1.stop()
            self._bg_fade_1.setStartValue(self._bg_opacity_1.opacity())
            self._bg_fade_1.setEndValue(1.0)
            self._bg_fade_1.start()

            self._active_bg_layer = 1

    def set_playing(self, is_playing: bool) -> None:
        self._is_playing = is_playing
        self._play_pause_btn.set_state(1 if is_playing else 0, animated=True)

    def set_position(self, position_seconds: float, duration_seconds: float) -> None:
        self._seek_bar.set_position(position_seconds, duration_seconds)

    def set_shuffle(self, enabled: bool) -> None:
        self._shuffle_on = enabled
        self._shuffle_btn.setChecked(enabled)
        self._refresh_mode_icons()

    def set_repeat_mode(self, mode: str) -> None:
        self._repeat_mode = mode
        self._refresh_mode_icons()

    def set_lyrics_active(self, active: bool) -> None:
        self._lyrics_active = active
        self._lyrics_btn.setChecked(active)
        self._update_lyrics_state()
        self._update_toggle_styles()

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

    def set_available_devices(self, devices: list[object], current: object | None, is_default: bool = True) -> None:
        self._devices = list(devices)
        self._current_device = current
        self._is_default = is_default

    def _refresh_mode_icons(self) -> None:
        if not self._theme:
            return
        accent = self._theme.get("accent", "#6C5CE7")
        secondary = self._theme.get("text_secondary", "#9AA0AC")

        # Shuffle Lottie update
        self._shuffle_btn.set_state_colors(accent, secondary)
        self._shuffle_btn.set_state(0 if self._shuffle_on else 1, animated=True)

        # Repeat Lottie update
        if self._repeat_mode == "off":
            self._repeat_btn.play_to(29, secondary, animated=True, forward_only=True)
        elif self._repeat_mode == "all":
            self._repeat_btn.play_to(10, accent, animated=True, forward_only=True)
        else:  # "one"
            self._repeat_btn.play_to(20, accent, animated=True, forward_only=True)

    # ------------------------------------------------------------------
    # Theme application
    # ------------------------------------------------------------------

    def apply_theme(self, theme: dict) -> None:
        """Re-render all SVG icons and apply background color for the
        given theme dict (from ui.theme.THEMES[key]).
        Called by MainWindow._apply_theme() whenever the theme changes.
        """
        self._theme = theme
        bg = theme.get("bg", "#14161A")
        surface = theme.get("surface", "#1C1F26")
        text_primary = theme.get("text_primary", "#EDEFF2")
        text_secondary = theme.get("text_secondary", "#9AA0AC")
        accent = theme.get("accent", "#6C5CE7")
        border = theme.get("border", "#2E323C")

        self.setStyleSheet(
            f"QFrame#playerScreen {{ background-color: {bg}; }}"
            f"QWidget#playerScreen QWidget {{ background-color: transparent; border: none; }}"
            f"QLabel#playerTitle {{ color: {text_primary}; background: transparent; }}"
            f"QLabel#playerTitle:hover {{ color: {accent}; text-decoration: underline; background: transparent; }}"
            f"QLabel#playerArtist, QLabel#playerArtistComma {{ color: {text_secondary}; background: transparent; }}"
            f"QLabel#playerArtist:hover {{ color: {accent}; text-decoration: underline; background: transparent; }}"
            f"QLabel#playerArt {{ background-color: {surface}; border-radius: 16px; "
            f"color: {text_secondary}; font-size: 64px; }}"
        )

        # Seek bar
        self._seek_bar.set_colors(accent, border, text_primary, text_secondary)

        # Transport icons
        self._back_btn.setIcon(svg_icon("back", text_primary, _ICON_SIZE))
        self._prev_btn.setIcon(svg_icon("prev", text_primary, _ICON_SIZE))
        self._next_btn.setIcon(svg_icon("next", text_primary, _ICON_SIZE))
        self._play_pause_btn.set_color(text_primary)

        # Heart (outline = inactive, filled red = active)
        heart_color = "#E05C5C" if self._heart_btn.isChecked() else text_secondary
        self._heart_btn.setIcon(svg_icon("heart", heart_color, _ICON_SIZE, filled=self._heart_btn.isChecked()))

        # Shuffle + repeat mode icons
        self._refresh_mode_icons()

        # Panel toggles
        self._update_toggle_styles()

        # Headphone icon
        self._headphone_btn.setIcon(svg_icon("headphone", text_secondary, _ICON_SIZE))

        # Re-render default art if no custom art is loaded
        if not getattr(self, "_has_custom_art", False):
            from ui.svg_icon import get_default_cover
            self._art_label.setPixmap(get_default_cover(_ART_SIZE, theme, corner_radius=16.0))

        # Update volume icon
        self._update_volume_icon()

        # Apply theme to lyrics and queue panels
        if hasattr(self, "_lyrics_panel"):
            self._lyrics_panel.apply_theme(theme)
        if hasattr(self, "_queue_panel"):
            self._queue_panel.apply_theme(theme)

        # Re-render blurred background with new theme overlay tint
        if getattr(self, "_has_custom_art", False) and getattr(self, "_last_art_pixmap", None):
            self._update_blurred_background(self._last_art_pixmap)
        else:
            self._clear_blurred_background()

    # ------------------------------------------------------------------
    # Slide animation
    # ------------------------------------------------------------------

    def show_player(self) -> None:
        """Animate the player screen sliding up from the bottom."""
        parent = self.parent()
        if parent is None:
            return
        pw, ph = parent.width(), parent.height()
        self.setGeometry(0, ph, pw, ph)   # start: off-screen below
        self.show()
        self.raise_()

        self._slide_anim.stop()
        self._slide_anim.setStartValue(QRect(0, ph, pw, ph))
        self._slide_anim.setEndValue(QRect(0, 0, pw, ph))
        self._slide_anim.start()

    def hide_player(self) -> None:
        """Animate the player screen sliding back down."""
        parent = self.parent()
        if parent is None:
            self.hide()
            return
        pw, ph = parent.width(), parent.height()

        self._slide_anim.stop()
        self._slide_anim.setStartValue(QRect(0, 0, pw, ph))
        self._slide_anim.setEndValue(QRect(0, ph, pw, ph))
        self._slide_anim.finished.connect(self._on_slide_out_done)
        self._slide_anim.start()

    def _on_slide_out_done(self) -> None:
        self.hide()
        try:
            self._slide_anim.finished.disconnect(self._on_slide_out_done)
        except TypeError:
            pass

    def resizeEvent(self, event) -> None:
        """Keep the lyrics panel geometry in sync with the content area."""
        super().resizeEvent(event)
        if hasattr(self, "_bg_label_1") and hasattr(self, "_bg_label_2"):
            w, h = self.width(), self.height()
            self._bg_label_1.setGeometry(0, 0, w, h)
            self._bg_label_2.setGeometry(0, 0, w, h)
            self._bg_label_1.lower()
            self._bg_label_2.lower()

        if hasattr(self, "_lyrics_panel") and hasattr(self, "_content_area"):
            rect = self._content_area.rect()
            self._lyrics_panel.setGeometry(rect.adjusted(24, 12, -24, -12))

    def eventFilter(self, watched, event) -> bool:
        from PyQt6.QtCore import QEvent
        if watched == getattr(self, "_content_area", None) and event.type() == QEvent.Type.Resize:
            if hasattr(self, "_lyrics_panel"):
                rect = self._content_area.rect()
                self._lyrics_panel.setGeometry(rect.adjusted(24, 12, -24, -12))
        return super().eventFilter(watched, event)

    def parentResized(self, new_size: "QSize") -> None:
        """Called by MainWindow.resizeEvent so the overlay always fills
        the window even when it's hidden (ready for the next open).
        """
        if not self._slide_anim.state() == QPropertyAnimation.State.Running:
            self.setGeometry(0, 0, new_size.width(), new_size.height())
        if hasattr(self, "_bg_label_1") and hasattr(self, "_bg_label_2"):
            w, h = new_size.width(), new_size.height()
            self._bg_label_1.setGeometry(0, 0, w, h)
            self._bg_label_2.setGeometry(0, 0, w, h)
            self._bg_label_1.lower()
            self._bg_label_2.lower()
        if self.isVisible():
            self.raise_()
