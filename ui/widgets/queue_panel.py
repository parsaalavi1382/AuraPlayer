"""

QueuePanel widget: reusable panel displaying the active play queue.

Supports drag-and-drop reordering, double-click to play, right-click context menu,

resizing via left edge drag, hover highlights, and close behavior.

"""



from __future__ import annotations



import os

import math

import time

from PyQt6.QtCore import Qt, pyqtSignal, QTimer, QRect, QPoint, QRectF, QMimeData

from PyQt6.QtWidgets import (

    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QListWidget,

    QListWidgetItem, QAbstractItemView, QMenu, QFrame, QSizePolicy,

)

from PyQt6.QtGui import QFont, QAction, QPainter, QPainterPath, QBrush, QColor, QPixmap, QDrag, QPen



from core.library_store import LibraryStore

from core.models import Track

from core.metadata_reader import get_album_art





class QueueListWidget(QListWidget):

    reordered = pyqtSignal(list)
    paths_dropped = pyqtSignal(list, int)

    def __init__(self, parent=None):

        super().__init__(parent)

        self.setDragEnabled(True)
        self.setAcceptDrops(True)
        self.setDragDropMode(QAbstractItemView.DragDropMode.DragDrop)

        self.setDefaultDropAction(Qt.DropAction.MoveAction)

        self.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)

        self.setMouseTracking(True)

        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)

        self._drag_hover_row = -1

    def startDrag(self, supportedActions):
        selected_items = self.selectedItems()
        if not selected_items:
            return
        paths = []
        for item in selected_items:
            path = item.data(Qt.ItemDataRole.UserRole)
            if path:
                paths.append(path)
        if not paths:
            return
        drag = QDrag(self)
        mime = QMimeData()
        mime.setText("\n".join(paths))
        mime.setData("application/x-aura-tracks", b"1")
        drag.setMimeData(mime)
        drag.exec(Qt.DropAction.MoveAction | Qt.DropAction.CopyAction)

    def _get_drag_row(self, pos) -> int:
        item = self.itemAt(pos)
        if item:
            row = self.row(item)
            rect = self.visualItemRect(item)
            if pos.y() > rect.top() + rect.height() // 2:
                return row + 1
            else:
                return row
        else:
            return self.count()

    def dragEnterEvent(self, event):
        if event.mimeData().hasFormat("application/x-aura-tracks") or event.mimeData().hasText():
            event.acceptProposedAction()
            self._drag_hover_row = self._get_drag_row(event.position().toPoint())
            self.viewport().update()
        else:
            super().dragEnterEvent(event)

    def dragMoveEvent(self, event):
        if event.mimeData().hasFormat("application/x-aura-tracks") or event.mimeData().hasText():
            event.acceptProposedAction()
            new_row = self._get_drag_row(event.position().toPoint())
            if new_row != self._drag_hover_row:
                self._drag_hover_row = new_row
                self.viewport().update()
        else:
            super().dragMoveEvent(event)

    def dragLeaveEvent(self, event):
        self._drag_hover_row = -1
        self.viewport().update()
        super().dragLeaveEvent(event)

    def paintEvent(self, event):
        super().paintEvent(event)
        if hasattr(self, "_drag_hover_row") and self._drag_hover_row >= 0:
            painter = QPainter(self.viewport())
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            pen = QPen(QColor("#FFFFFF"), 2)
            painter.setPen(pen)
            
            row = self._drag_hover_row
            row_count = self.count()
            
            if row < row_count:
                item = self.item(row)
                if item:
                    rect = self.visualItemRect(item)
                    y = rect.top()
                else:
                    y = 0
            else:
                if row_count > 0:
                    item = self.item(row_count - 1)
                    if item:
                        rect = self.visualItemRect(item)
                        y = rect.bottom()
                    else:
                        y = 0
                else:
                    y = 0
                    
            painter.drawLine(0, y, self.viewport().width(), y)
            painter.end()

    def dropEvent(self, event):
        self._drag_hover_row = -1
        self.viewport().update()

        mime = event.mimeData()
        if mime.hasFormat("application/x-aura-tracks") or mime.hasText():
            text = mime.text()
            paths = [p.strip() for p in text.split("\n") if p.strip()]
            
            if paths:
                pos = event.position().toPoint()
                to_row = self._get_drag_row(pos)
                
                # Check if this is an internal reorder move
                if event.source() == self:
                    current_paths = [self.item(i).data(Qt.ItemDataRole.UserRole) for i in range(self.count())]
                    selected_items = self.selectedItems()
                    if selected_items:
                        dragged_path = selected_items[0].data(Qt.ItemDataRole.UserRole)
                        if dragged_path in current_paths:
                            from_row = current_paths.index(dragged_path)
                            current_paths.pop(from_row)
                            if to_row > from_row:
                                to_row -= 1
                            current_paths.insert(to_row, dragged_path)
                            
                            self.reordered.emit(current_paths)
                            event.acceptProposedAction()
                            return
                else:
                    # External drop (adding external paths)
                    self.paths_dropped.emit(paths, to_row)
                    event.acceptProposedAction()
                    return

        super().dropEvent(event)





