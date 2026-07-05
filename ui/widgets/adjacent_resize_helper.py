from __future__ import annotations

from PyQt6.QtCore import QObject, QEvent
from PyQt6.QtWidgets import QHeaderView, QTableView


class AdjacentResizeHelper(QObject):
    """
    Ensures that when a user resizes a column, only the column to its immediate
    left (the one being resized) and the column to its immediate right (the adjacent
    one) are affected. This keeps the subsequent columns in the exact same positions
    rather than shifting them.

    Also persists the column positions (widths) in the cache, and synchronizes adjacent
    or duplicate tables (e.g., disc-grouped tables in AlbumPageView) in real-time.
    """

    def __init__(self, header: QHeaderView, store=None, cache_key: str | None = None):
        super().__init__(header)
        self.header = header
        self.store = store
        self.cache_key = cache_key
        self._is_resizing = False

        self.table = header.parentWidget()
        if self.table and self.table.viewport():
            self.table.viewport().installEventFilter(self)

        # Restore saved widths if they exist in the cache
        if self.store and self.cache_key:
            saved_widths = self.store.cache.settings.column_widths.get(self.cache_key)
            if saved_widths:
                self._is_resizing = True
                for i, w in enumerate(saved_widths):
                    if i < self.header.count():
                        self.header.resizeSection(i, w)
                self._is_resizing = False

        self.header.sectionResized.connect(self.on_section_resized)

    def eventFilter(self, watched, event) -> bool:
        if self.table and watched == self.table.viewport() and event.type() == QEvent.Type.Resize:
            res = super().eventFilter(watched, event)
            self.adjust_columns_to_viewport()
            return res
        return super().eventFilter(watched, event)

    def adjust_columns_to_viewport(self) -> None:
        if self._is_resizing:
            return
        
        viewport_width = self.table.viewport().width()
        if viewport_width <= 0:
            return
            
        col_count = self.header.count()
        if col_count == 0:
            return
            
        widths = [self.header.sectionSize(i) for i in range(col_count)]
        current_sum = sum(widths)
        if current_sum <= 0:
            return
            
        self._is_resizing = True
        new_widths = []
        accumulated = 0
        min_size = self.header.minimumSectionSize()
        if min_size < 30:
            min_size = 30
            
        for i in range(col_count):
            if i == col_count - 1:
                new_w = max(min_size, viewport_width - accumulated)
            else:
                ratio = widths[i] / current_sum
                new_w = max(min_size, int(viewport_width * ratio))
                accumulated += new_w
            new_widths.append(new_w)
            
        for i, w in enumerate(new_widths):
            self.header.resizeSection(i, w)
            
        self._is_resizing = False

    def on_section_resized(self, index: int, old_size: int, new_size: int) -> None:
        if self._is_resizing:
            return

        if index + 1 < self.header.count():
            delta = new_size - old_size
            next_col_size = self.header.sectionSize(index + 1)
            new_next_size = next_col_size - delta

            min_size = self.header.minimumSectionSize()
            if min_size < 30:
                min_size = 30

            if new_next_size < min_size:
                allowed_delta = next_col_size - min_size
                self._is_resizing = True
                self.header.resizeSection(index, old_size + allowed_delta)
                self.header.resizeSection(index + 1, min_size)
                self._is_resizing = False
            else:
                self._is_resizing = True
                self.header.resizeSection(index + 1, new_next_size)
                self._is_resizing = False

        # Persist to cache
        if self.store and self.cache_key:
            widths = [self.header.sectionSize(i) for i in range(self.header.count())]
            self.store.cache.settings.column_widths[self.cache_key] = widths
            self.store.save()

            # Synchronize any other tables sharing the same cache_key on the same page
            parent_page = self.header.parent()
            while parent_page:
                if hasattr(parent_page, "_tables"):
                    break
                parent_page = parent_page.parent()

            if parent_page and hasattr(parent_page, "_tables"):
                for table in parent_page._tables:
                    if table.horizontalHeader() != self.header:
                        helper = getattr(table, "resize_helper", None)
                        if helper and helper.cache_key == self.cache_key and not helper._is_resizing:
                            helper._is_resizing = True
                            for i, w in enumerate(widths):
                                if i < helper.header.count():
                                    helper.header.resizeSection(i, w)
                            helper._is_resizing = False
