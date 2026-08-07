"""
Shared helpers for track table views: cover sizing, multi-artist hover
drawing/hit-testing, primary-column 4-state sort cycling, and column resize setup.
"""

from __future__ import annotations

from PyQt6.QtCore import Qt, QRect, QPoint
from PyQt6.QtGui import QFont, QColor, QFontMetrics
from PyQt6.QtWidgets import QHeaderView, QTableView

from core.library_store import LibraryStore
from ui.widgets.adjacent_resize_helper import AdjacentResizeHelper

COVER_SIZE = 36
COVER_LEFT_MARGIN = 10
COVER_CORNER_RADIUS = 4.0


def cover_rect_for_cell(cell_rect: QRect, cover_size: int = COVER_SIZE) -> QRect:
    cover_x = cell_rect.left() + COVER_LEFT_MARGIN
    cover_y = cell_rect.top() + (cell_rect.height() - cover_size) // 2
    return QRect(cover_x, cover_y, cover_size, cover_size)


def title_text_left(cell_rect: QRect, cover_size: int = COVER_SIZE) -> int:
    return cell_rect.left() + cover_size + 18


def title_and_artist_rects(cell_rect: QRect, cover_size: int = COVER_SIZE) -> tuple[QRect, QRect]:
    text_left = title_text_left(cell_rect, cover_size)
    text_rect = QRect(text_left, cell_rect.top(), cell_rect.right() - 6 - text_left, cell_rect.height())
    row_h = text_rect.height()
    title_rect = QRect(text_rect.left(), text_rect.top(), text_rect.width(), int(row_h * 0.54))
    artist_rect = QRect(text_rect.left(), text_rect.top() + int(row_h * 0.52), text_rect.width(), int(row_h * 0.44))
    return title_rect, artist_rect


def merged_artist_rect_for_cell(cell_rect: QRect, cover_size: int = COVER_SIZE) -> QRect:
    _, artist_rect = title_and_artist_rects(cell_rect, cover_size)
    return artist_rect


def merged_artist_rect_no_cover(cell_rect: QRect) -> QRect:
    rect = cell_rect.adjusted(6, 0, -6, 0)
    row_h = rect.height()
    return QRect(rect.left(), rect.top() + int(row_h * 0.52), rect.width(), int(row_h * 0.44))


def artist_subline_font(base_font: QFont, base_metrics: QFontMetrics) -> QFont:
    font = QFont(base_font)
    font.setBold(False)
    font.setPixelSize(max(9, int(base_metrics.height() * 0.82)))
    return font


def next_primary_sort_state(
    sort_column: int,
    sort_ascending: bool,
    title_col: int,
    artist_col: int,
) -> tuple[int, bool]:
    """Cycle: Title Asc -> Title Desc -> Artist Asc -> Artist Desc -> Title Asc."""
    if sort_column == title_col and sort_ascending:
        return title_col, False
    if sort_column == title_col and not sort_ascending:
        return artist_col, True
    if sort_column == artist_col and sort_ascending:
        return artist_col, False
    if sort_column == artist_col and not sort_ascending:
        return title_col, True
    return title_col, True


