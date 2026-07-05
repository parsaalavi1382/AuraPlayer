"""
Top bar: Settings + Search buttons, per spec.

Step 2 scope: Settings opens a real dialog (folder management +
separator config, since both are needed to test scanning from the UI
at all). Search is visually present but wired in Step 9 per the
roadmap -- clicking it now shows a brief inline note rather than doing
nothing silently.

Renamed to "AuraPlayer" (2026-06-28). The app icon at assets/logo.png
and the animated active-tab indicator (FEATURE_BACKLOG.md item #15)
are deliberately NOT built here -- both are real feature work bundled
with the Step 9 top-bar/search redesign (the tab indicator lives in
MainWindow's QTabWidget styling, not this widget, and the logo asset
isn't in the repo yet per the person's explicit request to place it
themselves later). Doing the logo+indicator work piecemeal now would
mean touching this same area twice.
"""

from __future__ import annotations

from PyQt6.QtCore import pyqtSignal, Qt
from PyQt6.QtWidgets import QFrame, QHBoxLayout, QPushButton, QLabel


class TopBar(QFrame):
    settings_clicked = pyqtSignal()
    queue_clicked = pyqtSignal()
    search_clicked = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("topBar")
        self.setFixedHeight(48)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 0, 16, 0)
        layout.setSpacing(8)

        import os
        from utils.paths import get_resource_path
        from PyQt6.QtGui import QPixmap
        logo_path = get_resource_path("assets", "logo.png")

        self.logo_label = QLabel()
        self.logo_label.setObjectName("topBarLogo")
        if os.path.exists(logo_path):
            pix = QPixmap(logo_path)
            if not pix.isNull():
                self.logo_label.setPixmap(pix.scaled(36, 36, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
        layout.addWidget(self.logo_label)

        title = QLabel("AuraPlayer")
        title.setStyleSheet("font-size: 15px; font-weight: 700;")
        layout.addWidget(title)
        layout.addStretch()

        self.search_button = QPushButton("")
        self.search_button.setObjectName("iconButton")
        self.search_button.setFixedSize(32, 32)
        self.search_button.clicked.connect(self.search_clicked.emit)
        layout.addWidget(self.search_button)

        self.settings_button = QPushButton("")
        self.settings_button.setObjectName("iconButton")
        self.settings_button.setFixedSize(32, 32)
        self.settings_button.clicked.connect(self.settings_clicked.emit)
        layout.addWidget(self.settings_button)

    def apply_theme(self, theme: dict) -> None:
        """Re-render SVG icons for the top bar with active theme colors."""
        from ui.svg_icon import svg_icon
        text_sec = theme.get("text_secondary", "#9AA0AC")
        self.search_button.setIcon(svg_icon("search", text_sec, 18))
        self.settings_button.setIcon(svg_icon("settings", text_sec, 18))