class QueueCoverLabel(QWidget):

    clicked = pyqtSignal()



    def __init__(self, track_path: str, is_active: bool, is_playing: bool, theme_colors: dict, has_embedded_art: bool = True, parent_widget=None):

        super().__init__(parent_widget)

        self.track_path = track_path

        self.is_active = is_active

        self.is_playing = is_playing

        self.is_hovered = False

        self.theme_colors = theme_colors

        self.setFixedSize(32, 32)

        self.pixmap = None

       

        # Load cover art

        raw_pixmap = get_album_art(track_path) if (track_path and has_embedded_art) else None

        if raw_pixmap and not raw_pixmap.isNull():

            self.pixmap = raw_pixmap.scaled(

                32, 32,

                Qt.AspectRatioMode.KeepAspectRatioByExpanding,

                Qt.TransformationMode.SmoothTransformation,

            )



    def paintEvent(self, event):

        painter = QPainter(self)

        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

       

        cover_rect = self.rect()

        clip_path = QPainterPath()

        clip_path.addRoundedRect(QRectF(cover_rect), 4.0, 4.0)

       

        painter.save()

        painter.setClipPath(clip_path)

       

        bg = self.theme_colors.get("surface", "#1C1F26")

        text_sec = self.theme_colors.get("text_secondary", "#9AA0AC")

       

        if self.pixmap:

            painter.drawPixmap(cover_rect, self.pixmap)

        else:

            from ui.svg_icon import get_default_cover

            disc_px = get_default_cover(cover_rect.width(), self.theme_colors, corner_radius=4.0)

            if disc_px and not disc_px.isNull():

                painter.drawPixmap(cover_rect, disc_px)

            else:

                painter.fillRect(cover_rect, QColor(bg))

        painter.restore()

       

        # Overlay if playing or hovered

        show_overlay = (self.is_active and self.is_playing) or self.is_hovered

        if show_overlay:

            painter.save()

            painter.setClipPath(clip_path)

            painter.fillRect(cover_rect, QColor(0, 0, 0, 110))

            painter.restore()

           

        if self.is_active and self.is_playing:

            # Draw animated equalizer (State A)

            max_bar_h = 12

            bar_w = 2

            spacing = 1

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

        elif self.is_hovered:

            # Draw Play icon (State B)

            painter.save()

            font = QFont("Segoe UI", 9, QFont.Weight.Bold)

            painter.setFont(font)

            painter.setPen(QColor("#FFFFFF"))

            play_rect = cover_rect.adjusted(1, 0, 0, 0)

            painter.drawText(play_rect, Qt.AlignmentFlag.AlignCenter, "▶")

            painter.restore()



    def enterEvent(self, event):

        super().enterEvent(event)

        self.is_hovered = True

        self.update()

        self.setCursor(Qt.CursorShape.PointingHandCursor)



    def leaveEvent(self, event):

        super().leaveEvent(event)

        self.is_hovered = False

        self.update()

        self.setCursor(Qt.CursorShape.ArrowCursor)



    def mousePressEvent(self, event):

        if event.button() == Qt.MouseButton.LeftButton:

            self.clicked.emit()

            event.accept()

        else:

            super().mousePressEvent(event)





