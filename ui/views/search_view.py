"""
Search Mechanism (SearchView / SearchOverlay).
Implements the 9-point specification as a floating modal overlay on top of MainWindow.
"""

from __future__ import annotations

import html
import re
from typing import Callable, Any

from PyQt6.QtCore import Qt, pyqtSignal, QTimer, QRect, QSize, QPoint
from PyQt6.QtGui import QPixmap, QColor, QPainter, QCursor, QAction
from PyQt6.QtWidgets import (
    QWidget, QFrame, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QScrollArea, QMenu, QGraphicsDropShadowEffect, QSizePolicy,
    QAbstractItemView
)

from core.library_store import LibraryStore
from core.models import Track, Playlist
from ui.models.library_group_models import (
    build_artist_groups, build_album_groups, ArtistGroup, AlbumGroup
)
from ui.svg_icon import svg_icon, svg_pixmap, get_default_cover
from ui.theme import THEMES, DEFAULT_THEME


def highlight_text(text: str, query: str, accent_color: str) -> str:
    """Case-insensitively wrap matching substrings in HTML span tags with accent_color."""
    if not query or not text:
        return html.escape(text)
    escaped_text = html.escape(text)
    escaped_query = html.escape(query)
    pattern = re.escape(escaped_query)

    def replace_fn(match):
        return f'<span style="color: {accent_color}; font-weight: bold;">{match.group(0)}</span>'

    return re.sub(f'({pattern})', replace_fn, escaped_text, flags=re.IGNORECASE)


def rank_items(items: list[Any], query: str, name_fn: Callable[[Any], str]) -> list[Any]:
    """Sort items by:
    1. Case-insensitive prefix match (exact startswith)
    2. Case-insensitive substring match (contains)
    3. Alphabetical fallback
    """
    q_lower = query.lower().strip()
    if not q_lower:
        return []

    prefix_matches = []
    contains_matches = []

    for item in items:
        name = name_fn(item)
        if not name:
            continue
        n_lower = name.lower()
        if n_lower.startswith(q_lower):
            prefix_matches.append(item)
        elif q_lower in n_lower:
            contains_matches.append(item)

    prefix_matches.sort(key=lambda x: name_fn(x).lower())
    contains_matches.sort(key=lambda x: name_fn(x).lower())

    return prefix_matches + contains_matches


class SearchLineEdit(QLineEdit):
    """QLineEdit that emits escape_pressed when Esc is pressed."""
    escape_pressed = pyqtSignal()

    def keyPressEvent(self, event) -> None:
        if event.key() == Qt.Key.Key_Escape:
            self.escape_pressed.emit()
            event.accept()
        else:
            super().keyPressEvent(event)


class HoverLinkLabel(QLabel):
    """Clickable label that underlines text on mouse hover."""
    clicked = pyqtSignal()

    def __init__(self, text: str = "", parent=None):
        super().__init__(text, parent)
        self.setObjectName("clickableLabel")
        self.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Maximum)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setTextFormat(Qt.TextFormat.RichText)

    def set_styles(self, font_size: int, text_color: str, hover_color: str) -> None:
        self.setStyleSheet(f"""
            QLabel#clickableLabel {{
                font-size: {font_size}px;
                color: {text_color};
                background: transparent;
            }}
            QLabel#clickableLabel:hover {{
                color: {hover_color};
                text-decoration: underline;
            }}
        """)

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
        super().mousePressEvent(event)


class StaticCoverLabel(QLabel):
    """Static cover image without hover effects, pointing cursor, or click events."""
    def __init__(self, size: int = 42, parent=None):
        super().__init__(parent)
        self.setFixedSize(size, size)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)

    def set_cover(self, pixmap: QPixmap | None) -> None:
        if pixmap and not pixmap.isNull():
            self.setPixmap(pixmap)
        else:
            self.clear()


