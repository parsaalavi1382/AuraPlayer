"""
MetadataEditorDialog: Dialogue window for editing track tagging/metadata,
including tags (artists, album artists, genres) using custom chip widgets
and writing changes back to physical files via mutagen.
"""

from __future__ import annotations

import os
from typing import Optional, List

from PyQt6.QtCore import Qt, QSize, QRect, QPoint, QEvent
from PyQt6.QtWidgets import (
    QDialog, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel,
    QLineEdit, QPushButton, QSpinBox, QMessageBox, QFrame, QLayout, QLayoutItem, QSizePolicy
)
from PyQt6.QtGui import QFont, QPixmap

from core.library_store import LibraryStore
from core.models import Track
from core.metadata_reader import get_album_art
from core.metadata_writer import write_track_metadata
from ui.theme import THEMES, DEFAULT_THEME
from ui.svg_icon import svg_pixmap


class FlowLayout(QLayout):
    """A standard custom wrapping FlowLayout for Qt widgets (such as chips/tags)."""
    def __init__(self, parent=None, margin=0, hspacing=6, vspacing=6):
        super().__init__(parent)
        self._items: list[QLayoutItem] = []
        self._hspacing = hspacing
        self._vspacing = vspacing
        self.setContentsMargins(margin, margin, margin, margin)

    def __del__(self):
        del self._items

    def addItem(self, item: QLayoutItem) -> None:
        self._items.append(item)

    def horizontalSpacing(self) -> int:
        return self._hspacing

    def verticalSpacing(self) -> int:
        return self._vspacing

    def count(self) -> int:
        return len(self._items)

    def itemAt(self, index: int) -> QLayoutItem | None:
        if 0 <= index < len(self._items):
            return self._items[index]
        return None

    def takeAt(self, index: int) -> QLayoutItem | None:
        if 0 <= index < len(self._items):
            return self._items.pop(index)
        return None

    def expandingDirections(self) -> Qt.Orientation:
        return Qt.Orientation(0)

    def hasHeightForWidth(self) -> bool:
        return True

    def heightForWidth(self, width: int) -> int:
        return self._do_layout(QRect(0, 0, width, 0), True)

    def setGeometry(self, rect: QRect) -> None:
        super().setGeometry(rect)
        self._do_layout(rect, False)

    def sizeHint(self) -> QSize:
        return self.minimumSize()

    def minimumSize(self) -> QSize:
        size = QSize()
        for item in self._items:
            size = size.expandedTo(item.minimumSize())
        margins = self.contentsMargins()
        size += QSize(margins.left() + margins.right(), margins.top() + margins.bottom())
        return size

    def _do_layout(self, rect: QRect, test_only: bool) -> int:
        margins = self.contentsMargins()
        x = rect.x() + margins.left()
        y = rect.y() + margins.top()
        line_height = 0

        for item in self._items:
            wid = item.widget()
            space_x = self.horizontalSpacing()
            space_y = self.verticalSpacing()
            next_x = x + item.sizeHint().width() + space_x
            if next_x - space_x > rect.right() - margins.right() and line_height > 0:
                x = rect.x() + margins.left()
                y = y + line_height + space_y
                next_x = x + item.sizeHint().width() + space_x
                line_height = 0

            if not test_only:
                item.setGeometry(QRect(QPoint(x, y), item.sizeHint()))

            x = next_x
            line_height = max(line_height, item.sizeHint().height())

        return y + line_height - rect.y() + margins.bottom()


class TagItem(QFrame):
    """An elegant Tag/Chip widget displaying a name and a small close button."""
    def __init__(self, text: str, on_remove, parent=None):
        super().__init__(parent)
        self.text = text
        self.on_remove = on_remove

        layout = QHBoxLayout(self)
        layout.setContentsMargins(6, 2, 6, 2)
        layout.setSpacing(6)

        label = QLabel(text)
        label.setStyleSheet("color: var(--text_primary); font-size: 12px; border: none; background: transparent; padding: 0;")

        self.btn = QPushButton("✕")
        self.btn.setFixedSize(14, 14)
        self.btn.setStyleSheet("""
            QPushButton {
                border: none;
                background: transparent;
                color: var(--text_secondary);
                font-size: 10px;
                font-weight: bold;
                padding: 0;
            }
            QPushButton:hover {
                color: var(--accent);
            }
        """)
        self.btn.clicked.connect(lambda: self.on_remove(self))

        layout.addWidget(label)
        layout.addWidget(self.btn)

        self.setStyleSheet("""
            QFrame {
                background-color: var(--surface);
                border: 1px solid var(--border);
                border-radius: 4px;
            }
        """)


