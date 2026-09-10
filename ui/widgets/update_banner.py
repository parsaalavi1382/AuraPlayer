from PyQt6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QCursor
import qtawesome as qta


class UpdateBanner(QFrame):
    dismissed = pyqtSignal()
    update_requested = pyqtSignal()

    def __init__(self, version: str, parent=None):
        super().__init__(parent)
        self.setObjectName("updateBanner")
        self.setFixedHeight(38)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 0, 16, 0)
        layout.setSpacing(12)

        self.icon_label = QLabel()
        self.icon_label.setFixedSize(16, 16)
        self.icon_label.setPixmap(qta.icon("fa5s.arrow-circle-up", color="#61AFEF").pixmap(16, 16))

        self.text_label = QLabel(f"Version {version} is available!")
        self.text_label.setObjectName("updateBannerText")

        self.update_btn = QPushButton("Update Now")
        self.update_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.update_btn.setObjectName("accentButton")
        self.update_btn.clicked.connect(self._on_update)

        self.close_btn = QPushButton()
        self.close_btn.setFixedSize(24, 24)
        self.close_btn.setIcon(qta.icon("fa5s.times", color="#9AA0AC"))
        self.close_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.close_btn.setToolTip("Dismiss")
        self.close_btn.setStyleSheet("""
            QPushButton {
                background: transparent;
                border: none;
            }
            QPushButton:hover {
                background: rgba(255, 255, 255, 0.1);
                border-radius: 12px;
            }
        """)

        self.close_btn.clicked.connect(self._on_close)

        layout.addWidget(self.icon_label)
        layout.addWidget(self.text_label)
        layout.addStretch(1)
        layout.addWidget(self.update_btn)
        layout.addWidget(self.close_btn)

    def apply_theme(self, theme: dict) -> None:
        surface = theme.get("surface", "#1C1F26")
        border = theme.get("border", "#30363D")
        text_primary = theme.get("text_primary", "#E6E6E6")
        accent = theme.get("accent", "#61AFEF")
        text_muted = theme.get("text_muted", "#9AA0AC")

        self.setStyleSheet(f"""
            QFrame#updateBanner {{
                background-color: {surface};
                border-bottom: 1px solid {border};
            }}
        """)
        self.text_label.setStyleSheet(f"color: {text_primary}; font-size: 13px;")
        self.icon_label.setPixmap(qta.icon("fa5s.arrow-circle-up", color=accent).pixmap(16, 16))
        self.close_btn.setIcon(qta.icon("fa5s.times", color=text_muted))

    def _on_close(self):
        self.hide()
        self.dismissed.emit()

    def _on_update(self):
        self.hide()
        self.update_requested.emit()