class CoverThumbButton(QFrame):
    """Square thumbnail cover button that shows a play overlay icon on mouse hover or EQ animation when playing."""
    clicked = pyqtSignal()

    def __init__(self, size: int = 42, parent=None):
        super().__init__(parent)
        self.setFixedSize(size, size)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._pixmap: QPixmap | None = None
        self._play_icon: QPixmap | None = None
        self._hovered = False
        self._row_hovered = False
        self._is_playing = False
        self._accent_color = "#61AFEF"
        self._anim_timer: QTimer | None = None

    def set_cover(self, pixmap: QPixmap | None, play_icon: QPixmap | None) -> None:
        self._pixmap = pixmap
        self._play_icon = play_icon
        self.update()

    def set_playing(self, is_playing: bool, accent_color: str = "#61AFEF") -> None:
        self._is_playing = is_playing
        self._accent_color = accent_color
        if is_playing:
            if self._anim_timer is None:
                self._anim_timer = QTimer(self)
                self._anim_timer.timeout.connect(self.update)
            if not self._anim_timer.isActive():
                self._anim_timer.start(50)
        else:
            if self._anim_timer and self._anim_timer.isActive():
                self._anim_timer.stop()
        self.update()

    def set_row_hovered(self, hovered: bool) -> None:
        if self._row_hovered != hovered:
            self._row_hovered = hovered
            self.update()

    def enterEvent(self, event) -> None:
        self._hovered = True
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:
        self._hovered = False
        self.update()
        super().leaveEvent(event)

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(event)

    def paintEvent(self, event) -> None:
        import time, math
        from PyQt6.QtCore import QRectF
        from PyQt6.QtGui import QBrush

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        if self._pixmap and not self._pixmap.isNull():
            painter.drawPixmap(0, 0, self.width(), self.height(), self._pixmap)
            
        if self._is_playing:
            painter.fillRect(self.rect(), QColor(0, 0, 0, 150))
            max_bar_h = 14
            bar_w = 3
            spacing = 2
            eq_w = 3 * bar_w + 2 * spacing
            eq_x = (self.width() - eq_w) // 2
            eq_y = (self.height() - max_bar_h) // 2

            t = time.time()
            h1 = 0.2 + 0.7 * abs(math.sin(t * 9.0))
            h2 = 0.3 + 0.6 * abs(math.sin(t * 13.0 + 1.5))
            h3 = 0.1 + 0.8 * abs(math.sin(t * 7.5 + 3.0))

            heights = [h1 * max_bar_h, h2 * max_bar_h, h3 * max_bar_h]

            painter.save()
            painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QBrush(QColor("#FFFFFF")))
            for i, h in enumerate(heights):
                x = eq_x + i * (bar_w + spacing)
                y = (eq_y + max_bar_h) - h
                painter.drawRect(QRectF(x, y, bar_w, h))
            painter.restore()
        elif self._hovered or self._row_hovered:
            painter.fillRect(self.rect(), QColor(0, 0, 0, 150))
            if self._play_icon and not self._play_icon.isNull():
                iw = self._play_icon.width()
                ih = self._play_icon.height()
                x = (self.width() - iw) // 2
                y = (self.height() - ih) // 2
                painter.drawPixmap(x, y, self._play_icon)