class QueueHoverLabel(QLabel):
    """
    Hover-underline label used for both the queue row's title and each
    individual artist name.

    Bugfix (2026-07-03): artist names sit packed tightly, side-by-side,
    in a zero-spacing/zero-margin row. With the previous `Maximum`
    size policy, Qt was not guaranteed to size each label to exactly
    its own text -- in that tightly packed context, adjacent labels'
    actual hit-boxes could overlap or leave dead gaps between them, so
    hovering over one artist's text often didn't land inside that
    label's true geometry, and enterEvent/leaveEvent fired unreliably
    (or not at all). The title label never hit this because it's alone
    on its own row with nothing crowding it, which is why "title hover
    works, artist hover doesn't" despite both using this same class.

    Fix: give the label a `Fixed` size policy and an explicit
    `setFixedWidth()` computed from its own font metrics, so its
    hit-box is pixel-exact to its visible text -- no shared boundaries
    with neighboring labels, no dead zones. `setMouseTracking` +
    `WA_Hover` are set defensively on top of that. The actual hover
    effect is unchanged: underline via `QFont.setUnderline()` only, no
    background/rectangle, no row highlight.
    """

    clicked = pyqtSignal()

    def __init__(self, text: str, is_active: bool, theme_colors: dict, is_bold: bool = False, font_size: int = 9, parent=None):

        super().__init__(text, parent)

        self.is_active = is_active

        self.theme_colors = theme_colors

        self.is_bold = is_bold

        self.font_size = font_size

        self.is_hovered = False

        # Defensive: enterEvent/leaveEvent don't strictly require mouse
        # tracking, but enabling it plus WA_Hover removes any ambiguity
        # about whether this specific small widget receives hover
        # notifications reliably while embedded inside a QListWidget
        # item widget.
        self.setMouseTracking(True)
        self.setAttribute(Qt.WidgetAttribute.WA_Hover, True)

        # Fixed (not Maximum) so this label's box is pixel-exact to its
        # text -- see class docstring above for why this matters here.
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Preferred)

        self._update_style()

    def _resize_to_text(self) -> None:
        fm = self.fontMetrics()
        width = fm.horizontalAdvance(self.text())
        self.setFixedWidth(max(width, 1))

    def _update_style(self):

        accent = self.theme_colors.get("accent", "#6C5CE7")

        text_primary = self.theme_colors.get("text_primary", "#EDEFF2")

        text_secondary = self.theme_colors.get("text_secondary", "#9AA0AC")

       

        color = text_primary if self.is_bold else text_secondary

        if self.is_active:

            color = accent

        elif self.is_hovered:

            color = accent

       

        font = QFont("Segoe UI", self.font_size)
        font.setBold(self.is_bold or self.is_active)
        font.setUnderline(self.is_hovered)
        self.setFont(font)

        self.setStyleSheet(f"""
            color: {color};
            background-color: transparent;
            border: none;
            padding: 0px;
            margin: 0px;
        """)

        self._resize_to_text()

       

    def enterEvent(self, event):

        super().enterEvent(event)

        self.is_hovered = True

        self._update_style()

        self.setCursor(Qt.CursorShape.PointingHandCursor)

       

    def leaveEvent(self, event):

        super().leaveEvent(event)

        self.is_hovered = False

        self._update_style()

        self.setCursor(Qt.CursorShape.ArrowCursor)



    def mousePressEvent(self, event):

        if event.button() == Qt.MouseButton.LeftButton:

            self.clicked.emit()

            event.accept()

        else:

            super().mousePressEvent(event)





