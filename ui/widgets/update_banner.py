from PyQt6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QCursor
from ui.svg_icon import svg_icon

class UpdateBanner(QFrame):
    dismissed = pyqtSignal()

    def __init__(self, version: str, parent=None):
        super().__init__(parent)
        self.setObjectName("updateBanner")
        # Ensure it doesn't take up too much space
        self.setFixedHeight(36)
        
        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 0, 16, 0)
        layout.setSpacing(12)

        icon_label = QLabel()
        icon_label.setFixedSize(16, 16)
        icon_label.setPixmap(svg_icon("arrow-up-circle", "#61AFEF").pixmap(16, 16))
        
        self.text_label = QLabel(f"Version {version} is available. You can update from Settings.")
        self.text_label.setObjectName("updateBannerText")
        self.text_label.setStyleSheet("color: var(--text);")
        
        self.close_btn = QPushButton()
        self.close_btn.setFixedSize(24, 24)
        self.close_btn.setIcon(svg_icon("x", "#9AA0AC"))
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

        layout.addWidget(icon_label)
        layout.addWidget(self.text_label)
        layout.addStretch(1)
        layout.addWidget(self.close_btn)

        # Style the banner itself
        self.setStyleSheet("""
            QFrame#updateBanner {
                background-color: var(--surface);
                border-bottom: 1px solid var(--border);
            }
        """)

    def _on_close(self):
        self.hide()
        self.dismissed.emit()