class BaseSearchRow(QFrame):
    """Base interactive row widget for search results."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("SearchRow")
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.setMouseTracking(True)
        self._bg_color = "transparent"
        self._hover_bg_color = "#3E4452"
        self._apply_style()

    def set_row_hovered(self, hovered: bool) -> None:
        self.setProperty("hovered", hovered)
        self.style().unpolish(self)
        self.style().polish(self)
        if hasattr(self, "cover_btn") and hasattr(self.cover_btn, "set_row_hovered"):
            self.cover_btn.set_row_hovered(hovered)
        self.update()

    def set_row_colors(self, bg: str, hover_bg: str) -> None:
        self._bg_color = bg
        self._hover_bg_color = hover_bg
        self._apply_style()

    def _apply_style(self) -> None:
        self.setStyleSheet(f"""
            QFrame#SearchRow {{
                background-color: {self._bg_color};
                border-radius: 8px;
            }}
            QFrame#SearchRow:hover, QFrame#SearchRow[hovered="true"] {{
                background-color: {self._hover_bg_color};
            }}
        """)


class TrackRow(BaseSearchRow):
    double_clicked = pyqtSignal()

    def __init__(self, track: Track, query: str, theme: dict[str, Any], cover_pix: QPixmap | None, play_pix: QPixmap | None, parent=None):
        super().__init__(parent)
        self.track = track
        self.setFixedHeight(54)
        
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 6, 12, 6)
        layout.setSpacing(12)

        self.cover_btn = CoverThumbButton(size=42, parent=self)
        self.cover_btn.set_cover(cover_pix, play_pix)
        layout.addWidget(self.cover_btn)

        text_layout = QVBoxLayout()
        text_layout.setContentsMargins(0, 0, 0, 0)
        text_layout.setSpacing(2)

        self.title_lbl = HoverLinkLabel(parent=self)
        self.title_lbl.set_styles(14, theme.get("text_primary", "#FFFFFF"), theme.get("accent", "#61AFEF"))
        self.title_lbl.setText(highlight_text(track.title, query, theme.get("accent", "#61AFEF")))
        text_layout.addWidget(self.title_lbl, 0, Qt.AlignmentFlag.AlignLeft)

        self.artist_lbls: list[HoverLinkLabel] = []
        artists = track.artists if track.artists else ["Unknown Artist"]
        artist_layout = QHBoxLayout()
        artist_layout.setContentsMargins(0, 0, 0, 0)
        artist_layout.setSpacing(0)

        for i, artist_name in enumerate(artists):
            lbl = HoverLinkLabel(parent=self)
            lbl.set_styles(12, theme.get("text_secondary", "#ABB2BF"), theme.get("accent", "#61AFEF"))
            lbl.setText(highlight_text(artist_name, query, theme.get("accent", "#61AFEF")))
            artist_layout.addWidget(lbl, 0, Qt.AlignmentFlag.AlignLeft)
            self.artist_lbls.append(lbl)

            if i < len(artists) - 1:
                comma = QLabel(", ", parent=self)
                comma.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Maximum)
                comma.setStyleSheet(f"font-size: 12px; color: {theme.get('text_secondary', '#ABB2BF')}; background: transparent;")
                artist_layout.addWidget(comma, 0, Qt.AlignmentFlag.AlignLeft)
        artist_layout.addStretch()
        text_layout.addLayout(artist_layout)

        layout.addLayout(text_layout)
        layout.addStretch()

    def enterEvent(self, event) -> None:
        self.cover_btn.set_row_hovered(True)
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:
        self.cover_btn.set_row_hovered(False)
        super().leaveEvent(event)

    def mouseDoubleClickEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.double_clicked.emit()
            event.accept()
        super().mouseDoubleClickEvent(event)


class ArtistRow(BaseSearchRow):
    double_clicked = pyqtSignal()

    def __init__(self, artist: ArtistGroup, query: str, theme: dict[str, Any], cover_pix: QPixmap | None = None, parent=None):
        super().__init__(parent)
        self.artist = artist
        self.setFixedHeight(54)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 6, 12, 6)
        layout.setSpacing(12)

        self.cover_lbl = StaticCoverLabel(size=42, parent=self)
        self.cover_lbl.set_cover(cover_pix)
        layout.addWidget(self.cover_lbl)

        self.name_lbl = HoverLinkLabel(parent=self)
        self.name_lbl.set_styles(14, theme.get("text_primary", "#FFFFFF"), theme.get("accent", "#61AFEF"))
        self.name_lbl.setText(highlight_text(artist.name, query, theme.get("accent", "#61AFEF")))
        layout.addWidget(self.name_lbl, 0, Qt.AlignmentFlag.AlignLeft)
        layout.addStretch()

    def mouseDoubleClickEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.double_clicked.emit()
            event.accept()
        super().mouseDoubleClickEvent(event)


class AlbumRow(BaseSearchRow):
    double_clicked = pyqtSignal()

    def __init__(self, album: AlbumGroup, query: str, theme: dict[str, Any], cover_pix: QPixmap | None, parent=None):
        super().__init__(parent)
        self.album = album
        self.setFixedHeight(54)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 6, 12, 6)
        layout.setSpacing(12)

        self.cover_lbl = StaticCoverLabel(size=42, parent=self)
        self.cover_lbl.set_cover(cover_pix)
        layout.addWidget(self.cover_lbl)

        text_layout = QVBoxLayout()
        text_layout.setContentsMargins(0, 0, 0, 0)
        text_layout.setSpacing(2)

        self.title_lbl = HoverLinkLabel(parent=self)
        self.title_lbl.set_styles(14, theme.get("text_primary", "#FFFFFF"), theme.get("accent", "#61AFEF"))
        self.title_lbl.setText(highlight_text(album.album_name, query, theme.get("accent", "#61AFEF")))
        text_layout.addWidget(self.title_lbl, 0, Qt.AlignmentFlag.AlignLeft)

        self.artist_lbls: list[HoverLinkLabel] = []
        artists = album.album_artists if album.album_artists else ["Unknown Artist"]
        artist_layout = QHBoxLayout()
        artist_layout.setContentsMargins(0, 0, 0, 0)
        artist_layout.setSpacing(0)

        for i, artist_name in enumerate(artists):
            lbl = HoverLinkLabel(parent=self)
            lbl.set_styles(12, theme.get("text_secondary", "#ABB2BF"), theme.get("accent", "#61AFEF"))
            lbl.setText(highlight_text(artist_name, query, theme.get("accent", "#61AFEF")))
            artist_layout.addWidget(lbl, 0, Qt.AlignmentFlag.AlignLeft)
            self.artist_lbls.append(lbl)

            if i < len(artists) - 1:
                comma = QLabel(", ", parent=self)
                comma.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Maximum)
                comma.setStyleSheet(f"font-size: 12px; color: {theme.get('text_secondary', '#ABB2BF')}; background: transparent;")
                artist_layout.addWidget(comma, 0, Qt.AlignmentFlag.AlignLeft)
        artist_layout.addStretch()
        text_layout.addLayout(artist_layout)

        layout.addLayout(text_layout)
        layout.addStretch()

    def mouseDoubleClickEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.double_clicked.emit()
            event.accept()
        super().mouseDoubleClickEvent(event)


class GenreRow(BaseSearchRow):
    double_clicked = pyqtSignal()

    def __init__(self, genre_name: str, query: str, theme: dict[str, Any], parent=None):
        super().__init__(parent)
        self.genre_name = genre_name
        self.setFixedHeight(40)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 6, 12, 6)

        self.name_lbl = HoverLinkLabel(parent=self)
        self.name_lbl.set_styles(14, theme.get("text_primary", "#FFFFFF"), theme.get("accent", "#61AFEF"))
        self.name_lbl.setText(highlight_text(genre_name, query, theme.get("accent", "#61AFEF")))
        layout.addWidget(self.name_lbl, 0, Qt.AlignmentFlag.AlignLeft)
        layout.addStretch()

    def mouseDoubleClickEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.double_clicked.emit()
            event.accept()
        super().mouseDoubleClickEvent(event)


class PlaylistRow(BaseSearchRow):
    double_clicked = pyqtSignal()

    def __init__(self, playlist: Playlist, query: str, theme: dict[str, Any], cover_pix: QPixmap | None, parent=None):
        super().__init__(parent)
        self.playlist = playlist
        self.setFixedHeight(54)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 6, 12, 6)
        layout.setSpacing(12)

        self.cover_lbl = StaticCoverLabel(size=42, parent=self)
        self.cover_lbl.set_cover(cover_pix)
        layout.addWidget(self.cover_lbl)

        self.title_lbl = HoverLinkLabel(parent=self)
        self.title_lbl.set_styles(14, theme.get("text_primary", "#FFFFFF"), theme.get("accent", "#61AFEF"))
        self.title_lbl.setText(highlight_text(playlist.name, query, theme.get("accent", "#61AFEF")))
        layout.addWidget(self.title_lbl, 0, Qt.AlignmentFlag.AlignLeft)
        layout.addStretch()

    def mouseDoubleClickEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.double_clicked.emit()
            event.accept()
        super().mouseDoubleClickEvent(event)


class SearchSectionWidget(QFrame):
    """Container for a single category section (Tracks, Artists, Albums, Genre, Playlist)."""
    def __init__(self, category_name: str, overlay: "SearchOverlay", parent=None):
        super().__init__(parent)
        self.category_name = category_name
        self.overlay = overlay
        self.items: list[Any] = []
        self.query = ""
        self._expanded = False

        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(0, 8, 0, 12)
        self.layout.setSpacing(4)

        self.header_lbl = QLabel(category_name)
        self.layout.addWidget(self.header_lbl)

        self.rows_container = QWidget()
        self.rows_layout = QVBoxLayout(self.rows_container)
        self.rows_layout.setContentsMargins(0, 0, 0, 0)
        self.rows_layout.setSpacing(2)
        self.layout.addWidget(self.rows_container)

        self.toggle_btn = QPushButton("View more")
        self.toggle_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.toggle_btn.clicked.connect(self._on_toggle_clicked)
        self.layout.addWidget(self.toggle_btn, alignment=Qt.AlignmentFlag.AlignLeft)

    def apply_theme(self, theme: dict[str, Any]) -> None:
        self.header_lbl.setStyleSheet(f"font-size: 16px; font-weight: bold; color: {theme.get('text_primary', '#FFFFFF')}; margin-bottom: 4px;")
        self.toggle_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent;
                color: {theme.get('accent', '#61AFEF')};
                border: none;
                font-size: 13px;
                font-weight: bold;
                padding: 4px 8px;
            }}
            QPushButton:hover {{
                text-decoration: underline;
            }}
        """)

    def get_rows(self) -> list[BaseSearchRow]:
        rows = []
        for i in range(self.rows_layout.count()):
            item = self.rows_layout.itemAt(i)
            if item and item.widget() and isinstance(item.widget(), BaseSearchRow):
                rows.append(item.widget())
        return rows

    def get_interactive_items(self) -> list[QWidget]:
        items: list[QWidget] = []
        for i in range(self.rows_layout.count()):
            item = self.rows_layout.itemAt(i)
            if item and item.widget() and isinstance(item.widget(), BaseSearchRow):
                items.append(item.widget())
        if self.toggle_btn.isVisible():
            items.append(self.toggle_btn)
        return items

    def set_button_focused(self, focused: bool) -> None:
        theme = self.overlay._current_theme
        accent = theme.get('accent', '#61AFEF')
        bg = theme.get('surface_hover', '#3E4452') if focused else 'transparent'
        text_dec = 'underline' if focused else 'none'
        border = f"1px solid {accent}" if focused else "none"
        self.toggle_btn.setStyleSheet(f"""
            QPushButton {{
                background: {bg};
                color: {accent};
                border: {border};
                border-radius: 4px;
                font-size: 13px;
                font-weight: bold;
                padding: 4px 8px;
                text-decoration: {text_dec};
            }}
        """)

    def update_items(self, items: list[Any], query: str, theme: dict[str, Any]) -> None:
        self.items = items
        self.query = query
        self._expanded = False
        if not items:
            self.setVisible(False)
            return
        self.setVisible(True)
        self.apply_theme(theme)
        self._render_rows(theme)

    def _on_toggle_clicked(self) -> None:
        self._expanded = not self._expanded
        self._render_rows(self.overlay._current_theme)
        if hasattr(self.overlay, "_update_row_focus"):
            self.overlay._update_row_focus()

    def _render_rows(self, theme: dict[str, Any]) -> None:
        while self.rows_layout.count():
            child = self.rows_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()

        limit = len(self.items) if self._expanded else min(5, len(self.items))
        to_show = self.items[:limit]

        play_pix = svg_pixmap("play", size=20, color="#FFFFFF")

        for item in to_show:
            row_widget = self._create_row_for_item(item, theme, play_pix)
            if row_widget:
                row_widget.set_row_colors("transparent", theme.get("surface_hover", "#3E4452"))
                self.rows_layout.addWidget(row_widget)

        if len(self.items) > 5:
            self.toggle_btn.setVisible(True)
            self.toggle_btn.setText("Show less" if self._expanded else "View more")
        else:
            self.toggle_btn.setVisible(False)

    def _create_row_for_item(self, item: Any, theme: dict[str, Any], play_pix: QPixmap) -> BaseSearchRow | None:
        if self.category_name == "Tracks":
            track: Track = item
            cover = self.overlay._get_cover_pixmap(track.path, track.has_embedded_art, size=42)
            row = TrackRow(track, self.query, theme, cover, play_pix)
            row.title_lbl.clicked.connect(lambda t=track: self.overlay.track_requested.emit(t.path))
            for i, artist_lbl in enumerate(row.artist_lbls):
                artist_name = track.artists[i] if (track.artists and i < len(track.artists)) else ""
                if artist_name:
                    artist_lbl.clicked.connect(lambda checked=False, a=artist_name: self.overlay.artist_requested.emit(a))
            row.cover_btn.clicked.connect(lambda checked=False, p=track.path: self.overlay._play_results(self.items, start_path=p))
            row.double_clicked.connect(lambda p=track.path: self.overlay._play_results(self.items, start_path=p))
            row.customContextMenuRequested.connect(lambda pos, r=row, t=track: self.overlay._show_row_context_menu(r.mapToGlobal(pos), [t]))
            return row

        elif self.category_name == "Artists":
            artist: ArtistGroup = item
            from ui.views.artists_view import get_artist_collage
            cover_pix = get_artist_collage(self.overlay.store, artist.name, 42, theme)
            row = ArtistRow(artist, self.query, theme, cover_pix)
            row.name_lbl.clicked.connect(lambda a=artist.name: self.overlay.artist_requested.emit(a))
            row.double_clicked.connect(lambda a=artist.name: self.overlay.artist_requested.emit(a))
            row.customContextMenuRequested.connect(lambda pos, r=row, t_list=artist.tracks: self.overlay._show_row_context_menu(r.mapToGlobal(pos), t_list))
            return row

        elif self.category_name == "Albums":
            album: AlbumGroup = item
            cover_path = album.tracks[0].path if album.tracks else ""
            has_art = album.tracks[0].has_embedded_art if album.tracks else False
            cover = self.overlay._get_cover_pixmap(cover_path, has_art, size=42)
            row = AlbumRow(album, self.query, theme, cover)
            row.title_lbl.clicked.connect(lambda k=album.album_key: self.overlay.album_requested.emit(k))
            row.double_clicked.connect(lambda k=album.album_key: self.overlay.album_requested.emit(k))
            for i, artist_lbl in enumerate(row.artist_lbls):
                artist_name = album.album_artists[i] if (album.album_artists and i < len(album.album_artists)) else ""
                if artist_name:
                    artist_lbl.clicked.connect(lambda checked=False, a=artist_name: self.overlay.artist_requested.emit(a))
            row.customContextMenuRequested.connect(lambda pos, r=row, t_list=album.tracks: self.overlay._show_row_context_menu(r.mapToGlobal(pos), t_list))
            return row

        elif self.category_name == "Genre":
            genre_name: str = item
            row = GenreRow(genre_name, self.query, theme)
            row.name_lbl.clicked.connect(lambda g=genre_name: self.overlay.genre_requested.emit(g))
            row.double_clicked.connect(lambda g=genre_name: self.overlay.genre_requested.emit(g))
            matching_tracks = [t for t in self.overlay.store.all_tracks() if t.genre and genre_name.lower() in [g.strip().lower() for g in t.genre.split(",")]]
            row.customContextMenuRequested.connect(lambda pos, r=row, t_list=matching_tracks: self.overlay._show_row_context_menu(r.mapToGlobal(pos), t_list))
            return row

        elif self.category_name == "Playlist":
            playlist: Playlist = item
            tracks = self.overlay.store.get_playlist_tracks(playlist.id)
            cover_path = tracks[0].path if tracks else ""
            has_art = tracks[0].has_embedded_art if tracks else False
            cover = self.overlay._get_cover_pixmap(cover_path, has_art, size=42)
            row = PlaylistRow(playlist, self.query, theme, cover)
            row.title_lbl.clicked.connect(lambda pid=playlist.id: self.overlay.playlist_requested.emit(pid))
            row.double_clicked.connect(lambda pid=playlist.id: self.overlay.playlist_requested.emit(pid))
            row.customContextMenuRequested.connect(lambda pos, r=row, t_list=tracks: self.overlay._show_row_context_menu(r.mapToGlobal(pos), t_list))
            return row

        return None


