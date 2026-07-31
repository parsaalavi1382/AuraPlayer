import os
from typing import Optional
from PyQt6.QtWidgets import QPushButton
from PyQt6.QtCore import QTimer, QSize, Qt
from PyQt6.QtGui import QIcon, QPixmap, QImage, QPainter, QColor
from ui.widgets.hover_bold_button import HoverBoldButton

try:
    import rlottie_python
    HAS_RLOTTIE = True
except ImportError:
    HAS_RLOTTIE = False

class LottieIconButton(HoverBoldButton):
    """
    A custom button that plays a Lottie animation to transition between two states.
    It inherits HoverBoldButton's scaling on hover, and applies a color tint to the Lottie frames.
    """
    def __init__(self, lottie_path: str, size: int = 24, parent=None):
        super().__init__("", parent)
        self.setFixedSize(size + 16, size + 16)
        self.setFlat(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setObjectName("iconButton")
        self.setIconSize(QSize(size, size))

        self._lottie_path = lottie_path
        self._icon_size = size
        self._animation = None
        self._total_frames = 0
        self._fps = 60.0
        
        self._speed = 1.0

        self._current_frame = 0
        self._state = 0  # 0 or 1
        self._target_frame = 0
        self._direction = 1
        self._is_animating = False
        
        self._color_start: Optional[str] = None
        self._color_end: Optional[str] = None
        
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._advance_frame)

        self._load_animation()

    def _load_animation(self):
        if not HAS_RLOTTIE or not os.path.exists(self._lottie_path):
            return
            
        try:
            self._animation = rlottie_python.LottieAnimation.from_file(self._lottie_path)
            self._total_frames = self._animation.lottie_animation_get_totalframe()
            self._fps = float(self._animation.lottie_animation_get_framerate() or 60.0)
            self._update_timer_interval()
            self._render_current_frame()
        except Exception as e:
            print(f"Error loading lottie file {self._lottie_path}: {e}")

    def _update_timer_interval(self):
        if self._fps > 0:
            interval = int(1000.0 / (self._fps * self._speed))
            self._timer.setInterval(max(1, interval))

    def set_colors(self, color_start: str, color_end: Optional[str] = None):
        """Sets the color(s) to tint the lottie frames. If color_end is provided, it interpolates."""
        self._color_start = color_start
        self._color_end = color_end
        self._render_current_frame()

    def set_color(self, hex_color: str):
        """Sets a static color to tint the lottie frames."""
        self.set_colors(hex_color)

    def set_speed(self, speed: float):
        """Sets the playback speed multiplier (e.g. 1.5 for 50% faster)."""
        self._speed = max(0.1, speed)
        self._update_timer_interval()

    def set_state(self, state: int, animated: bool = True):
        """
        Transition to a state.
        state=0 goes to frame 0.
        state=1 goes to total_frames - 1.
        """
        if not self._animation or self._total_frames == 0:
            return

        self._state = state
        self._target_frame = (self._total_frames - 1) if state == 1 else 0

        if not animated:
            self._current_frame = self._target_frame
            self._is_animating = False
            self._timer.stop()
            self._render_current_frame()
            return

        # Start animation towards target
        if self._current_frame != self._target_frame:
            self._direction = 1 if self._target_frame > self._current_frame else -1
            self._is_animating = True
            self._update_timer_interval()
            self._timer.start()

    def enterEvent(self, event):
        super().enterEvent(event)
        self._render_current_frame()

    def leaveEvent(self, event):
        super().leaveEvent(event)
        self._render_current_frame()

    def _interpolate_color(self, hex1: str, hex2: str, t: float) -> str:
        c1 = QColor(hex1)
        c2 = QColor(hex2)
        r = int(c1.red() + (c2.red() - c1.red()) * t)
        g = int(c1.green() + (c2.green() - c1.green()) * t)
        b = int(c1.blue() + (c2.blue() - c1.blue()) * t)
        a = int(c1.alpha() + (c2.alpha() - c1.alpha()) * t)
        return QColor(r, g, b, a).name(QColor.NameFormat.HexArgb)

    def _render_current_frame(self):
        if not self._animation:
            return

        curr_size = self.iconSize()
        w = curr_size.width() if not curr_size.isEmpty() else self._icon_size
        h = curr_size.height() if not curr_size.isEmpty() else self._icon_size
        
        try:
            pil_img = self._animation.render_pillow_frame(
                frame_num=int(self._current_frame),
                width=w,
                height=h
            )
            raw_data = pil_img.tobytes("raw", "RGBA")
            qimg = QImage(raw_data, w, h, QImage.Format.Format_RGBA8888)
            pixmap = QPixmap.fromImage(qimg)
            
            # Apply color tint if specified
            tint_hex = None
            if self._color_start and self._color_end and self._total_frames > 1:
                t = self._current_frame / (self._total_frames - 1)
                tint_hex = self._interpolate_color(self._color_start, self._color_end, t)
            elif self._color_start:
                tint_hex = self._color_start

            if tint_hex:
                colored = QPixmap(pixmap.size())
                colored.fill(Qt.GlobalColor.transparent)
                painter = QPainter(colored)
                painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Source)
                painter.drawPixmap(0, 0, pixmap)
                painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceIn)
                painter.fillRect(colored.rect(), QColor(tint_hex))
                painter.end()
                pixmap = colored
                
            self.setIcon(QIcon(pixmap))
            
        except Exception as e:
            print(f"Error rendering lottie frame: {e}")

    def _advance_frame(self):
        if not self._is_animating:
            self._timer.stop()
            return

        next_frame = self._current_frame + self._direction
        reached_target = False

        if self._direction > 0 and next_frame >= self._target_frame:
            next_frame = self._target_frame
            reached_target = True
        elif self._direction < 0 and next_frame <= self._target_frame:
            next_frame = self._target_frame
            reached_target = True

        self._current_frame = next_frame
        self._render_current_frame()

        if reached_target:
            self._is_animating = False
            self._timer.stop()