class QueueItemWidget(QWidget):

    """Custom widget inside QListWidget for rich display (Cover, Title, Artist)."""

    album_requested = pyqtSignal(str)

    artist_requested = pyqtSignal(str)

    cover_clicked = pyqtSignal()



    def __init__(self, track_path: str, title: str, artist: str, album_key: str, first_artist: str, is_active: bool, is_playing: bool, theme_colors: dict, has_embedded_art: bool = True, parent=None):

        super().__init__(parent)

        self.track_path = track_path

        self.album_key = album_key

        self.first_artist = first_artist



        layout = QHBoxLayout(self)

        layout.setContentsMargins(8, 4, 8, 4)

        layout.setSpacing(10)



        # Album cover on the left with three states

        self.cover_lbl = QueueCoverLabel(track_path, is_active, is_playing, theme_colors, has_embedded_art, self)

        self.cover_lbl.clicked.connect(self.cover_clicked.emit)

        layout.addWidget(self.cover_lbl)



        # Text column (Title + Artist)

        text_layout = QVBoxLayout()

        text_layout.setSpacing(2)

        text_layout.setContentsMargins(0, 0, 0, 0)



        self.title_lbl = QueueHoverLabel(title, is_active, theme_colors, is_bold=True, font_size=10, parent=self)

        self.title_lbl.clicked.connect(lambda: self.album_requested.emit(self.album_key))

        text_layout.addWidget(self.title_lbl)



        # Separate artists dynamically for individual hover and underline effects

        artists_layout = QHBoxLayout()

        artists_layout.setContentsMargins(0, 0, 0, 0)

        artists_layout.setSpacing(0)



        if artist and artist != "Unknown Artist":

            artist_parts = [a.strip() for a in artist.split(",") if a.strip()]

        else:

            artist_parts = ["Unknown Artist"]



        for idx, art_name in enumerate(artist_parts):

            art_lbl = QueueHoverLabel(art_name, is_active, theme_colors, is_bold=False, font_size=9, parent=self)

            art_lbl.clicked.connect(lambda name=art_name: self.artist_requested.emit(name))

            artists_layout.addWidget(art_lbl)



            if idx < len(artist_parts) - 1:

                sep_lbl = QLabel(", ")

                sep_lbl.setFont(QFont("Segoe UI", 9))

                text_secondary = theme_colors.get("text_secondary", "#9AA0AC")

                sep_lbl.setStyleSheet(f"color: {text_secondary};")

                sep_lbl.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Preferred)

                artists_layout.addWidget(sep_lbl)



        artists_layout.addStretch()

        text_layout.addLayout(artists_layout)



        layout.addLayout(text_layout, stretch=1)





