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
from PyQt6.QtWidgets import QFrame, QHBoxLayout, QGridLayout, QWidget, QPushButton, QLabel, QLineEdit, QSizePolicy


class SearchLineEdit(QLineEdit):
    """QLineEdit that emits escape_pressed when Esc is pressed."""
    escape_pressed = pyqtSignal()

    def keyPressEvent(self, event) -> None:
        if event.key() == Qt.Key.Key_Escape:
            self.escape_pressed.emit()
            event.accept()
        else:
            super().keyPressEvent(event)


class TopBar(QFrame):
    settings_clicked = pyqtSignal()
    queue_clicked = pyqtSignal()
    back_clicked = pyqtSignal()
    forward_clicked = pyqtSignal()
    home_clicked = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("topBar")
        self.setFixedHeight(48)

        layout = QGridLayout(self)
        layout.setContentsMargins(16, 0, 16, 0)
        layout.setColumnStretch(0, 1)
        layout.setColumnStretch(1, 0)
        layout.setColumnStretch(2, 1)

        import os
        from utils.paths import get_resource_path
        from PyQt6.QtGui import QPixmap
        logo_path = get_resource_path("assets", "logo.png")

        left_widget = QWidget(self)
        left_layout = QHBoxLayout(left_widget)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(8)

        self.logo_label = QLabel()
        self.logo_label.setObjectName("topBarLogo")
        if os.path.exists(logo_path):
            pix = QPixmap(logo_path)
            if not pix.isNull():
                self.logo_label.setPixmap(pix.scaled(36, 36, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
        left_layout.addWidget(self.logo_label)

        title = QLabel("AuraPlayer")
        title.setStyleSheet("font-size: 15px; font-weight: 700;")
        left_layout.addWidget(title)

        left_layout.addSpacing(16)
        self.back_button = QPushButton("")
        self.back_button.setObjectName("iconButton")
        self.back_button.setFixedSize(32, 32)
        self.back_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.back_button.clicked.connect(self.back_clicked.emit)
        left_layout.addWidget(self.back_button)

        self.home_button = QPushButton("")
        self.home_button.setObjectName("iconButton")
        self.home_button.setFixedSize(32, 32)
        self.home_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.home_button.clicked.connect(self.home_clicked.emit)
        left_layout.addWidget(self.home_button)

        self.forward_button = QPushButton("")
        self.forward_button.setObjectName("iconButton")
        self.forward_button.setFixedSize(32, 32)
        self.forward_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.forward_button.clicked.connect(self.forward_clicked.emit)
        left_layout.addWidget(self.forward_button)
        left_layout.addStretch()

        layout.addWidget(left_widget, 0, 0, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)

        self.search_bar_frame = QFrame(self)
        self.search_bar_frame.setObjectName("TopSearchBarFrame")
        self.search_bar_frame.setFixedSize(280, 32)
        s_layout = QHBoxLayout(self.search_bar_frame)
        s_layout.setContentsMargins(12, 0, 10, 0)
        s_layout.setSpacing(6)

        self.search_icon_lbl = QLabel(self.search_bar_frame)
        s_layout.addWidget(self.search_icon_lbl)

        self.search_input = SearchLineEdit(self.search_bar_frame)
        self.search_input.setPlaceholderText("Search...")
        self.search_input.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        s_layout.addWidget(self.search_input)

        self.clear_btn = QPushButton("×", self.search_bar_frame)
        self.clear_btn.setObjectName("searchClearBtn")
        self.clear_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.clear_btn.setFixedSize(24, 24)
        self.clear_btn.clicked.connect(self.search_input.clear)
        self.clear_btn.setVisible(False)
        self.search_input.textChanged.connect(lambda t: self.clear_btn.setVisible(len(t) > 0))
        s_layout.addWidget(self.clear_btn)

        layout.addWidget(self.search_bar_frame, 0, 1, Qt.AlignmentFlag.AlignCenter | Qt.AlignmentFlag.AlignVCenter)

        right_widget = QWidget(self)
        right_layout = QHBoxLayout(right_widget)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.addStretch()

        self.settings_button = QPushButton("")
        self.settings_button.setObjectName("iconButton")
        self.settings_button.setFixedSize(32, 32)
        self.settings_button.clicked.connect(self.settings_clicked.emit)
        right_layout.addWidget(self.settings_button)

        layout.addWidget(right_widget, 0, 2, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

        from ui.theme import THEMES, DEFAULT_THEME
        self.apply_theme(THEMES.get(DEFAULT_THEME, {}))
        self.update_nav_state(False, False, False, visible=False)

    def apply_theme(self, theme: dict) -> None:
        """Re-render SVG icons for the top bar with active theme colors."""
        self._current_theme = theme
        from ui.svg_icon import svg_icon, svg_pixmap
        from PyQt6.QtGui import QIcon
        text_sec = theme.get("text_secondary", "#9AA0AC")
        text_pri = theme.get("text_primary", "#E5E9F0")
        disabled_col = theme.get("border", "#3E4452")

        def _icon(asset: str, size: int = 18, mirrored: bool = False) -> QIcon:
            ic = QIcon()
            ic.addPixmap(svg_pixmap(asset, text_pri, size, mirrored=mirrored), QIcon.Mode.Normal)
            ic.addPixmap(svg_pixmap(asset, disabled_col, size, mirrored=mirrored), QIcon.Mode.Disabled)
            return ic

        self.back_button.setIcon(_icon("back", 18, mirrored=False))
        self.home_button.setIcon(_icon("home", 18, mirrored=False))
        self.forward_button.setIcon(_icon("back", 18, mirrored=True))

        self.search_icon_lbl.setPixmap(svg_pixmap("search", text_sec, 14))
        self.search_bar_frame.setStyleSheet(f"""
            QFrame#TopSearchBarFrame {{
                background-color: {theme.get('surface', '#282C34')};
                border: 1px solid {theme.get('border', '#3E4452')};
                border-radius: 16px;
            }}
            QLineEdit {{
                border: none;
                background: transparent;
                font-size: 13px;
                color: {theme.get('text_primary', '#FFFFFF')};
            }}
        """)
        self.clear_btn.setStyleSheet(f"""
            QPushButton#searchClearBtn {{
                border: none;
                background: transparent;
                padding: 0px;
                margin: 0px;
                text-align: center;
                font-size: 18px;
                font-weight: bold;
                color: {theme.get('text_secondary', '#ABB2BF')};
            }}
            QPushButton#searchClearBtn:hover {{
                color: {theme.get('text_primary', '#FFFFFF')};
            }}
        """)
        self.settings_button.setIcon(svg_icon("settings", text_sec, 18))

    def update_nav_state(self, can_back: bool, can_forward: bool, can_home: bool, visible: bool = True) -> None:
        self.back_button.setVisible(visible)
        self.home_button.setVisible(visible)
        self.forward_button.setVisible(visible)
        self.back_button.setEnabled(can_back)
        self.home_button.setEnabled(can_home)
        self.forward_button.setEnabled(can_forward)
        if hasattr(self, "_current_theme"):
            self.apply_theme(self._current_theme)
