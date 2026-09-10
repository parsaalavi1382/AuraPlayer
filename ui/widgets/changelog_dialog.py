from PyQt6.QtWidgets import QDialog, QVBoxLayout, QTextBrowser, QPushButton, QHBoxLayout
from PyQt6.QtCore import Qt
from ui.theme import THEMES, DEFAULT_THEME

class ChangelogDialog(QDialog):
    def __init__(self, version: str, markdown_content: str, theme: dict, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"What's New in {version}")
        self.resize(600, 400)
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        self.browser = QTextBrowser()
        self.browser.setOpenExternalLinks(True)
        self.browser.setMarkdown(markdown_content)
        
        # Style the browser
        bg = theme.get("surface", "#1C1F26")
        fg = theme.get("text", "#E6E6E6")
        border = theme.get("border", "#30363D")
        self.browser.setStyleSheet(f"""
            QTextBrowser {{
                background-color: {bg};
                color: {fg};
                border: 1px solid {border};
                border-radius: 6px;
                padding: 8px;
            }}
        """)
        
        layout.addWidget(self.browser)

        btn_layout = QHBoxLayout()
        btn_layout.addStretch(1)
        close_btn = QPushButton("Close")
        close_btn.setFixedWidth(100)
        close_btn.clicked.connect(self.accept)
        btn_layout.addWidget(close_btn)
        
        layout.addLayout(btn_layout)

        self.setStyleSheet(f"""
            QDialog {{
                background-color: {theme.get("background", "#000000")};
            }}
            QPushButton {{
                background-color: {theme.get("surface", "#1C1F26")};
                color: {fg};
                border: 1px solid {border};
                border-radius: 4px;
                padding: 6px 12px;
            }}
            QPushButton:hover {{
                background-color: {theme.get("hover", "#2A2E38")};
            }}
        """)
