"""
A custom QTableView that supports dragging selected tracks' paths as plain text,
and optionally handles internal moves (drag-reordering) and external drops.
"""

from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal, QPoint
from PyQt6.QtWidgets import QTableView, QAbstractItemView
from PyQt6.QtGui import QDrag, QMouseEvent, QPainter, QColor, QPen
from PyQt6.QtCore import QMimeData


class AuraDragTableView(QTableView):
    reordered = pyqtSignal(int, int)        # from_row, to_row
    dropped_paths = pyqtSignal(list, int)   # list of track paths dropped, target_row (-1 if sorted)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setDragEnabled(True)
        self.setAcceptDrops(False)
        self.setDragDropMode(QAbstractItemView.DragDropMode.DragOnly)
        self._drag_start_pos = None
        self._drag_hover_row = -1
        self.store = None

    def mousePressEvent(self, event: QMouseEvent):
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_start_pos = event.position().toPoint()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent):
        if event.buttons() & Qt.MouseButton.LeftButton and self._drag_start_pos is not None:
            if (event.position().toPoint() - self._drag_start_pos).manhattanLength() >= 10:
                self._start_drag()
                self._drag_start_pos = None
                return
        super().mouseMoveEvent(event)

    def _start_drag(self):
        selected_indexes = self.selectionModel().selectedRows()
        if not selected_indexes:
            return

        paths = []
        for idx in selected_indexes:
            track = self.model().data(idx, Qt.ItemDataRole.UserRole)
            if track and hasattr(track, 'path'):
                paths.append(track.path)

        if not paths:
            return

        drag = QDrag(self)
        mime = QMimeData()
        mime.setText("\n".join(paths))
        mime.setData("application/x-aura-tracks", b"1")
        drag.setMimeData(mime)
        drag.exec(Qt.DropAction.CopyAction | Qt.DropAction.MoveAction)

    def _get_drag_row(self, pos) -> int:
        idx = self.indexAt(pos)
        if idx.isValid():
            rect = self.visualRect(idx)
            if pos.y() > rect.top() + rect.height() // 2:
                return idx.row() + 1
            else:
                return idx.row()
        else:
            return self.model().rowCount() if self.model() else 0

    def dragEnterEvent(self, event):
        if event.mimeData().hasFormat("application/x-aura-tracks") or event.mimeData().hasText():
            event.acceptProposedAction()
            if event.source() == self:
                self._drag_hover_row = self._get_drag_row(event.position().toPoint())
            else:
                self._drag_hover_row = -1
            self.viewport().update()
        else:
            super().dragEnterEvent(event)

    def dragMoveEvent(self, event):
        if event.mimeData().hasFormat("application/x-aura-tracks") or event.mimeData().hasText():
            event.acceptProposedAction()
            if event.source() == self:
                new_row = self._get_drag_row(event.position().toPoint())
                if new_row != self._drag_hover_row:
                    self._drag_hover_row = new_row
                    self.viewport().update()
            else:
                if self._drag_hover_row != -1:
                    self._drag_hover_row = -1
                    self.viewport().update()
        else:
            super().dragMoveEvent(event)

    def dragLeaveEvent(self, event):
        self._drag_hover_row = -1
        self.viewport().update()
        super().dragLeaveEvent(event)

    def paintEvent(self, event):
        super().paintEvent(event)
        
        model = self.model()
        if model and hasattr(self, "_drag_hover_row") and self._drag_hover_row >= 0:
            from ui.theme import THEMES, DEFAULT_THEME
            theme_color = "#6C5CE7"
            if hasattr(self, "store") and self.store:
                theme_key = self.store.cache.settings.theme
                theme = THEMES.get(theme_key, THEMES[DEFAULT_THEME])
                theme_color = theme.get("accent", "#6C5CE7")
                
            painter = QPainter(self.viewport())
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            pen = QPen(QColor(theme_color), 2)
            painter.setPen(pen)
            
            row = self._drag_hover_row
            row_count = model.rowCount()
            
            if row < row_count:
                idx = model.index(row, 0)
                rect = self.visualRect(idx)
                y = rect.top()
            else:
                if row_count > 0:
                    idx = model.index(row_count - 1, 0)
                    rect = self.visualRect(idx)
                    y = rect.bottom()
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
            
            # Check if this is an internal reorder move
            if event.source() == self:
                selected_rows = self.selectionModel().selectedRows()
                if selected_rows:
                    from_row = selected_rows[0].row()
                    pos = event.position().toPoint()
                    to_idx = self.indexAt(pos)
                    if to_idx.isValid():
                        rect = self.visualRect(to_idx)
                        if pos.y() > rect.top() + rect.height() // 2:
                            to_row = to_idx.row() + 1
                        else:
                            to_row = to_idx.row()
                    else:
                        to_row = self.model().rowCount()
                    if from_row != to_row:
                        self.reordered.emit(from_row, to_row)
                        event.acceptProposedAction()
                        return

            # Otherwise, it's adding external paths
            if paths:
                self.dropped_paths.emit(paths, -1)
                event.acceptProposedAction()
                return

        super().dropEvent(event)