class QueuePanel(QFrame):

    close_requested = pyqtSignal()

    album_requested = pyqtSignal(str)

    artist_requested = pyqtSignal(str)



    def __init__(self, store: LibraryStore, engine, parent=None):

        super().__init__(parent)

        self.store = store

        self.engine = engine

        self._theme_colors: dict = {}



        # Resize limits and drag state

        self._min_width = 280

        self._max_width = 500

        self._resizing = False

        self._drag_start_pos = None

        self._drag_start_width = None

        self.setMouseTracking(True)



        # Equalizer animation timer

        self.animation_timer = QTimer(self)

        self.animation_timer.setInterval(120)  # ~8 fps

        self.animation_timer.timeout.connect(self._on_animation_tick)



        self.setObjectName("queuePanel")

        self.setFrameShape(QFrame.Shape.NoFrame)



        self._build_ui()

        self._wire_signals()



    def _build_ui(self) -> None:

        layout = QVBoxLayout(self)

        layout.setContentsMargins(12, 12, 12, 12)

        layout.setSpacing(12)



        # Header Row

        header = QHBoxLayout()

        header.setContentsMargins(0, 0, 0, 0)

        header.setSpacing(8)



        self.title_lbl = QLabel("Play Queue")

        self.title_lbl.setFont(QFont("Segoe UI", 11, QFont.Weight.Bold))

        self.title_lbl.setStyleSheet("text-transform: uppercase; letter-spacing: 0.5px;")

        header.addWidget(self.title_lbl)



        header.addStretch()



        # Removed the "Clear" button per spec.

        # Close button is now "<" symbol

        self.close_btn = QPushButton("<")

        self.close_btn.setFixedSize(24, 24)

        self.close_btn.setFlat(True)

        self.close_btn.setCursor(Qt.CursorShape.PointingHandCursor)

        self.close_btn.setStyleSheet("font-size: 16px; font-weight: bold; border: none; background: transparent;")

        header.addWidget(self.close_btn)



        layout.addLayout(header)



        # List Widget

        self.list_widget = QueueListWidget(self)

        layout.addWidget(self.list_widget, stretch=1)



    def _wire_signals(self) -> None:

        self.close_btn.clicked.connect(self.close_requested.emit)

        self.list_widget.reordered.connect(self._on_queue_reordered)
        self.list_widget.paths_dropped.connect(self._on_queue_paths_dropped)

        self.list_widget.doubleClicked.connect(self._on_item_double_clicked)

        self.list_widget.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)

        self.list_widget.customContextMenuRequested.connect(self._show_context_menu)



        # Wire engine updates

        self.engine.queue_changed.connect(self.refresh)

        self.engine.track_changed.connect(self.refresh)

        self.engine.playback_state_changed.connect(self.refresh)

        self.engine.shuffle_changed.connect(self.refresh)



    def apply_theme(self, theme_colors: dict) -> None:

        self._theme_colors = theme_colors

        bg = theme_colors.get("surface", "#1C1F26")

        border = theme_colors.get("border", "#2E323C")

        text = theme_colors.get("text_primary", "#EDEFF2")

        text_sec = theme_colors.get("text_secondary", "#9AA0AC")



        self.title_lbl.setStyleSheet(f"color: {text};")



        self.setStyleSheet(f"""

            QFrame#queuePanel {{

                background-color: {bg};

                border-left: 1px solid {border};

            }}

            QPushButton {{

                color: {text_sec};

                background: transparent;

                border: none;

            }}

            QPushButton:hover {{

                color: {text};

            }}

            QListWidget {{

                background-color: transparent;

                border: none;

            }}

            QListWidget::item {{

                border-bottom: 1px solid {border};

                padding: 4px;

            }}

            QListWidget::item:hover {{

                background-color: transparent;

            }}

            QListWidget::item:selected {{

                background-color: {theme_colors.get("surface_selected", "#2A2440")};

            }}

        """)

        self.refresh()



    def refresh(self) -> None:

        self.list_widget.blockSignals(True)

        self.list_widget.clear()



        queue = self.engine.get_queue()

        active_idx = self.engine.get_queue_index()



        for i, path in enumerate(queue):

            track = self.store.get_track(path)

            has_embedded_art = True

            if track:

                title = track.title

                artists_str = ", ".join(track.artists)

                album_key = track.album_key

                first_artist = track.artists[0] if track.artists else "Unknown Artist"

                has_embedded_art = track.has_embedded_art

            else:

                title = os.path.basename(path)

                artists_str = "Unknown Artist"

                album_key = ""

                first_artist = "Unknown Artist"

                has_embedded_art = False



            item = QListWidgetItem()

            item.setData(Qt.ItemDataRole.UserRole, path)

            self.list_widget.addItem(item)



            is_active = (i == active_idx)

            is_playing = is_active and self.engine.is_playing()

            widget = QueueItemWidget(path, title, artists_str, album_key, first_artist, is_active, is_playing, self._theme_colors, has_embedded_art, self.list_widget)

            widget.album_requested.connect(self.album_requested.emit)

            widget.artist_requested.connect(self.artist_requested.emit)

            widget.cover_clicked.connect(lambda r=i: self._on_cover_clicked(r))

            item.setSizeHint(widget.sizeHint())

            self.list_widget.setItemWidget(item, widget)



            if is_active:

                self.list_widget.setCurrentItem(item)



        self.list_widget.blockSignals(False)

        self._update_animation_timer()



    def _update_animation_timer(self) -> None:

        if self.engine and self.engine.is_playing() and self.isVisible():

            if not self.animation_timer.isActive():

                self.animation_timer.start()

        else:

            if self.animation_timer.isActive():

                self.animation_timer.stop()



    def _on_animation_tick(self) -> None:

        self.list_widget.viewport().update()



    def showEvent(self, event) -> None:

        super().showEvent(event)

        self._update_animation_timer()

        self.refresh()



    def hideEvent(self, event) -> None:

        super().hideEvent(event)

        self._update_animation_timer()



    def _on_queue_reordered(self, paths: list[str]) -> None:

        try:

            self.engine.reorder_queue(paths)

        except Exception as e:

            self.refresh()

    def _on_queue_paths_dropped(self, paths: list[str], to_row: int) -> None:

        try:

            self.engine.insert_into_queue(paths, to_row)

        except Exception as e:

            self.refresh()



    def _on_item_double_clicked(self, index) -> None:

        row = index.row()

        self.engine._play_queue_index(row)



    def _on_cover_clicked(self, row: int) -> None:

        self.engine._play_queue_index(row)



    def _show_context_menu(self, pos) -> None:

        item = self.list_widget.itemAt(pos)

        if not item:

            return



        path = item.data(Qt.ItemDataRole.UserRole)

        row = self.list_widget.row(item)



        menu = QMenu(self)

        if self._theme_colors:

            bg = self._theme_colors.get("surface", "#1C1F26")

            text = self._theme_colors.get("text_primary", "#EDEFF2")

            border = self._theme_colors.get("border", "#2E323C")

            accent = self._theme_colors.get("accent", "#6C5CE7")

            menu.setStyleSheet(f"""

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

                }}

                QMenu::item:selected {{

                    background-color: {accent};

                    color: {text};

                }}

            """)



        play_action = QAction("Play Now", self)

        play_action.triggered.connect(lambda: self.engine._play_queue_index(row))

        menu.addAction(play_action)



        remove_action = QAction("Remove", self)

        remove_action.triggered.connect(lambda: self.engine.remove_from_queue(path))

        menu.addAction(remove_action)



        menu.exec(self.list_widget.mapToGlobal(pos))



    def keyPressEvent(self, event) -> None:

        if event.key() == Qt.Key.Key_Delete:

            item = self.list_widget.currentItem()

            if item:

                path = item.data(Qt.ItemDataRole.UserRole)

                self.engine.remove_from_queue(path)

        else:

            super().keyPressEvent(event)



    # ------------------------------------------------------------------

    # Drag Resizing Logic on Left Edge

    # ------------------------------------------------------------------



    def mousePressEvent(self, event) -> None:

        if event.button() == Qt.MouseButton.LeftButton and event.position().x() <= 8:

            self._resizing = True

            self._drag_start_pos = event.globalPosition()

            self._drag_start_width = self.width()

            event.accept()

        else:

            super().mousePressEvent(event)



    def mouseMoveEvent(self, event) -> None:

        if self._resizing:

            delta_x = event.globalPosition().x() - self._drag_start_pos.x()

            new_width = self._drag_start_width - int(delta_x)

            new_width = max(self._min_width, min(new_width, self._max_width))

            self.setMinimumWidth(new_width)

            self.setMaximumWidth(new_width)

            event.accept()

        elif event.position().x() <= 8:

            self.setCursor(Qt.CursorShape.SplitHCursor)

            event.accept()

        else:

            self.setCursor(Qt.CursorShape.ArrowCursor)

            super().mouseMoveEvent(event)



    def mouseReleaseEvent(self, event) -> None:

        if self._resizing:

            self._resizing = False

            event.accept()

        else:

            super().mouseReleaseEvent(event)



    def leaveEvent(self, event) -> None:

        if not self._resizing:

            self.setCursor(Qt.CursorShape.ArrowCursor)

        super().leaveEvent(event)