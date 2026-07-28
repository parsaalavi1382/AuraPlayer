"""
HoverBoldButton: A custom QPushButton subclass that dynamically switches font weight to BOLD (and scales icon slightly if present) on mouse hover in any button state.
"""

from PyQt6.QtWidgets import QPushButton
from PyQt6.QtCore import QSize, Qt
from PyQt6.QtGui import QFont

class HoverBoldButton(QPushButton):
    """QPushButton subclass that toggles bold font weight on mouse hover in any state."""
    def __init__(self, text: str = "", parent=None):
        super().__init__(text, parent)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._orig_icon_size: QSize | None = None

    def enterEvent(self, event) -> None:
        font = self.font()
        font.setBold(True)
        self.setFont(font)

        curr_icon_size = self.iconSize()
        if not curr_icon_size.isEmpty():
            if self._orig_icon_size is None:
                self._orig_icon_size = curr_icon_size
            self.setIconSize(self._orig_icon_size + QSize(2, 2))

        super().enterEvent(event)

    def leaveEvent(self, event) -> None:
        font = self.font()
        font.setBold(False)
        self.setFont(font)

        if self._orig_icon_size is not None:
            self.setIconSize(self._orig_icon_size)

        super().leaveEvent(event)