class ModalBox(QFrame):
    """Container frame that consumes clicks to prevent backdrop dismissal when clicking inside."""
    def mousePressEvent(self, event) -> None:
        event.accept()


class SearchOverlay(QFrame):
    """Floating modal search overlay on top of MainWindow."""
    track_requested = pyqtSignal(str)
    artist_requested = pyqtSignal(str)
    album_requested = pyqtSignal(str)
    genre_requested = pyqtSignal(str)
    playlist_requested = pyqtSignal(str)
    closed = pyqtSignal()

    def __init__(self, store: LibraryStore, engine: Any = None, parent=None):
        super().__init__(parent)
        self.store = store
        self.engine = engine
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self._art_cache: dict[str, QPixmap] = {}
        self._current_theme = THEMES[DEFAULT_THEME]
        self._query_text = ""
        self._focused_row_index: int = -1

        if self.engine:
            self.engine.track_changed.connect(self._on_playback_changed)
            self.engine.playback_state_changed.connect(self._on_playback_changed)

        backdrop_layout = QVBoxLayout(self)
        backdrop_layout.setContentsMargins(0, 4, 0, 20)
        backdrop_layout.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignHCenter)

        self.modal_box = ModalBox(self)
        self.modal_box.setObjectName("SearchModalBox")
        self.modal_box.setMinimumWidth(500)
        self.modal_box.setMaximumWidth(680)
        self.modal_box.setMaximumHeight(550)

        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(35)
        shadow.setColor(QColor(0, 0, 0, 180))
        shadow.setOffset(0, 10)
        self.modal_box.setGraphicsEffect(shadow)

        modal_layout = QVBoxLayout(self.modal_box)
        modal_layout.setContentsMargins(20, 20, 20, 20)
        modal_layout.setSpacing(16)

        self.no_results_lbl = QLabel("No results found", self.modal_box)
        self.no_results_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.no_results_lbl.setFixedHeight(100)
        self.no_results_lbl.setVisible(False)
        modal_layout.addWidget(self.no_results_lbl)

        self.scroll_area = QScrollArea(self.modal_box)
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll_area.setVisible(False)

        self.results_container = QWidget()
        self.results_layout = QVBoxLayout(self.results_container)
        self.results_layout.setContentsMargins(0, 0, 8, 0)
        self.results_layout.setSpacing(16)
        self.scroll_area.setWidget(self.results_container)

        modal_layout.addWidget(self.scroll_area)

        self.tracks_sec = SearchSectionWidget("Tracks", self, self.results_container)
        self.artists_sec = SearchSectionWidget("Artists", self, self.results_container)
        self.albums_sec = SearchSectionWidget("Albums", self, self.results_container)
        self.genres_sec = SearchSectionWidget("Genre", self, self.results_container)
        self.playlists_sec = SearchSectionWidget("Playlist", self, self.results_container)

        self.results_layout.addWidget(self.tracks_sec)
        self.results_layout.addWidget(self.artists_sec)
        self.results_layout.addWidget(self.albums_sec)
        self.results_layout.addWidget(self.genres_sec)
        self.results_layout.addWidget(self.playlists_sec)
        self.results_layout.addStretch()

        backdrop_layout.addWidget(self.modal_box)

        self.debounce_timer = QTimer(self)
        self.debounce_timer.setSingleShot(True)
        self.debounce_timer.timeout.connect(self._perform_search)

        self.hide()
        self.apply_theme(THEMES[DEFAULT_THEME])

    def apply_theme(self, theme: dict[str, Any]) -> None:
        self._current_theme = theme
        self.setStyleSheet(f"""
            SearchOverlay {{
                background-color: rgba(0, 0, 0, 0.5);
            }}
            QFrame#SearchModalBox {{
                background-color: {theme.get('surface', '#282C34')};
                border: 1px solid {theme.get('border', '#3E4452')};
                border-radius: 14px;
            }}
            QPushButton {{
                border: none;
                background: transparent;
                font-size: 22px;
                font-weight: bold;
                color: {theme.get('text_secondary', '#ABB2BF')};
            }}
            QPushButton:hover {{
                color: {theme.get('text_primary', '#FFFFFF')};
            }}
            QScrollArea {{
                background: transparent;
                border: none;
            }}
            QWidget {{
                background: transparent;
            }}
        """)

        self.no_results_lbl.setStyleSheet(f"font-size: 16px; color: {theme.get('text_secondary', '#ABB2BF')};")

        self.tracks_sec.apply_theme(theme)
        self.artists_sec.apply_theme(theme)
        self.albums_sec.apply_theme(theme)
        self.genres_sec.apply_theme(theme)
        self.playlists_sec.apply_theme(theme)

    def show_search(self) -> None:
        parent = self.parent()
        if parent is None:
            return
        top_y = parent.top_bar.height() if hasattr(parent, "top_bar") else 48
        self.setGeometry(0, top_y, parent.width(), parent.height() - top_y)
        self.modal_box.setFixedWidth(min(680, max(450, parent.width() - 80)))
        self.modal_box.setMaximumHeight(max(300, parent.height() - top_y - 40))
        self.show()
        self.raise_()

    def parentResized(self, size: QSize) -> None:
        parent = self.parent()
        top_y = parent.top_bar.height() if parent and hasattr(parent, "top_bar") else 48
        self.setGeometry(0, top_y, size.width(), size.height() - top_y)
        self.modal_box.setFixedWidth(min(680, max(450, size.width() - 80)))
        self.modal_box.setMaximumHeight(max(300, size.height() - top_y - 40))

    def hide_search(self) -> None:
        if not self.isVisible():
            return
        self.hide()
        self.closed.emit()

    def mousePressEvent(self, event) -> None:
        if not self.modal_box.geometry().contains(event.pos()):
            self.hide_search()
            event.accept()
        else:
            super().mousePressEvent(event)

    def keyPressEvent(self, event) -> None:
        if event.key() == Qt.Key.Key_Escape:
            self.hide_search()
            event.accept()
        elif event.key() in (Qt.Key.Key_Down, Qt.Key.Key_Tab):
            self.navigate_down()
            event.accept()
        elif event.key() in (Qt.Key.Key_Up, Qt.Key.Key_Backtab):
            self.navigate_up()
            event.accept()
        elif event.key() in (Qt.Key.Key_Enter, Qt.Key.Key_Return):
            self.execute_selected_row()
            event.accept()
        else:
            super().keyPressEvent(event)

    def set_query(self, text: str) -> None:
        self._query_text = text
        self.debounce_timer.stop()
        if not text.strip():
            self.hide_search()
            return
        if not self.isVisible():
            self.show_search()
        self.debounce_timer.start(180)

    def _perform_search(self) -> None:
        self._focused_row_index = -1
        query = self._query_text.strip()
        if not query:
            self.scroll_area.setVisible(False)
            self.no_results_lbl.setVisible(False)
            return

        all_tracks = self.store.all_tracks()
        all_artists = build_artist_groups(all_tracks)
        all_albums = build_album_groups(all_tracks)

        genre_counts: dict[str, int] = {}
        for t in all_tracks:
            if t.genre:
                for g in t.genre.split(","):
                    g_clean = g.strip()
                    if g_clean:
                        genre_counts[g_clean.title()] = 1
        all_genres = sorted(list(genre_counts.keys()))
        all_playlists = self.store.all_playlists()

        matched_tracks = rank_items(all_tracks, query, lambda t: t.title)
        matched_artists = rank_items(all_artists, query, lambda a: a.name)
        matched_albums = rank_items(all_albums, query, lambda alb: alb.album_name)
        matched_genres = rank_items(all_genres, query, lambda g: g)
        matched_playlists = rank_items(all_playlists, query, lambda p: p.name)

        total_matches = (
            len(matched_tracks) + len(matched_artists) + len(matched_albums) +
            len(matched_genres) + len(matched_playlists)
        )

        if total_matches == 0:
            self.scroll_area.setVisible(False)
            self.no_results_lbl.setVisible(True)
            return

        self.no_results_lbl.setVisible(False)
        self.scroll_area.setVisible(True)

        theme = self._current_theme
        self.tracks_sec.update_items(matched_tracks, query, theme)
        self.artists_sec.update_items(matched_artists, query, theme)
        self.albums_sec.update_items(matched_albums, query, theme)
        self.genres_sec.update_items(matched_genres, query, theme)
        self.playlists_sec.update_items(matched_playlists, query, theme)
        self._update_playback_state()

    def _on_playback_changed(self, *args) -> None:
        self._update_playback_state()

    def _update_playback_state(self) -> None:
        current_path = self.engine.get_current_track_path() if self.engine else ""
        is_playing = self.engine.is_playing() if self.engine else False

        for sec in (self.tracks_sec, self.artists_sec, self.albums_sec, self.genres_sec, self.playlists_sec):
            for row in sec.get_rows():
                if hasattr(row, "track") and hasattr(row, "cover_btn"):
                    playing = (row.track.path == current_path) and is_playing
                    row.cover_btn.set_playing(playing, self._current_theme.get("accent", "#61AFEF"))

    def _get_all_result_rows(self) -> list[QWidget]:
        items: list[QWidget] = []
        for sec in (self.tracks_sec, self.artists_sec, self.albums_sec, self.genres_sec, self.playlists_sec):
            if sec.isVisible():
                items.extend(sec.get_interactive_items())
        return items

    def _update_row_focus(self) -> None:
        items = self._get_all_result_rows()
        if not items:
            self._focused_row_index = -1
            return
        self._focused_row_index = max(0, min(self._focused_row_index, len(items) - 1))
        
        for sec in (self.tracks_sec, self.artists_sec, self.albums_sec, self.genres_sec, self.playlists_sec):
            sec.set_button_focused(False)

        for idx, item in enumerate(items):
            is_focused = (idx == self._focused_row_index)
            if isinstance(item, BaseSearchRow):
                item.set_row_hovered(is_focused)
            elif isinstance(item, QPushButton):
                for sec in (self.tracks_sec, self.artists_sec, self.albums_sec, self.genres_sec, self.playlists_sec):
                    if sec.toggle_btn == item:
                        sec.set_button_focused(is_focused)
                        break
            if is_focused:
                self.scroll_area.ensureWidgetVisible(item)

    def navigate_down(self) -> None:
        rows = self._get_all_result_rows()
        if not rows:
            return
        self._focused_row_index += 1
        if self._focused_row_index >= len(rows):
            self._focused_row_index = 0
        self._update_row_focus()

    def navigate_up(self) -> None:
        rows = self._get_all_result_rows()
        if not rows:
            return
        if self._focused_row_index <= 0:
            self._focused_row_index = len(rows) - 1
        else:
            self._focused_row_index -= 1
        self._update_row_focus()

    def execute_selected_row(self) -> None:
        items = self._get_all_result_rows()
        if not items or self._focused_row_index < 0 or self._focused_row_index >= len(items):
            return
        item = items[self._focused_row_index]
        if isinstance(item, BaseSearchRow):
            if hasattr(item, "double_clicked"):
                item.double_clicked.emit()
        elif isinstance(item, QPushButton):
            item.click()

    def _get_cover_pixmap(self, path: str, has_art: bool, size: int = 42) -> QPixmap | None:
        if not path:
            return self._get_default_cover(size)
        cache_key = f"{path}_{size}"
        if cache_key in self._art_cache:
            return self._art_cache[cache_key]
        pix = None
        if has_art:
            from core.metadata_reader import get_album_art
            dpr = self.devicePixelRatioF() if hasattr(self, "devicePixelRatioF") else 1.0
            pix = get_album_art(path, target_size=size, dpr=dpr, corner_radius=6.0)
        if not pix or pix.isNull():
            pix = self._get_default_cover(size)
        self._art_cache[cache_key] = pix
        return pix

    def _get_default_cover(self, size: int = 42) -> QPixmap:
        return get_default_cover(size, self._current_theme, corner_radius=6.0)

    def _play_results(self, items: list[Any], start_path: str | None = None) -> None:
        if not self.engine or not items:
            return
        paths = []
        for item in items:
            if isinstance(item, Track):
                if not item.file_missing:
                    paths.append(item.path)
        if not paths:
            return
        shuffle = self.engine.get_shuffle()
        self.engine.play_all(paths, shuffle=shuffle, start_track_path=start_path)

    def _show_row_context_menu(self, pos: QPoint, tracks: list[Track]) -> None:
        if not tracks:
            return
        valid_tracks = [t for t in tracks if not t.file_missing]
        if not valid_tracks:
            return

        menu = QMenu(self)
        theme = self._current_theme
        qss = f"""
            QMenu {{
                background-color: {theme.get('surface', '#282C34')};
                color: {theme.get('text_primary', '#E5E9F0')};
                border: 1px solid {theme.get('border', '#3E4452')};
                border-radius: 6px;
                padding: 4px 0px;
            }}
            QMenu::item {{
                padding: 6px 24px 6px 12px;
            }}
            QMenu::item:selected {{
                background-color: {theme.get('surface_hover', '#3E4452')};
            }}
            QMenu::separator {{
                height: 1px;
                background: {theme.get('border', '#3E4452')};
                margin: 4px 0px;
            }}
        """
        menu.setStyleSheet(qss)

        add_queue_act = QAction("Add to Queue", self)
        add_queue_act.triggered.connect(lambda: self.engine.add_to_queue([t.path for t in valid_tracks]) if self.engine else None)
        menu.addAction(add_queue_act)

        play_next_act = QAction("Play Next", self)
        play_next_act.triggered.connect(lambda: self.engine.play_next([t.path for t in valid_tracks]) if self.engine else None)
        menu.addAction(play_next_act)

        menu.addSeparator()

        add_pl_menu = QMenu("Add to Playlist", self)
        add_pl_menu.setStyleSheet(qss)

        fav_act = QAction("Favorites", self)
        fav_act.triggered.connect(lambda: [self.store.set_track_favorited(t.path, True) for t in valid_tracks])
        add_pl_menu.addAction(fav_act)

        custom_pls = [p for p in self.store.all_playlists() if not p.id.startswith("smart_")]
        if custom_pls:
            add_pl_menu.addSeparator()
            for pl in custom_pls:
                act = QAction(pl.name, self)
                act.triggered.connect(lambda checked, pid=pl.id: self.store.add_tracks_to_playlist(pid, [t.path for t in valid_tracks]))
                add_pl_menu.addAction(act)

        menu.addMenu(add_pl_menu)
        menu.exec(pos)
