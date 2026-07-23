"""
Playlists tab view: displays non-removable smart playlists and customizable
playlists in a responsive, beautifully-styled layout matching the original designs.
"""

from __future__ import annotations

import os
from PyQt6.QtCore import Qt, pyqtSignal, QRectF, QPoint
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QScrollArea,
    QGridLayout, QInputDialog, QMessageBox, QSizePolicy, QMenu
)
from PyQt6.QtGui import QPainter, QPainterPath, QPixmap, QColor, QFont, QAction, QPen

from core.library_store import LibraryStore
from ui.theme import THEMES, DEFAULT_THEME
from ui.svg_icon import get_default_cover


def get_playlist_collage(store: LibraryStore, playlist_id: str, size: int = 160, theme: dict = None) -> QPixmap:
    # 1. Check for custom cover path first
    if not playlist_id.startswith("smart_"):
        pl_obj = store.get_playlist(playlist_id)
        if pl_obj and pl_obj.cover_path and os.path.exists(pl_obj.cover_path):
            pix = QPixmap(pl_obj.cover_path)
            if not pix.isNull():
                return pix.scaled(
                    size, size,
                    Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                    Qt.TransformationMode.SmoothTransformation
                )

    # 2. Query tracks
    tracks = store.get_playlist_tracks(playlist_id)
    distinct_pixmaps = []
    seen_albums = set()
    for t in tracks:
        if t.has_embedded_art:
            from core.metadata_reader import get_album_art
            pix = get_album_art(t.path)
            if pix and not pix.isNull():
                album_key = t.album_key
                if album_key not in seen_albums:
                    seen_albums.add(album_key)
                    distinct_pixmaps.append(pix)
                    if len(distinct_pixmaps) == 4:
                        break

    collage = QPixmap(size, size)
    collage.fill(Qt.GlobalColor.transparent)
    painter = QPainter(collage)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)

    # Clip to rounded rect with 12px corners
    path = QPainterPath()
    path.addRoundedRect(QRectF(0, 0, size, size), 12.0, 12.0)
    painter.setClipPath(path)

    num_covers = len(distinct_pixmaps)
    if num_covers == 0:
        painter.end()
        return get_default_cover(size, theme, corner_radius=12.0)
    elif num_covers == 1:
        first_pix = distinct_pixmaps[0]
        scaled = first_pix.scaled(
            size, size,
            Qt.AspectRatioMode.KeepAspectRatioByExpanding,
            Qt.TransformationMode.SmoothTransformation
        )
        if scaled.width() != size or scaled.height() != size:
            x = max(0, (scaled.width() - size) // 2)
            y = max(0, (scaled.height() - size) // 2)
            scaled = scaled.copy(x, y, size, size)
        painter.drawPixmap(0, 0, scaled)
    elif num_covers == 2 or num_covers == 3:
        # Show two album covers split vertically (left half and right half)
        half_width = size // 2
        
        # Cover 1: Left half
        pix1 = distinct_pixmaps[0]
        scaled1 = pix1.scaled(
            half_width, size,
            Qt.AspectRatioMode.KeepAspectRatioByExpanding,
            Qt.TransformationMode.SmoothTransformation
        )
        if scaled1.width() != half_width or scaled1.height() != size:
            x = max(0, (scaled1.width() - half_width) // 2)
            y = max(0, (scaled1.height() - size) // 2)
            scaled1 = scaled1.copy(x, y, half_width, size)
        painter.drawPixmap(0, 0, scaled1)
        
        # Cover 2: Right half
        pix2 = distinct_pixmaps[1]
        scaled2 = pix2.scaled(
            half_width, size,
            Qt.AspectRatioMode.KeepAspectRatioByExpanding,
            Qt.TransformationMode.SmoothTransformation
        )
        if scaled2.width() != half_width or scaled2.height() != size:
            x = max(0, (scaled2.width() - half_width) // 2)
            y = max(0, (scaled2.height() - size) // 2)
            scaled2 = scaled2.copy(x, y, half_width, size)
        painter.drawPixmap(half_width, 0, scaled2)
    else:
        # Show four album covers (2x2 grid)
        half_size = size // 2
        coords = [
            (0, 0),
            (half_size, 0),
            (0, half_size),
            (half_size, half_size)
        ]
        for i, pix in enumerate(distinct_pixmaps[:4]):
            scaled = pix.scaled(
                half_size, half_size,
                Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                Qt.TransformationMode.SmoothTransformation
            )
            if scaled.width() != half_size or scaled.height() != half_size:
                x = max(0, (scaled.width() - half_size) // 2)
                y = max(0, (scaled.height() - half_size) // 2)
                scaled = scaled.copy(x, y, half_size, half_size)
            x, y = coords[i]
            painter.drawPixmap(x, y, scaled)

    painter.end()
    return collage


def get_smart_playlist_cover(playlist_id: str, size: int = 160, theme_key: str = "dark") -> QPixmap:
    is_light = (theme_key == "light")
    
    # Select colors
    if is_light:
        if playlist_id == "smart_favorites":
            bg = "#FCE8E6"
            fg = "#C53929"
        elif playlist_id == "smart_recently_added":
            bg = "#FEF7E0"
            fg = "#B06000"
        elif playlist_id == "smart_recently_played":
            bg = "#E8F0FE"
            fg = "#1967D2"
        else: # smart_most_played
            bg = "#E6F4EA"
            fg = "#137333"
    else:
        if playlist_id == "smart_favorites":
            bg = "#3C1E20"
            fg = "#FFA6AA"
        elif playlist_id == "smart_recently_added":
            bg = "#3D2D14"
            fg = "#FFD180"
        elif playlist_id == "smart_recently_played":
            bg = "#122047"
            fg = "#A4C2FF"
        else: # smart_most_played
            bg = "#0A3A21"
            fg = "#A3E2B6"

    # Resolve icon name
    icon_name = {
        "smart_favorites": "heart",
        "smart_recently_added": "recently_added",
        "smart_recently_played": "history",
        "smart_most_played": "trending_up"
    }.get(playlist_id, "disc")

    # Create pixmap
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)
    
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    
    # Clip to rounded rect (12px corners)
    path = QPainterPath()
    path.addRoundedRect(QRectF(0, 0, size, size), 12.0, 12.0)
    painter.setClipPath(path)
    
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QColor(bg))
    painter.drawRect(0, 0, size, size)
    
    # Load and draw SVG icon (centered, size 48px or 64px)
    icon_size = 48 if size <= 160 else 64
    from ui.svg_icon import svg_pixmap
    # Render at 4x resolution for premium, ultra-crisp display
    render_size = icon_size * 4
    if playlist_id == "smart_favorites":
        ico_px = svg_pixmap(icon_name, fg, render_size, filled=True)
    else:
        ico_px = svg_pixmap(icon_name, fg, render_size)
        
    if not ico_px.isNull():
        x = (size - icon_size) // 2
        y = (size - icon_size) // 2
        painter.drawPixmap(QRectF(x, y, icon_size, icon_size), ico_px, QRectF(ico_px.rect()))
        
    painter.end()
    return pixmap


class SmartPlaylistCard(QWidget):
    clicked = pyqtSignal(str)

    def __init__(self, playlist_id: str, title: str, track_count: int, icon_name: str, store: LibraryStore, parent=None):
        super().__init__(parent)
        self.playlist_id = playlist_id
        self.title = title
        self.track_count = track_count
        self.icon_name = icon_name
        self.store = store
        self.is_hovered = False
        self.is_drag_over = False

        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedHeight(95)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setAcceptDrops(True)

    def dragEnterEvent(self, event):
        if self.playlist_id == "smart_favorites":
            if event.mimeData().hasFormat("application/x-aura-tracks") or event.mimeData().hasText():
                event.acceptProposedAction()
                self.is_drag_over = True
                self.update()

    def dragMoveEvent(self, event):
        if self.playlist_id == "smart_favorites":
            if event.mimeData().hasFormat("application/x-aura-tracks") or event.mimeData().hasText():
                event.acceptProposedAction()

    def dragLeaveEvent(self, event):
        self.is_drag_over = False
        self.update()

    def dropEvent(self, event):
        self.is_drag_over = False
        self.update()
        if self.playlist_id == "smart_favorites":
            mime = event.mimeData()
            if mime.hasFormat("application/x-aura-tracks") or mime.hasText():
                text = mime.text()
                paths = [p.strip() for p in text.split("\n") if p.strip()]
                if paths:
                    self.store.add_tracks_to_playlist(self.playlist_id, paths)
                    event.acceptProposedAction()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self.playlist_id)

    def enterEvent(self, event):
        self.is_hovered = True
        self.update()

    def leaveEvent(self, event):
        self.is_hovered = False
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        theme_key = self.store.cache.settings.theme
        is_light = (theme_key == "light")

        # Select color palettes based on light/dark mode and playlist_id
        if is_light:
            if self.playlist_id == "smart_favorites":
                bg = "#FCE8E6" if not self.is_hovered else "#FADAD6"
                fg = "#C53929"
                fg_sec = "#8C514A"
            elif self.playlist_id == "smart_recently_added":
                bg = "#FEF7E0" if not self.is_hovered else "#FDF0CD"
                fg = "#B06000"
                fg_sec = "#80633C"
            elif self.playlist_id == "smart_recently_played":
                bg = "#E8F0FE" if not self.is_hovered else "#D2E3FC"
                fg = "#1967D2"
                fg_sec = "#527EBF"
            else: # smart_most_played
                bg = "#E6F4EA" if not self.is_hovered else "#CEEAD6"
                fg = "#137333"
                fg_sec = "#49855C"
        else:
            if self.playlist_id == "smart_favorites":
                bg = "#3C1E20" if not self.is_hovered else "#4D2628"
                fg = "#FFA6AA"
                fg_sec = "#CFA3A5"
            elif self.playlist_id == "smart_recently_added":
                bg = "#3D2D14" if not self.is_hovered else "#4E3A1A"
                fg = "#FFD180"
                fg_sec = "#D2C0A5"
            elif self.playlist_id == "smart_recently_played":
                bg = "#122047" if not self.is_hovered else "#1B2F63"
                fg = "#A4C2FF"
                fg_sec = "#8B97AE"
            else: # smart_most_played
                bg = "#0A3A21" if not self.is_hovered else "#0F5230"
                fg = "#A3E2B6"
                fg_sec = "#8B97AE"

        # Draw rounded card background
        painter.save()
        if getattr(self, "is_drag_over", False):
            theme_key = self.store.cache.settings.theme
            theme = THEMES.get(theme_key, THEMES[DEFAULT_THEME])
            accent = theme.get("accent", "#6C5CE7")
            painter.setPen(QPen(QColor(accent), 2))
        else:
            painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(bg))
        painter.drawRoundedRect(QRectF(self.rect()).adjusted(1, 1, -1, -1), 12.0, 12.0)
        painter.restore()

        # Draw icon
        from ui.svg_icon import svg_pixmap
        if self.playlist_id == "smart_favorites":
            ico_px = svg_pixmap(self.icon_name, fg, 96, filled=True)
        else:
            ico_px = svg_pixmap(self.icon_name, fg, 96)
            
        if not ico_px.isNull():
            painter.drawPixmap(QRectF(16, 12, 24, 24), ico_px, QRectF(ico_px.rect()))

        # Draw Title
        painter.save()
        font = QFont("Segoe UI", 10, QFont.Weight.DemiBold)
        painter.setFont(font)
        text_primary_color = fg if is_light else "#FFFFFF"
        painter.setPen(QColor(text_primary_color))
        painter.drawText(16, 56, self.title)
        painter.restore()

        # Draw Track Count
        painter.save()
        font = QFont("Segoe UI", 8, QFont.Weight.Normal)
        painter.setFont(font)
        tracks_text = "1 track" if self.track_count == 1 else f"{self.track_count} tracks"
        painter.setPen(QColor(fg_sec))
        painter.drawText(16, 74, tracks_text)
        painter.restore()


class CustomPlaylistRow(QWidget):
    clicked = pyqtSignal(str)
    rename_requested = pyqtSignal(str)
    delete_requested = pyqtSignal(str)

    def __init__(self, playlist_id: str, name: str, track_count: int, store: LibraryStore, parent=None):
        super().__init__(parent)
        self.playlist_id = playlist_id
        self.name = name
        self.track_count = track_count
        self.store = store
        self.is_hovered = False
        self.is_drag_over = False

        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedHeight(64)
        self.setAcceptDrops(True)

        # Layout
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 6, 8, 6)
        layout.setSpacing(12)

        # Thumbnail cover
        self.cover_label = QLabel()
        self.cover_label.setFixedSize(52, 52)
        layout.addWidget(self.cover_label)

        # Text labels layout
        text_layout = QVBoxLayout()
        text_layout.setSpacing(2)
        text_layout.setContentsMargins(0, 4, 0, 4)

        theme_key = self.store.cache.settings.theme
        theme = THEMES.get(theme_key, THEMES[DEFAULT_THEME])

        self.title_label = QLabel(self.name)
        self.title_label.setStyleSheet(f"color: {theme['text_primary']}; font-size: 14px; font-weight: 600; background: transparent;")
        text_layout.addWidget(self.title_label)

        tracks_text = "1 track" if self.track_count == 1 else f"{self.track_count} tracks"
        self.tracks_label = QLabel(tracks_text)
        self.tracks_label.setStyleSheet(f"color: {theme['text_secondary']}; font-size: 12px; background: transparent;")
        text_layout.addWidget(self.tracks_label)

        layout.addLayout(text_layout)
        layout.addStretch()

        self.refresh_cover()

    def dragEnterEvent(self, event):
        if event.mimeData().hasFormat("application/x-aura-tracks") or event.mimeData().hasText():
            event.acceptProposedAction()
            self.is_drag_over = True
            self.update()

    def dragMoveEvent(self, event):
        if event.mimeData().hasFormat("application/x-aura-tracks") or event.mimeData().hasText():
            event.acceptProposedAction()

    def dragLeaveEvent(self, event):
        self.is_drag_over = False
        self.update()

    def dropEvent(self, event):
        self.is_drag_over = False
        self.update()
        mime = event.mimeData()
        if mime.hasFormat("application/x-aura-tracks") or mime.hasText():
            text = mime.text()
            paths = [p.strip() for p in text.split("\n") if p.strip()]
            if paths:
                self.store.add_tracks_to_playlist(self.playlist_id, paths)
                event.acceptProposedAction()

    def refresh_cover(self):
        theme_key = self.store.cache.settings.theme
        theme = THEMES.get(theme_key, THEMES[DEFAULT_THEME])
        collage_px = get_playlist_collage(self.store, self.playlist_id, size=52, theme=theme)
        self.cover_label.setPixmap(collage_px)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self.playlist_id)
        elif event.button() == Qt.MouseButton.RightButton:
            self._show_context_menu(event.globalPosition().toPoint())

    def enterEvent(self, event):
        self.is_hovered = True
        self.update()

    def leaveEvent(self, event):
        self.is_hovered = False
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        theme_key = self.store.cache.settings.theme
        theme = THEMES.get(theme_key, THEMES[DEFAULT_THEME])

        if self.is_hovered or getattr(self, "is_drag_over", False):
            painter.save()
            if getattr(self, "is_drag_over", False):
                accent = theme.get("accent", "#6C5CE7")
                painter.setPen(QPen(QColor(accent), 2))
                painter.setBrush(QColor(theme.get("surface_hover", "#262A33")))
                painter.drawRoundedRect(QRectF(self.rect()).adjusted(1, 1, -1, -1), 8.0, 8.0)
            else:
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(QColor(theme.get("surface_hover", "#262A33")))
                painter.drawRoundedRect(QRectF(self.rect()), 8.0, 8.0)
            painter.restore()

        painter.end()

    def _show_context_menu(self, global_pos):
        menu = QMenu(self)
        
        theme_key = self.store.cache.settings.theme
        theme = THEMES.get(theme_key, THEMES[DEFAULT_THEME])
        bg = theme.get("surface", "#1E222B")
        text = theme.get("text_primary", "#FFFFFF")
        border = theme.get("border", "#2E323C")
        accent = theme.get("accent", "#6C5CE7")

        qss = f"""
            QMenu {{
                background-color: {bg};
                color: {text};
                border: 1px solid {border};
                border-radius: 8px;
                padding: 4px;
            }}
            QMenu::item {{
                padding: 6px 12px;
                border-radius: 4px;
                color: {text};
            }}
            QMenu::item:selected {{
                background-color: {accent};
                color: {text};
            }}
        """
        menu.setStyleSheet(qss)
        
        rename_action = QAction("Rename Playlist", self)
        delete_action = QAction("Delete Playlist", self)
        
        menu.addAction(rename_action)
        menu.addAction(delete_action)

        rename_action.triggered.connect(lambda: self.rename_requested.emit(self.playlist_id))
        delete_action.triggered.connect(lambda: self.delete_requested.emit(self.playlist_id))

        menu.exec(global_pos)


class PlaylistsView(QWidget):
    playlist_selected = pyqtSignal(str)

    def __init__(self, store: LibraryStore, parent=None):
        super().__init__(parent)
        self.store = store
        self.smart_cards: list[SmartPlaylistCard] = []
        self.custom_rows: list[CustomPlaylistRow] = []

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        outer.addWidget(self.scroll)

        self.scroll_content = QWidget()
        self.scroll_content.setObjectName("scrollContent")
        self.scroll_layout = QVBoxLayout(self.scroll_content)
        self.scroll_layout.setContentsMargins(24, 24, 24, 24)
        self.scroll_layout.setSpacing(16)
        self.scroll.setWidget(self.scroll_content)

        # Smart Grid (2x2 / 1x4 dynamic)
        self.smart_grid = QGridLayout()
        self.smart_grid.setContentsMargins(0, 0, 0, 0)
        self.smart_grid.setSpacing(12)
        self.scroll_layout.addLayout(self.smart_grid)

        self.scroll_layout.addSpacing(8)

        # Interactive Row Header (Create Playlist and Stats)
        self.header_layout = QHBoxLayout()
        self.header_layout.setContentsMargins(8, 8, 8, 8)

        # "+ Create Playlist" button
        self.create_btn = QPushButton("+ Create Playlist")
        self.create_btn.setObjectName("textButton")
        self.create_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.create_btn.clicked.connect(self._on_create_playlist)
        self.header_layout.addWidget(self.create_btn)

        self.header_layout.addStretch()

        self.stats_lbl = QLabel("0 playlists")
        self.stats_lbl.setStyleSheet("font-size: 13px; font-weight: normal; background: transparent;")
        self.header_layout.addWidget(self.stats_lbl)

        self.scroll_layout.addLayout(self.header_layout)

        # Custom empty state
        self.custom_empty_label = QLabel("No custom playlists yet. Click '+ Create Playlist' to start.")
        self.custom_empty_label.setObjectName("emptyStateSubtitle")
        self.scroll_layout.addWidget(self.custom_empty_label)

        # Custom playlists list (vertical layout)
        self.custom_list_widget = QWidget()
        self.custom_list_layout = QVBoxLayout(self.custom_list_widget)
        self.custom_list_layout.setContentsMargins(0, 0, 0, 0)
        self.custom_list_layout.setSpacing(4)
        self.scroll_layout.addWidget(self.custom_list_widget)

        self.scroll_layout.addStretch()

        self.store.playlists_changed.connect(self._on_playlists_changed)
        self.store.tracks_added.connect(self._on_playlists_changed)
        self.store.track_updated.connect(self._on_playlists_changed)
        self.store.track_removed.connect(self._on_playlists_changed)
        
        self.refresh()

    def _layout_smart_cards(self) -> None:
        if len(self.smart_cards) < 4:
            return
        
        w = self.width()
        # Breakpoint consistent with wide desktop: 850px
        use_one_row = (w > 850)
        
        # Remove from grid
        for card in self.smart_cards:
            self.smart_grid.removeWidget(card)
            
        if use_one_row:
            # 1 row, 4 columns
            for i, card in enumerate(self.smart_cards):
                self.smart_grid.addWidget(card, 0, i)
        else:
            # 2 rows, 2 columns
            for i, card in enumerate(self.smart_cards):
                row = i // 2
                col = i % 2
                self.smart_grid.addWidget(card, row, col)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._layout_smart_cards()

    def refresh(self) -> None:
        # Style self stats label based on theme
        theme_key = self.store.cache.settings.theme
        theme = THEMES.get(theme_key, THEMES[DEFAULT_THEME])
        self.stats_lbl.setStyleSheet(f"color: {theme['text_secondary']}; font-size: 13px; font-weight: normal; background: transparent;")

        # Clear existing smart cards
        while self.smart_grid.count() > 0:
            item = self.smart_grid.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()
        self.smart_cards.clear()

        # Clear existing custom rows
        while self.custom_list_layout.count() > 0:
            item = self.custom_list_layout.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()
        self.custom_rows.clear()

        # 1. SMART PLAYLISTS
        smarts = [
            ("smart_favorites", "Favorites", "heart"),
            ("smart_recently_added", "Recently added", "recently_added"),
            ("smart_recently_played", "Recently played", "history"),
            ("smart_most_played", "Most played", "trending_up"),
        ]
        
        # Instantiate smart cards
        for pl_id, name, icon_name in smarts:
            tracks = self.store.get_playlist_tracks(pl_id)
            card = SmartPlaylistCard(pl_id, name, len(tracks), icon_name, self.store, self)
            card.clicked.connect(self.playlist_selected.emit)
            self.smart_cards.append(card)

        self._layout_smart_cards()

        # 2. CUSTOM PLAYLISTS
        customs = [p for p in self.store.all_playlists() if not p.id.startswith("smart_")]
        
        # Sort customs alphabetically ascending
        customs.sort(key=lambda p: p.name.lower())
        
        for p in customs:
            tracks = self.store.get_playlist_tracks(p.id)
            row_widget = CustomPlaylistRow(p.id, p.name, len(tracks), self.store, self)
            row_widget.clicked.connect(self.playlist_selected.emit)
            row_widget.rename_requested.connect(self._on_rename_playlist)
            row_widget.delete_requested.connect(self._on_delete_playlist)
            
            self.custom_list_layout.addWidget(row_widget)
            self.custom_rows.append(row_widget)

        # Update stats
        self.stats_lbl.setText(f"{len(customs)} playlists")

        # Show / hide custom empty label
        if not customs:
            self.custom_empty_label.show()
        else:
            self.custom_empty_label.hide()

    def _on_playlists_changed(self, *_args) -> None:
        self.refresh()

    def _on_create_playlist(self) -> None:
        name, ok = QInputDialog.getText(
            self, "Create Playlist",
            "Enter playlist name:",
            text=""
        )
        if ok and name.strip():
            playlist_id = self.store.create_playlist(name.strip())
            self.playlist_selected.emit(playlist_id)

    def _on_rename_playlist(self, playlist_id: str) -> None:
        pl_obj = self.store.get_playlist(playlist_id)
        if not pl_obj:
            return
        
        name, ok = QInputDialog.getText(
            self, "Rename Playlist",
            f"Rename '{pl_obj.name}' to:",
            text=pl_obj.name
        )
        if ok and name.strip() and name.strip() != pl_obj.name:
            self.store.rename_playlist(playlist_id, name.strip())

    def _on_delete_playlist(self, playlist_id: str) -> None:
        pl_obj = self.store.get_playlist(playlist_id)
        if not pl_obj:
            return
        reply = QMessageBox.question(
            self, "Delete Playlist",
            f"Are you sure you want to delete '{pl_obj.name}'?\n\nThis cannot be undone.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            self.store.delete_playlist(playlist_id)