class TagInputField(QWidget):
    """
    A custom tag chip input field that supports split-on-comma instantly,
    split-on-enter, and split-on-focus-out.
    """
    def __init__(self, tags: list[str] = None, placeholder: str = "", parent=None):
        super().__init__(parent)
        self._tags = list(tags) if tags else []

        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(0, 0, 0, 0)
        self.main_layout.setSpacing(4)

        # Tags container
        self.tags_container = QWidget()
        self.tags_layout = FlowLayout(self.tags_container, margin=0, hspacing=6, vspacing=6)
        self.main_layout.addWidget(self.tags_container)

        # Text Input
        self.input_edit = QLineEdit()
        self.input_edit.setPlaceholderText(placeholder)
        self.main_layout.addWidget(self.input_edit)

        self.input_edit.textChanged.connect(self._on_text_changed)
        self.input_edit.returnPressed.connect(self._on_enter_pressed)
        self.input_edit.installEventFilter(self)

        self._rebuild_tags_ui()

    def tags(self) -> list[str]:
        return list(self._tags)

    def set_tags(self, tags: list[str]) -> None:
        self._tags = list(tags)
        self._rebuild_tags_ui()

    def _on_text_changed(self, text: str) -> None:
        if "," in text:
            parts = text.split(",")
            to_add = parts[:-1]
            remaining = parts[-1]

            added_any = False
            for p in to_add:
                val = p.strip()
                if val and val not in self._tags:
                    self._tags.append(val)
                    added_any = True

            if added_any:
                self._rebuild_tags_ui()

            self.input_edit.blockSignals(True)
            self.input_edit.setText(remaining)
            self.input_edit.blockSignals(False)

    def _on_enter_pressed(self) -> None:
        text = self.input_edit.text()
        if text:
            parts = text.split(",")
            added_any = False
            for p in parts:
                val = p.strip()
                if val and val not in self._tags:
                    self._tags.append(val)
                    added_any = True
            if added_any:
                self._rebuild_tags_ui()
            self.input_edit.clear()

    def eventFilter(self, obj, event) -> bool:
        if obj == self.input_edit and event.type() == QEvent.Type.FocusOut:
            self._on_enter_pressed()
        return super().eventFilter(obj, event)

    def _rebuild_tags_ui(self) -> None:
        while self.tags_layout.count():
            item = self.tags_layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()

        for tag in self._tags:
            item_widget = TagItem(tag, self._remove_tag)
            self.tags_layout.addWidget(item_widget)

        self.tags_container.setVisible(len(self._tags) > 0)

    def _remove_tag(self, tag_item_widget: TagItem) -> None:
        tag_text = tag_item_widget.text
        if tag_text in self._tags:
            self._tags.remove(tag_text)
        tag_item_widget.deleteLater()

        if not self._tags:
            self.tags_container.setVisible(False)


