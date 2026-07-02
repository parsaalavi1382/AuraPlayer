"""
AlbumEditorDialog: Dialog window for bulk editing album metadata,
including album cover, album name, album artists, genres, and release year.
Applies changes to all tracks belonging to the album.
"""

from __future__ import annotations

import os
from typing import Optional, List

from PyQt6.QtCore import Qt, QSize, QRect, QPoint, QEvent
from PyQt6.QtWidgets import (
    QDialog, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel,
    QLineEdit, QPushButton, QMessageBox
)
from PyQt6.QtGui import QFont, QPixmap

from core.library_store import LibraryStore
from core.models import Track
from core.metadata_reader import get_album_art
from core.metadata_writer import write_track_metadata
from ui.theme import THEMES, DEFAULT_THEME
from ui.svg_icon import svg_pixmap
from ui.widgets.metadata_editor_dialog import TagInputField


class AlbumEditorDialog(QDialog):
    """
    QDialog offering visual bulk tag editing for all tracks in an album,
    including album name, album artists, genre, and year, plus album art.
    """
    def __init__(self, tracks: list[Track], store: LibraryStore, parent=None):
        super().__init__(parent)
        self.tracks = tracks
        self.store = store
        self._new_cover_path: Optional[str] = None
        self._save_clicked = False

        first_track = self.tracks[0] if self.tracks else None
        album_name = first_track.album if first_track else "Unknown Album"
        self.setWindowTitle(f"Edit Album Metadata — {album_name}")
        self.setMinimumSize(560, 520)
        self.resize(580, 560)

        theme_key = self.store.cache.settings.theme
        theme = THEMES.get(theme_key, THEMES[DEFAULT_THEME])

        # Main layouts
        self.dialog_layout = QVBoxLayout(self)
        self.dialog_layout.setContentsMargins(24, 24, 24, 24)
        self.dialog_layout.setSpacing(20)

        # Content area split: horizontal layout
        content_widget = QWidget()
        content_layout = QHBoxLayout(content_widget)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(24)
        self.dialog_layout.addWidget(content_widget, stretch=1)

        # -------------------------------------------------------------
        # Left Side: Album Cover Preview & Change Button
        # -------------------------------------------------------------
        left_container = QWidget()
        left_layout = QVBoxLayout(left_container)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(12)
        left_layout.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignHCenter)

        self.cover_label = QLabel()
        self.cover_label.setFixedSize(160, 160)
        self.cover_label.setStyleSheet("border-radius: 8px; border: 1px solid var(--border); background-color: var(--surface);")

        if first_track:
            art_pixmap = get_album_art(first_track.path)
            if art_pixmap and not art_pixmap.isNull():
                scaled = art_pixmap.scaled(
                    160, 160,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
                self.cover_label.setPixmap(scaled)
            else:
                self.cover_label.setText("💿")
                self.cover_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
                self.cover_label.setFont(QFont("Segoe UI", 48))
        else:
            self.cover_label.setText("💿")
            self.cover_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.cover_label.setFont(QFont("Segoe UI", 48))

        left_layout.addWidget(self.cover_label)

        browse_btn = QPushButton("Browse Cover...")
        browse_btn.clicked.connect(self._browse_cover)
        left_layout.addWidget(browse_btn)

        content_layout.addWidget(left_container)

        # -------------------------------------------------------------
        # Right Side: Form of Fields
        # -------------------------------------------------------------
        right_container = QWidget()
        form_layout = QGridLayout(right_container)
        form_layout.setContentsMargins(0, 0, 0, 0)
        form_layout.setSpacing(12)
        form_layout.setColumnStretch(1, 1)

        row = 0

        # a) Album Name
        form_layout.addWidget(QLabel("Album Name:"), row, 0)
        self.album_edit = QLineEdit(album_name)
        form_layout.addWidget(self.album_edit, row, 1)
        row += 1

        # b) Album Artist Name with separator support
        form_layout.addWidget(QLabel("Album Artist(s):"), row, 0, Qt.AlignmentFlag.AlignTop)
        initial_artists = first_track.album_artists if first_track else []
        self.album_artists_input = TagInputField(initial_artists, "Type album artist and press ',' or Enter")
        form_layout.addWidget(self.album_artists_input, row, 1)
        row += 1

        # c) Genre like Album Artist Name
        form_layout.addWidget(QLabel("Genre(s):"), row, 0, Qt.AlignmentFlag.AlignTop)
        initial_genres = [g.strip() for g in first_track.genre.split(",") if g.strip()] if first_track else []
        self.genres_input = TagInputField(initial_genres, "Type genre and press ',' or Enter")
        form_layout.addWidget(self.genres_input, row, 1)
        row += 1

        # d) Year Released
        form_layout.addWidget(QLabel("Year Released:"), row, 0)
        initial_year = first_track.year if first_track else ""
        self.year_edit = QLineEdit(initial_year)
        form_layout.addWidget(self.year_edit, row, 1)
        row += 1

        content_layout.addWidget(right_container, stretch=1)

        # -------------------------------------------------------------
        # Save & Close Bottom Row
        # -------------------------------------------------------------
        buttons_widget = QWidget()
        buttons_layout = QHBoxLayout(buttons_widget)
        buttons_layout.setContentsMargins(0, 0, 0, 0)
        buttons_layout.setSpacing(12)

        buttons_layout.addStretch()

        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.close)
        buttons_layout.addWidget(cancel_btn)

        save_btn = QPushButton("Save")
        save_btn.setObjectName("accentButton")
        save_btn.clicked.connect(self._save_changes)
        buttons_layout.addWidget(save_btn)

        self.dialog_layout.addWidget(buttons_widget)

    def _browse_cover(self) -> None:
        from PyQt6.QtWidgets import QFileDialog
        path, _ = QFileDialog.getOpenFileName(
            self, "Select Album Cover", "", "Images (*.png *.jpg *.jpeg)"
        )
        if path:
            self._new_cover_path = path
            pixmap = QPixmap(path)
            if not pixmap.isNull():
                scaled = pixmap.scaled(
                    160, 160,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
                self.cover_label.setPixmap(scaled)

    def _save_changes(self) -> None:
        try:
            new_album = self.album_edit.text().strip()
            new_album_artists = self.album_artists_input.tags()
            new_genres = self.genres_input.tags()
            new_year = self.year_edit.text().strip()

            # Apply changes to all tracks belonging to this album
            for track in self.tracks:
                write_track_metadata(
                    filepath=track.path,
                    title=track.title,
                    artists=track.artists,
                    album=new_album,
                    album_artists=new_album_artists,
                    genres=new_genres,
                    year=new_year,
                    disc_number=track.disc_number,
                    track_number=track.track_number,
                    cover_image_path=self._new_cover_path
                )

                # Update in-memory Track object
                track.album = new_album
                track.album_artists = new_album_artists
                track.genre = ", ".join(new_genres)
                track.year = new_year
                if self._new_cover_path:
                    track.has_embedded_art = True

                self.store.cache.upsert_track(track)

            # Bulk save the cache once at the end for performance
            self.store.cache.save()

            # Emit track_updated signals
            for track in self.tracks:
                self.store.track_updated.emit(track.path)

            self._save_clicked = True
            self.accept()

        except Exception as e:
            QMessageBox.critical(
                self, "Save Failed",
                f"Could not write album changes to physical files:\n\n{str(e)}"
            )
