from PyQt6.QtWidgets import QLabel, QSizePolicy
from PyQt6.QtCore import pyqtSignal, Qt

class ClickableLabel(QLabel):
    clicked = pyqtSignal()

    def __init__(self, text: str = "", parent=None):
        super().__init__(text, parent)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setObjectName("clickableLabel")
        self.setProperty("clickable", True)
        self.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Preferred)

    def enterEvent(self, event) -> None:
        font = self.font()
        font.setUnderline(True)
        self.setFont(font)
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:
        font = self.font()
        font.setUnderline(False)
        self.setFont(font)
        super().leaveEvent(event)

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
            event.accept()
        else:
            super().mousePressEvent(event)