def draw_artists_in_rect(
    painter,
    artists: list[str],
    rect: QRect,
    mouse_pos: QPoint,
    theme: dict,
    base_color: QColor,
    *,
    check_hover: bool = True,
) -> None:
    if not artists:
        return

    fm = painter.fontMetrics()
    y_baseline = rect.top() + (rect.height() + fm.ascent() - fm.descent()) // 2
    x_offset = rect.left()
    max_x = rect.right()
    ellipsis = "..."
    ellipsis_width = fm.horizontalAdvance(ellipsis)
    is_hovered = check_hover and rect.contains(mouse_pos)

    for i, artist in enumerate(artists):
        artist_width = fm.horizontalAdvance(artist)
        next_delim = ", " if i < len(artists) - 1 else ""
        delim_width = fm.horizontalAdvance(next_delim) if next_delim else 0

        if x_offset + artist_width + delim_width > max_x:
            available_w = max_x - x_offset - ellipsis_width
            if available_w > 10:
                elided_artist = fm.elidedText(artist, Qt.TextElideMode.ElideRight, available_w)
                elided_width = fm.horizontalAdvance(elided_artist)
                artist_rect = QRect(x_offset, rect.top(), elided_width, rect.height())
                artist_hovered = is_hovered and artist_rect.contains(mouse_pos)

                font = painter.font()
                font.setUnderline(artist_hovered)
                painter.setFont(font)
                painter.setPen(QColor(theme["accent"]) if artist_hovered else base_color)
                painter.drawText(x_offset, y_baseline, elided_artist)
            elif x_offset + ellipsis_width <= max_x + 5:
                painter.setPen(base_color)
                painter.drawText(x_offset, y_baseline, ellipsis)
            break

        artist_rect = QRect(x_offset, rect.top(), artist_width, rect.height())
        artist_hovered = is_hovered and artist_rect.contains(mouse_pos)

        font = painter.font()
        font.setUnderline(artist_hovered)
        painter.setFont(font)
        painter.setPen(QColor(theme["accent"]) if artist_hovered else base_color)
        painter.drawText(x_offset, y_baseline, artist)

        x_offset += artist_width
        if next_delim:
            font.setUnderline(False)
            painter.setFont(font)
            painter.setPen(base_color)
            painter.drawText(x_offset, y_baseline, next_delim)
            x_offset += delim_width


def artist_name_at_pos(
    artists: list[str],
    rect: QRect,
    pos: QPoint,
    font: QFont,
) -> str | None:
    if not rect.contains(pos):
        return None

    fm = QFontMetrics(font)
    max_x = rect.right()
    ellipsis_width = fm.horizontalAdvance("...")
    x_offset = rect.left()

    for i, artist in enumerate(artists):
        artist_width = fm.horizontalAdvance(artist)
        next_delim = ", " if i < len(artists) - 1 else ""
        delim_width = fm.horizontalAdvance(next_delim) if next_delim else 0

        if x_offset + artist_width + delim_width > max_x:
            available_w = max_x - x_offset - ellipsis_width
            if available_w > 10:
                elided_artist = fm.elidedText(artist, Qt.TextElideMode.ElideRight, available_w)
                elided_width = fm.horizontalAdvance(elided_artist)
                artist_rect = QRect(x_offset, rect.top(), elided_width, rect.height())
                if artist_rect.contains(pos):
                    return artist
            break

        artist_rect = QRect(x_offset, rect.top(), artist_width, rect.height())
        if artist_rect.contains(pos):
            return artist
        x_offset += artist_width + delim_width

    return None


def configure_track_table_resize(
    table: QTableView,
    store: LibraryStore,
    cache_key: str,
    *,
    col_title: int,
    col_artists: int,
    col_album: int,
    col_genre: int,
    col_duration: int,
    title_width: int = 400,
    album_width: int = 180,
    genre_width: int = 120,
    duration_width: int = 80,
    hide_artists: bool = True,
    extra_columns: dict[int, int] | None = None,
) -> AdjacentResizeHelper:
    header = table.horizontalHeader()
    header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
    header.setStretchLastSection(False)
    header.setMinimumSectionSize(40)
    header.setSectionResizeMode(col_duration, QHeaderView.ResizeMode.Fixed)

    if extra_columns:
        for col, width in extra_columns.items():
            table.setColumnWidth(col, width)

    table.setColumnWidth(col_title, title_width)
    if hide_artists:
        table.setColumnHidden(col_artists, True)
    table.setColumnWidth(col_album, album_width)
    table.setColumnWidth(col_genre, genre_width)
    table.setColumnWidth(col_duration, duration_width)

    return AdjacentResizeHelper(header, store, cache_key)
