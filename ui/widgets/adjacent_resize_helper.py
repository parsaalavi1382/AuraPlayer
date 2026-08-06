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
        self._ratios = None

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

        self.header.installEventFilter(self)
        self.header.sectionResized.connect(self.on_section_resized)

    def _is_near_right_edge_of_last_section(self, pos_x: int) -> bool:
        visible_cols = self._get_visible_sections()
        if not visible_cols:
            return False
        last_col = visible_cols[-1]
        last_right = self.header.sectionPosition(last_col) + self.header.sectionSize(last_col)
        return pos_x >= (last_right - 8)

    def eventFilter(self, watched, event) -> bool:
        try:
            if watched == self.header:
                if event.type() in (QEvent.Type.MouseMove, QEvent.Type.HoverMove):
                    pos_x = event.position().toPoint().x() if hasattr(event, "position") else event.pos().x()
                    if self._is_near_right_edge_of_last_section(pos_x):
                        from PyQt6.QtCore import Qt
                        self.header.setCursor(Qt.CursorShape.ArrowCursor)
                        return True
            elif self.table and watched == self.table.viewport() and event.type() == QEvent.Type.Resize:
                res = super().eventFilter(watched, event)
                self.adjust_columns_to_viewport()
                return res
        except RuntimeError:
            pass
        return super().eventFilter(watched, event)

    def _get_visible_sections(self) -> list[int]:
        return [i for i in range(self.header.count()) if not self.header.isSectionHidden(i)]

    def _get_next_visible_section(self, index: int) -> int | None:
        for i in range(index + 1, self.header.count()):
            if not self.header.isSectionHidden(i):
                return i
        return None

    def adjust_columns_to_viewport(self) -> None:
        if self._is_resizing:
            return
        
        try:
            if not self.table or not self.table.viewport():
                return
            viewport_width = self.table.viewport().width()
            if viewport_width <= 0:
                return
                
            visible_cols = self._get_visible_sections()
            if not visible_cols:
                return
                
            widths = [self.header.sectionSize(i) for i in visible_cols]
            current_sum = sum(widths)
            if current_sum <= 0:
                return

            if not self._ratios or len(self._ratios) != len(visible_cols):
                self._ratios = [w / current_sum for w in widths]

            self._is_resizing = True
            new_widths = []
            accumulated = 0
            exact_accumulated = 0.0
            min_size = self.header.minimumSectionSize()
            if min_size < 30:
                min_size = 30
                
            for idx, col in enumerate(visible_cols):
                if idx == len(visible_cols) - 1:
                    new_w = max(min_size, viewport_width - accumulated)
                else:
                    ratio = self._ratios[idx]
                    exact_w = viewport_width * ratio
                    exact_accumulated += exact_w
                    new_w = max(min_size, int(round(exact_accumulated)) - accumulated)
                    accumulated += new_w
                new_widths.append(new_w)
                
            for idx, col in enumerate(visible_cols):
                self.header.resizeSection(col, new_widths[idx])
                
            self._is_resizing = False
        except RuntimeError:
            self._is_resizing = False

    def on_section_resized(self, index: int, old_size: int, new_size: int) -> None:
        if self._is_resizing:
            return

        # User manually resized a column, invalidate cached ratios
        self._ratios = None

        try:
            next_visible = self._get_next_visible_section(index)
            if next_visible is None:
                # This is the last visible section! Its right edge is attached to the right side of the page.
                # Do not allow resizing the right edge of the last visible column.
                self._is_resizing = True
                self.header.resizeSection(index, old_size)
                self._is_resizing = False
                return

            delta = new_size - old_size
            next_col_size = self.header.sectionSize(next_visible)
            new_next_size = next_col_size - delta

            min_size = self.header.minimumSectionSize()
            if min_size < 30:
                min_size = 30

            if new_next_size < min_size:
                allowed_delta = next_col_size - min_size
                self._is_resizing = True
                self.header.resizeSection(index, old_size + allowed_delta)
                self.header.resizeSection(next_visible, min_size)
                self._is_resizing = False
            else:
                self._is_resizing = True
                self.header.resizeSection(next_visible, new_next_size)
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
                        try:
                            if table.horizontalHeader() != self.header:
                                helper = getattr(table, "resize_helper", None)
                                if helper and helper.cache_key == self.cache_key and not helper._is_resizing:
                                    helper._is_resizing = True
                                    for i, w in enumerate(widths):
                                        if i < helper.header.count():
                                            helper.header.resizeSection(i, w)
                                    helper._is_resizing = False
                        except RuntimeError:
                            pass
        except RuntimeError:
            self._is_resizing = False
