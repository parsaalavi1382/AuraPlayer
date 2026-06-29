"""
Reusable empty-state panel shown when a view has nothing to display yet
(no folders added, folder added but no supported files found, a search
with no matches, etc).

Copy follows the interface's-own-voice guidance: state what's true and
what to do next, no apology, no filler.
"""

from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QLabel, QPushButton


class EmptyStateWidget(QWidget):
    def __init__(self, title: str, subtitle: str = "", action_label: str = "", parent=None):
        super().__init__(parent)
        self._action_label = action_label

        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.setSpacing(8)

        title_label = QLabel(title)
        title_label.setObjectName("emptyStateTitle")
        title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title_label)

        if subtitle:
            subtitle_label = QLabel(subtitle)
            subtitle_label.setObjectName("emptyStateSubtitle")
            subtitle_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            subtitle_label.setWordWrap(True)
            layout.addWidget(subtitle_label)

        self.action_button = None
        if action_label:
            self.action_button = QPushButton(action_label)
            self.action_button.setObjectName("accentButton")
            self.action_button.setFixedWidth(180)
            btn_layout = QVBoxLayout()
            btn_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
            btn_layout.addWidget(self.action_button, alignment=Qt.AlignmentFlag.AlignCenter)
            layout.addSpacing(8)
            layout.addLayout(btn_layout)
