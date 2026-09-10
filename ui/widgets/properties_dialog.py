import os
import mutagen
from typing import Optional

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QDialog, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel,
    QPushButton, QFrame
)
from ui.widgets.aspect_label import AspectLabel
from PyQt6.QtGui import QIcon

from core.models import Track
from core.library_store import LibraryStore
from core.metadata_reader import get_album_art
from ui.theme import THEMES, DEFAULT_THEME

class PropertiesDialog(QDialog):
    """
    Read-only dialog to display track properties and technical metadata.
    """
    def __init__(self, track: Track, store: LibraryStore, parent=None):
        super().__init__(parent)
        self.track = track
        self.store = store

        self.setWindowTitle(f"Properties — {track.title}")
        
        from utils.paths import get_resource_path
        logo_path = get_resource_path("assets", "logo.png")
        if os.path.exists(logo_path):
            self.setWindowIcon(QIcon(logo_path))

        self.setMinimumSize(560, 480)
        self.resize(580, 520)

        theme_key = self.store.cache.settings.theme
        theme = THEMES.get(theme_key, THEMES[DEFAULT_THEME])
        from ui.theme import apply_theme_vars
        self.setStyleSheet(apply_theme_vars("""
            QDialog {
                background-color: var(--bg);
                color: var(--text_primary);
            }
            QLabel {
                color: var(--text_primary);
            }
        """, theme))

        self.dialog_layout = QVBoxLayout(self)
        self.dialog_layout.setContentsMargins(24, 24, 24, 24)
        self.dialog_layout.setSpacing(20)

        # -------------------------------------------------------------
        # Top Section: Album Cover & Core Info
        # -------------------------------------------------------------
        top_widget = QWidget()
        top_layout = QHBoxLayout(top_widget)
        top_layout.setContentsMargins(0, 0, 0, 0)
        top_layout.setSpacing(24)
        self.dialog_layout.addWidget(top_widget, stretch=0)

        # Left Side: Album Cover
        left_container = QWidget()
        left_layout = QVBoxLayout(left_container)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(12)
        left_layout.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignHCenter)

        self.cover_label = AspectLabel()
        self.cover_label.setFixedSize(180, 180)
        self.cover_label.setScaledContents(True)
        self.cover_label.setStyleSheet("border-radius: 8px; border: 1px solid var(--border); background-color: var(--surface);")

        dpr = self.devicePixelRatioF() if hasattr(self, "devicePixelRatioF") else 1.0
        art_pixmap = get_album_art(self.track.path, target_size=180, dpr=dpr, corner_radius=8.0)
        if art_pixmap and not art_pixmap.isNull():
            self.cover_label.setPixmap(art_pixmap)
        else:
            from ui.svg_icon import get_default_cover
            self.cover_label.setPixmap(get_default_cover(180, theme, corner_radius=8.0))

        left_layout.addWidget(self.cover_label)
        top_layout.addWidget(left_container)

        # Right Side: Core Info Form
        right_container = QWidget()
        form_layout = QGridLayout(right_container)
        form_layout.setContentsMargins(0, 0, 0, 0)
        form_layout.setSpacing(12)
        form_layout.setColumnStretch(1, 1)
        
        row = 0
        def add_row(layout, label_text, value_text):
            nonlocal row
            if not value_text or value_text == "Unknown" or value_text == "—":
                return
            lbl = QLabel(label_text)
            lbl.setStyleSheet("color: var(--text_secondary);")
            val = QLabel(str(value_text))
            val.setStyleSheet("color: var(--text_primary); font-weight: bold;")
            val.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            val.setWordWrap(True)
            layout.addWidget(lbl, row, 0, Qt.AlignmentFlag.AlignTop)
            layout.addWidget(val, row, 1, Qt.AlignmentFlag.AlignTop)
            row += 1

        # Format duration
        mins = int(self.track.duration // 60)
        secs = int(self.track.duration % 60)
        duration_str = f"{mins}:{secs:02d}"

        add_row(form_layout, "Name:", self.track.title)
        add_row(form_layout, "Artist(s):", ", ".join(self.track.artists) if self.track.artists else "")
        add_row(form_layout, "Album:", self.track.album)
        add_row(form_layout, "Duration:", duration_str)
        add_row(form_layout, "Genre(s):", self.track.genre)

        top_layout.addWidget(right_container)

        # -------------------------------------------------------------
        # Divider
        # -------------------------------------------------------------
        divider1 = QFrame()
        divider1.setFrameShape(QFrame.Shape.HLine)
        divider1.setStyleSheet("background-color: var(--border);")
        self.dialog_layout.addWidget(divider1)

        # -------------------------------------------------------------
        # Tag Info Section
        # -------------------------------------------------------------
        tag_container = QWidget()
        tag_layout = QGridLayout(tag_container)
        tag_layout.setContentsMargins(0, 0, 0, 0)
        tag_layout.setSpacing(12)
        tag_layout.setColumnStretch(1, 1)
        
        row = 0
        
        # Album Artist(s)
        if self.track.album_artists:
            add_row(tag_layout, "Album Artist(s):", ", ".join(self.track.album_artists))
            
        # Track number / Disc number
        track_disc_str = ""
        if self.track.track_number > 0:
            track_disc_str += f"Track {self.track.track_number}"
        if self.track.disc_number > 0:
            if track_disc_str:
                track_disc_str += " / "
            track_disc_str += f"Disc {self.track.disc_number}"
            
        add_row(tag_layout, "Track / Disc:", track_disc_str)
        add_row(tag_layout, "Year:", self.track.year)
        
        if row > 0:
            self.dialog_layout.addWidget(tag_container)
            divider2 = QFrame()
            divider2.setFrameShape(QFrame.Shape.HLine)
            divider2.setStyleSheet("background-color: var(--border);")
            self.dialog_layout.addWidget(divider2)

        # -------------------------------------------------------------
        # Technical / File Info Section
        # -------------------------------------------------------------
        tech_container = QWidget()
        tech_layout = QGridLayout(tech_container)
        tech_layout.setContentsMargins(0, 0, 0, 0)
        tech_layout.setSpacing(12)
        tech_layout.setColumnStretch(1, 1)
        
        row = 0
        
        if not self.track.file_missing:
            try:
                audio = mutagen.File(self.track.path)
                if audio is not None and audio.info is not None:
                    # Format
                    ext = os.path.splitext(self.track.path)[1][1:].upper()
                    if ext:
                        add_row(tech_layout, "Format:", ext)
                        
                    # Bitrate
                    bitrate = getattr(audio.info, "bitrate", 0)
                    if bitrate:
                        add_row(tech_layout, "Bitrate:", f"{bitrate // 1000} kbps")
                        
                    # Sample Rate
                    sample_rate = getattr(audio.info, "sample_rate", 0)
                    if sample_rate:
                        add_row(tech_layout, "Sample rate:", f"{sample_rate} Hz")
                        
                    # Channels
                    channels = getattr(audio.info, "channels", 0)
                    if channels:
                        add_row(tech_layout, "Channels:", str(channels))
                        
                    # File size
                    file_size = os.path.getsize(self.track.path)
                    add_row(tech_layout, "File size:", self._format_size(file_size))
                    
                    # File path
                    add_row(tech_layout, "File path:", self.track.path)
                    
            except Exception:
                pass # Skip technical info on error
                
            if row > 0:
                self.dialog_layout.addWidget(tech_container)
                
        self.dialog_layout.addStretch(1)
        
        # -------------------------------------------------------------
        # Bottom Buttons
        # -------------------------------------------------------------
        button_layout = QHBoxLayout()
        button_layout.addStretch()
        
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.accept)
        close_btn.setMinimumWidth(100)
        button_layout.addWidget(close_btn)
        
        self.dialog_layout.addLayout(button_layout)
        
    def _format_size(self, size_bytes: int) -> str:
        if size_bytes < 1024:
            return f"{size_bytes} B"
        elif size_bytes < 1024 * 1024:
            return f"{size_bytes / 1024:.1f} KB"
        elif size_bytes < 1024 * 1024 * 1024:
            return f"{size_bytes / (1024 * 1024):.1f} MB"
        else:
            return f"{size_bytes / (1024 * 1024 * 1024):.1f} GB"