class MetadataEditorDialog(QDialog):
    """
    QDialog offering visual tag/chip-based editing for all requested metadata fields,
    and writing them back using mutagen.
    """
    def __init__(self, track: Track, store: LibraryStore, parent=None):
        super().__init__(parent)
        self.track = track
        self.store = store
        self._new_cover_path: Optional[str] = None
        self._save_clicked = False

        self.setWindowTitle(f"Edit Metadata — {os.path.basename(track.path)}")
        
        from PyQt6.QtGui import QIcon
        logo_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "assets", "logo.png")
        if os.path.exists(logo_path):
            self.setWindowIcon(QIcon(logo_path))

        self.setMinimumSize(560, 620)
        self.resize(580, 660)

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

        art_pixmap = get_album_art(self.track.path)
        if art_pixmap and not art_pixmap.isNull():
            scaled = art_pixmap.scaled(
                160, 160,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            self.cover_label.setPixmap(scaled)
        else:
            from ui.svg_icon import get_default_cover
            self.cover_label.setPixmap(get_default_cover(160, theme, corner_radius=8.0))

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

        # a) Track Name
        form_layout.addWidget(QLabel("Track Title:"), row, 0)
        self.title_edit = QLineEdit(self.track.title)
        form_layout.addWidget(self.title_edit, row, 1)
        row += 1

        # b) Artist Name
        form_layout.addWidget(QLabel("Artist(s):"), row, 0, Qt.AlignmentFlag.AlignTop)
        self.artists_input = TagInputField(self.track.artists, "Type artist and press ',' or Enter")
        form_layout.addWidget(self.artists_input, row, 1)
        row += 1

        # c) Album Name
        form_layout.addWidget(QLabel("Album Title:"), row, 0)
        self.album_edit = QLineEdit(self.track.album)
        form_layout.addWidget(self.album_edit, row, 1)
        row += 1

        # d) Album Artist
        form_layout.addWidget(QLabel("Album Artist(s):"), row, 0, Qt.AlignmentFlag.AlignTop)
        self.album_artists_input = TagInputField(self.track.album_artists, "Type album artist and press ',' or Enter")
        form_layout.addWidget(self.album_artists_input, row, 1)
        row += 1

        # e) Genre
        form_layout.addWidget(QLabel("Genre(s):"), row, 0, Qt.AlignmentFlag.AlignTop)
        orig_genres = [g.strip() for g in self.track.genre.split(",") if g.strip()]
        self.genres_input = TagInputField(orig_genres, "Type genre and press ',' or Enter")
        form_layout.addWidget(self.genres_input, row, 1)
        row += 1

        # f) Album Year
        form_layout.addWidget(QLabel("Release Year:"), row, 0)
        self.year_edit = QLineEdit(self.track.year)
        form_layout.addWidget(self.year_edit, row, 1)
        row += 1

        # g) Disc Number & Track Number side by side
        form_layout.addWidget(QLabel("Disc & Track #:"), row, 0)
        
        numbers_widget = QWidget()
        numbers_layout = QHBoxLayout(numbers_widget)
        numbers_layout.setContentsMargins(0, 0, 0, 0)
        numbers_layout.setSpacing(16)

        # Disc
        disc_container = QWidget()
        disc_layout = QHBoxLayout(disc_container)
        disc_layout.setContentsMargins(0, 0, 0, 0)
        disc_layout.setSpacing(6)
        
        disc_icon = QLabel()
        disc_icon.setPixmap(svg_pixmap("disc", theme["text_secondary"], 16))
        self.disc_spin = QSpinBox()
        self.disc_spin.setRange(0, 99)
        self.disc_spin.setValue(self.track.disc_number)
        
        disc_layout.addWidget(disc_icon)
        disc_layout.addWidget(self.disc_spin)
        numbers_layout.addWidget(disc_container, stretch=1)

        # Track
        track_container = QWidget()
        track_layout = QHBoxLayout(track_container)
        track_layout.setContentsMargins(0, 0, 0, 0)
        track_layout.setSpacing(6)
        
        track_icon = QLabel("#")
        track_icon.setFont(QFont("Segoe UI", 13, QFont.Weight.Bold))
        track_icon.setStyleSheet("color: var(--text_secondary);")
        
        self.track_spin = QSpinBox()
        self.track_spin.setRange(0, 999)
        orig_track_no = self.track.track_number if self.track.track_number is not None else 0
        self.track_spin.setValue(orig_track_no)
        self.track_spin.setSpecialValueText("—")
        
        track_layout.addWidget(track_icon)
        track_layout.addWidget(self.track_spin)
        numbers_layout.addWidget(track_container, stretch=1)

        form_layout.addWidget(numbers_widget, row, 1)
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

    def _has_changes(self) -> bool:
        if self._new_cover_path is not None:
            return True
        if self.title_edit.text().strip() != self.track.title:
            return True
        if self.artists_input.tags() != self.track.artists:
            return True
        if self.album_edit.text().strip() != self.track.album:
            return True
        if self.album_artists_input.tags() != self.track.album_artists:
            return True
        orig_genres = [g.strip() for g in self.track.genre.split(",") if g.strip()]
        if self.genres_input.tags() != orig_genres:
            return True
        if self.year_edit.text().strip() != self.track.year:
            return True
        if self.disc_spin.value() != self.track.disc_number:
            return True
        orig_track_no = self.track.track_number if self.track.track_number is not None else 0
        if self.track_spin.value() != orig_track_no:
            return True
        return False

    def _save_changes(self) -> None:
        try:
            new_title = self.title_edit.text().strip()
            new_artists = self.artists_input.tags()
            new_album = self.album_edit.text().strip()
            new_album_artists = self.album_artists_input.tags()
            new_genres = self.genres_input.tags()
            new_year = self.year_edit.text().strip()
            new_disc = self.disc_spin.value()
            new_track = self.track_spin.value() if self.track_spin.value() > 0 else None

            # Write to the physical audio file first
            write_track_metadata(
                filepath=self.track.path,
                title=new_title,
                artists=new_artists,
                album=new_album,
                album_artists=new_album_artists,
                genres=new_genres,
                year=new_year,
                disc_number=new_disc,
                track_number=new_track,
                cover_image_path=self._new_cover_path
            )

            # Update the in-memory Track object
            self.track.title = new_title
            self.track.artists = new_artists
            self.track.album = new_album
            self.track.album_artists = new_album_artists
            self.track.genre = ", ".join(new_genres)
            self.track.year = new_year
            self.track.disc_number = new_disc
            self.track.track_number = new_track
            if self._new_cover_path:
                self.track.has_embedded_art = True

            # Trigger immediate reload across the application views
            self._save_clicked = True
            self.store.update_track(self.track)
            self.accept()

        except Exception as e:
            QMessageBox.critical(
                self, "Save Failed",
                f"Could not write changes to the original audio file:\n\n{str(e)}"
            )

    def closeEvent(self, event) -> None:
        if self._save_clicked:
            event.accept()
            return

        if self._has_changes():
            reply = QMessageBox.question(
                self, "Discard Changes?",
                "Are you sure? Changes will be lost.",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No
            )
            if reply == QMessageBox.StandardButton.Yes:
                event.accept()
            else:
                event.ignore()
        else:
            event.accept()
