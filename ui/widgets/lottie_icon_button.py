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
        self._state = 0  # legacy
        self._target_frame = 0
        self._transition_start_frame = 0
        self._direction = 1
        self._is_animating = False
        
        self._native_colors_map: dict[str, str] = {}
        
        self._color_start: Optional[str] = None
        self._color_end: Optional[str] = None
        
        self._state0_color: Optional[str] = None
        self._state1_color: Optional[str] = None

        self._custom_frame_0: Optional[int] = None
        self._custom_frame_1: Optional[int] = None

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._advance_frame)

        self._load_animation()

    def set_state_frames(self, frame_state_0: int, frame_state_1: int):
        """Sets custom target frames for state 0 (on) and state 1 (off)."""
        self._custom_frame_0 = frame_state_0
        self._custom_frame_1 = frame_state_1

    def set_state_colors(self, state0_color: str, state1_color: str):
        """Sets target color for state 0 and state 1."""
        self._state0_color = state0_color
        self._state1_color = state1_color

    def set_native_colors(self, color_map: dict[str, str]):
        """
        Replaces specific hardcoded hex colors in the Lottie JSON with new hex colors,
        preserving the original animation structure (avoids flattening like set_color).
        """
        self._native_colors_map = color_map
        self._load_animation()

    def _hex_to_rgb_float(self, hex_str: str) -> list[float]:
        hex_str = hex_str.lstrip('#')
        return [int(hex_str[0:2], 16)/255.0, int(hex_str[2:4], 16)/255.0, int(hex_str[4:6], 16)/255.0, 1.0]

    def _replace_colors_recursive(self, obj, color_map_floats: dict[tuple, list[float]]):
        if isinstance(obj, dict):
            if 'c' in obj and isinstance(obj['c'], dict) and 'k' in obj['c']:
                k = obj['c']['k']
                if isinstance(k, list) and len(k) == 4 and isinstance(k[0], (int, float)):
                    for orig_f, new_f in color_map_floats.items():
                        if all(abs(a - b) < 0.01 for a, b in zip(k, orig_f)):
                            obj['c']['k'] = new_f
            for v in obj.values():
                self._replace_colors_recursive(v, color_map_floats)
        elif isinstance(obj, list):
            for item in obj:
                self._replace_colors_recursive(item, color_map_floats)

    def _load_animation(self):
        if not HAS_RLOTTIE or not os.path.exists(self._lottie_path):
            return
            
        try:
            if self._native_colors_map:
                import json
                with open(self._lottie_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                
                # Convert color map to float tuples for fast matching
                float_map = {}
                for orig_hex, new_hex in self._native_colors_map.items():
                    float_map[tuple(self._hex_to_rgb_float(orig_hex))] = self._hex_to_rgb_float(new_hex)
                    
                self._replace_colors_recursive(data, float_map)
                json_str = json.dumps(data)
                self._animation = rlottie_python.LottieAnimation.from_data(json_str, resource_path="")
            else:
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
        default_frame_1 = self._total_frames - 1
        target = self._custom_frame_0 if state == 0 else self._custom_frame_1
        if target is None:
            target = 0 if state == 0 else default_frame_1

        self._target_frame = max(0, min(target, self._total_frames - 1))
        self._transition_start_frame = self._current_frame

        # Set transition colors if state colors are defined
        target_color = self._state0_color if state == 0 else self._state1_color
        if target_color:
            self._color_start = self._color_end if self._color_end else target_color
            self._color_end = target_color

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

    def play_to(self, target_frame: int, target_color: Optional[str] = None, animated: bool = True, forward_only: bool = False):
        """Plays the animation to a specific frame, interpolating to target_color."""
        if not self._animation or self._total_frames == 0:
            return

        # Current color becomes start color for this transition
        self._color_start = self._color_end if self._color_end else (self._color_start or target_color)
        self._color_end = target_color
        
        # Snap to 0 if we are at the end of the loop and need to play forward from the start
        if forward_only and self._current_frame >= self._total_frames - 2 and target_frame < self._current_frame:
            self._current_frame = 0

        self._target_frame = max(0, min(target_frame, self._total_frames - 1))
        self._transition_start_frame = self._current_frame

        if not animated:
            self._current_frame = self._target_frame
            self._is_animating = False
            self._timer.stop()
            self._render_current_frame()
            return

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
            qimg = QImage(raw_data, w, h, QImage.Format.Format_RGBA8888_Premultiplied)
            pixmap = QPixmap.fromImage(qimg)
            
            # Apply color tint if specified
            tint_hex = None
            if self._color_start and self._color_end and self._transition_start_frame != self._target_frame:
                # Interpolate based on transition progress
                total_dist = abs(self._target_frame - self._transition_start_frame)
                curr_dist = abs(self._current_frame - self._transition_start_frame)
                t = curr_dist / total_dist if total_dist > 0 else 1.0
                tint_hex = self._interpolate_color(self._color_start, self._color_end, t)
            elif self._color_end:
                tint_hex = self._color_end
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
