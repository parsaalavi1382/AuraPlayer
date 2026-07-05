"""
SeekBar: a custom QWidget that replaces QProgressBar for the Player
Screen progress strip. Supports both click-to-seek and drag-to-scrub
with a visual thumb indicator, and emits a single seek_requested(float)
signal carrying the target position in seconds.

Why not QSlider? QSlider has platform-specific groove/handle rendering
that fights our stylesheet and produces inconsistent hit-test geometry
across Windows/macOS/Linux. A manual paintEvent gives us pixel-perfect
control over the groove height, thumb size, accent color fill, and hover
state without fighting QSS specificity.

The bar also displays elapsed and remaining time labels flanking the
groove, matching standard music player conventions.
"""

from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal, QPoint
from PyQt6.QtGui import QPainter, QColor, QPen, QCursor
from PyQt6.QtWidgets import QWidget, QHBoxLayout, QLabel, QSizePolicy


class _GrooveWidget(QWidget):
    """The actual draggable groove strip. Separated from the outer
    SeekBar so that mouse events land cleanly on the groove geometry
    without interference from the time labels on either side.
    """
    seek_requested = pyqtSignal(float)  # 0.0–1.0 fraction

    _GROOVE_H = 4      # px, resting height
    _GROOVE_H_HOVER = 6  # px, expanded on hover/drag
    _THUMB_R = 7       # thumb radius on hover/drag (invisible when idle)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(20)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self._fraction = 0.0
        self._dragging = False
        self._hovering = False
        self._accent = "#6C5CE7"
        self._groove_bg = "#2E323C"
        self._thumb_color = "#FFFFFF"

    def set_colors(self, accent: str, groove_bg: str, thumb: str) -> None:
        self._accent = accent
        self._groove_bg = groove_bg
        self._thumb_color = thumb
        self.update()

    def set_fraction(self, fraction: float) -> None:
        self._fraction = max(0.0, min(1.0, fraction))
        self.update()

    def fraction(self) -> float:
        return self._fraction

    def _fraction_from_x(self, x: int) -> float:
        w = self.width()
        if w <= 0:
            return 0.0
        return max(0.0, min(1.0, x / w))

    def enterEvent(self, event):
        self._hovering = True
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._hovering = False
        self.update()
        super().leaveEvent(event)

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._dragging = True
            frac = self._fraction_from_x(event.position().x())
            self._fraction = frac
            self.seek_requested.emit(frac)
            self.update()

    def mouseMoveEvent(self, event) -> None:
        if self._dragging:
            frac = self._fraction_from_x(event.position().x())
            self._fraction = frac
            self.seek_requested.emit(frac)
            self.update()

    def mouseReleaseEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._dragging = False
            self.update()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        w = self.width()
        h = self.height()
        active = self._dragging or self._hovering
        groove_h = self._GROOVE_H_HOVER if active else self._GROOVE_H
        gy = (h - groove_h) // 2
        radius = groove_h // 2

        # Background groove
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(self._groove_bg))
        painter.drawRoundedRect(0, gy, w, groove_h, radius, radius)

        # Filled portion
        filled_w = int(w * self._fraction)
        if filled_w > 0:
            painter.setBrush(QColor(self._accent))
            painter.drawRoundedRect(0, gy, filled_w, groove_h, radius, radius)

        # Thumb (only visible on hover / drag)
        if active:
            tx = int(w * self._fraction)
            ty = h // 2
            painter.setBrush(QColor(self._thumb_color))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawEllipse(
                tx - self._THUMB_R, ty - self._THUMB_R,
                self._THUMB_R * 2, self._THUMB_R * 2,
            )

        painter.end()


class SeekBar(QWidget):
    """Full seek bar: elapsed label + groove + remaining label."""

    seek_requested = pyqtSignal(float)   # target position in seconds

    def __init__(self, parent=None):
        super().__init__(parent)
        self._duration = 0.0

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        self._elapsed_label = QLabel("0:00")
        self._elapsed_label.setObjectName("seekBarTime")
        self._elapsed_label.setFixedWidth(42)
        self._elapsed_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        layout.addWidget(self._elapsed_label)

        self._groove = _GrooveWidget()
        self._groove.seek_requested.connect(self._on_groove_seek)
        layout.addWidget(self._groove)

        self._remaining_label = QLabel("-0:00")
        self._remaining_label.setObjectName("seekBarTime")
        self._remaining_label.setFixedWidth(42)
        self._remaining_label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        layout.addWidget(self._remaining_label)

    def set_colors(self, accent: str, groove_bg: str, thumb: str, text: str) -> None:
        self._groove.set_colors(accent, groove_bg, thumb)
        for label in (self._elapsed_label, self._remaining_label):
            label.setStyleSheet(f"color: {text}; font-size: 11px;")

    def set_position(self, position_seconds: float, duration_seconds: float) -> None:
        self._duration = duration_seconds
        fraction = (position_seconds / duration_seconds) if duration_seconds > 0 else 0.0
        self._groove.set_fraction(fraction)
        self._elapsed_label.setText(self._fmt(position_seconds))
        remaining = duration_seconds - position_seconds
        self._remaining_label.setText(f"-{self._fmt(remaining)}" if remaining >= 0 else "-0:00")

    def _on_groove_seek(self, fraction: float) -> None:
        target = fraction * self._duration
        self.seek_requested.emit(target)

    @staticmethod
    def _fmt(seconds: float) -> str:
        if seconds < 0:
            seconds = 0
        m, s = divmod(int(seconds), 60)
        return f"{m}:{s:02d}"
