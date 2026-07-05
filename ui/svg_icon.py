"""
SVG icon loading, recoloring, and caching for AuraPlayer.

Strategy: load SVG bytes from disk once, string-replace 'currentColor'
with a hex value at theme-apply time, then render to a QPixmap via
QSvgRenderer and cache the result keyed by (path, hex_color, size).
This gives us:
  - Zero per-paint overhead (cached QPixmap handed straight to QPushButton)
  - Perfect theme adaptation across all 4 themes with no separate asset files
  - Programmatic mirroring for prev/rewind (no separate files needed)
  - SVG path injection for slash (shuffle-off/repeat-off) and "1" (repeat-one)

Public API used by the rest of the app:
  svg_pixmap(asset_name, color, size) -> QPixmap
  svg_icon(asset_name, color, size)   -> QIcon  (convenience wrapper)
  clear_cache()                        -> None   (call on theme change)
"""

from __future__ import annotations

import os
from typing import Optional

from PyQt6.QtCore import Qt, QByteArray, QRectF
from PyQt6.QtGui import QPixmap, QIcon, QPainter, QColor
from PyQt6.QtSvg import QSvgRenderer

# ---------------------------------------------------------------------------
# Asset root — everything resolves relative to this
# ---------------------------------------------------------------------------
_ASSETS_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "assets")

# Cache: (asset_name_or_key, hex_color, size_px) -> QPixmap
_CACHE: dict[tuple[str, str, int], QPixmap] = {}


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _asset_path(name: str) -> str:
    """Resolve an asset name ('play', 'next', …) to its full file path."""
    return os.path.join(_ASSETS_DIR, f"{name}.svg")


def _read_svg(name: str) -> bytes:
    """Read raw SVG bytes for a named asset. Raises FileNotFoundError if
    the asset doesn't exist -- callers should use only asset names from
    the approved list in the initialisation prompt."""
    path = _asset_path(name)
    with open(path, "rb") as f:
        return f.read()


def _recolor(svg_bytes: bytes, hex_color: str) -> bytes:
    """Replace every occurrence of 'currentColor' (case-insensitive) and
    common hardcoded stroke/fill values with the given hex_color, so the
    icon adapts to whichever theme is active.

    We also handle 'stroke="black"' and 'fill="black"' since some SVG
    exporters bake in explicit black rather than currentColor.
    """
    svg_str = svg_bytes.decode("utf-8", errors="replace")
    
    # Ensure root <svg> has a default fill of currentColor if not explicitly defined,
    # so any child path with no explicit fill inherits it
    if "fill=" not in svg_str and "<svg" in svg_str:
        svg_str = svg_str.replace("<svg", '<svg fill="currentColor"')

    replacements = [
        ("currentColor", hex_color),
        ('"black"', f'"{hex_color}"'),
        ("'black'", f"'{hex_color}'"),
        ('"#000000"', f'"{hex_color}"'),
        ("'#000000'", f"'{hex_color}'"),
        ('"#000"', f'"{hex_color}"'),
        ("'#000'", f"'{hex_color}'"),
        ("#000000", hex_color),
        ("#000", hex_color),
    ]
    for old, new in replacements:
        svg_str = svg_str.replace(old, new)
    return svg_str.encode("utf-8")


def _mirror_horizontal(svg_bytes: bytes) -> bytes:
    """Inject a transform that horizontally flips the SVG content, used
    to derive 'prev' from 'next' and 'rewind' from 'forward' without
    needing separate asset files.

    Wraps the existing SVG <g> children in a new <g transform="scale(-1,1)
    translate(-W,0)"> where W is the viewBox width, so the icon renders
    mirrored but at the same apparent position. If the viewBox can't be
    parsed, falls back to a simple scale(-1,1) applied inside the SVG root.
    """
    svg_str = svg_bytes.decode("utf-8", errors="replace")

    # Parse viewBox width for correct translation
    import re
    vb_match = re.search(r'viewBox=["\'][\d.]+ [\d.]+ ([\d.]+)', svg_str)
    width = vb_match.group(1) if vb_match else "24"

    # Inject a wrapping group right before </svg>
    mirror_group_open = f'<g transform="scale(-1,1) translate(-{width},0)">'
    mirror_group_close = "</g>"

    # Find where the actual content starts (after the opening <svg ...> tag)
    svg_open_end = svg_str.find(">", svg_str.find("<svg")) + 1
    svg_close = svg_str.rfind("</svg>")

    if svg_open_end <= 0 or svg_close <= 0:
        return svg_bytes  # can't parse; return as-is

    inner = svg_str[svg_open_end:svg_close]
    svg_header = svg_str[:svg_open_end]
    result = (
        svg_header
        + mirror_group_open
        + inner
        + mirror_group_close
        + "</svg>"
    )
    return result.encode("utf-8")


def _inject_slash(svg_bytes: bytes, hex_color: str) -> bytes:
    """Inject a diagonal slash line into an SVG to represent a disabled
    state (shuffle-off, repeat-off). The slash goes from top-left to
    bottom-right, dynamically scaled to the viewBox size of the SVG.
    The stroke color is taken from the current theme so the slash is
    visually cohesive, not a fixed contrasting color.
    """
    svg_str = svg_bytes.decode("utf-8", errors="replace")
    
    # Parse viewBox width to scale coordinates
    import re
    vb_match = re.search(r'viewBox=["\'][\d.]+ [\d.]+ ([\d.]+)', svg_str)
    try:
        width = float(vb_match.group(1)) if vb_match else 24.0
    except Exception:
        width = 24.0

    x1 = 0.125 * width
    y1 = 0.125 * width
    x2 = 0.875 * width
    y2 = 0.875 * width
    stroke_w = max(1.5, 2.0 * width / 24.0)

    slash = (
        f'<line x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" y2="{y2:.1f}" '
        f'stroke="{hex_color}" stroke-width="{stroke_w:.1f}" stroke-linecap="round"/>'
    )
    svg_str = svg_str.replace("</svg>", slash + "</svg>")
    return svg_str.encode("utf-8")


def _inject_repeat_one_label(svg_bytes: bytes, hex_color: str) -> bytes:
    """Inject a centered '1' text label into the repeat icon to represent
    repeat-one mode, matching the convention used by Spotify, Apple Music,
    and other players. Positioned dynamically at the visual center of the viewBox.
    """
    svg_str = svg_bytes.decode("utf-8", errors="replace")
    
    # Parse viewBox width
    import re
    vb_match = re.search(r'viewBox=["\'][\d.]+ [\d.]+ ([\d.]+)', svg_str)
    try:
        width = float(vb_match.group(1)) if vb_match else 24.0
    except Exception:
        width = 24.0

    x = width / 2.0
    y = width * 16.0 / 24.0
    font_size = 9.0 * width / 24.0

    label = (
        f'<text x="{x:.1f}" y="{y:.1f}" text-anchor="middle" '
        f'font-family="Segoe UI,sans-serif" font-size="{font_size:.1f}" '
        f'font-weight="700" fill="{hex_color}">1</text>'
    )
    svg_str = svg_str.replace("</svg>", label + "</svg>")
    return svg_str.encode("utf-8")


def _generate_back_arrow(hex_color: str) -> bytes:
    """Generate a clean left-pointing chevron arrow SVG entirely in code
    for the Player Screen's back button -- no separate file needed.
    Matches the visual weight of the other icons in the asset set.
    """
    svg = f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" 
        fill="none" stroke="{hex_color}" stroke-width="2" 
        stroke-linecap="round" stroke-linejoin="round">
      <polyline points="15 18 9 12 15 6"/>
    </svg>"""
    return svg.encode("utf-8")


def _render(svg_bytes: bytes, size: int) -> QPixmap:
    """Render SVG bytes to a square QPixmap at the given pixel size."""
    renderer = QSvgRenderer(QByteArray(svg_bytes))
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    renderer.render(painter, QRectF(0, 0, size, size))
    painter.end()
    return pixmap


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def svg_pixmap(
    asset_name: str,
    color: str,
    size: int = 22,
    *,
    mirrored: bool = False,
    slash: bool = False,
    repeat_one: bool = False,
    filled: bool = False,
) -> QPixmap:
    """Return a themed, cached QPixmap for the given asset.

    Parameters
    ----------
    asset_name : str
        Base name without extension, e.g. 'play', 'next', 'shuffle'.
        Special values: 'prev' and 'rewind' are synthesised from
        'next' and 'forward' respectively by horizontal mirroring.
        'back' is generated entirely in code (no file needed).
    color : str
        Hex color string, e.g. '#EDEFF2'. Applied wherever the SVG
        uses 'currentColor'.
    size : int
        Rendered pixel size (square). Default 22px matches the icon
        button design in the transport controls.
    mirrored : bool
        Horizontally flip the icon. Handled automatically for 'prev'
        and 'rewind'; exposed directly for any other case if needed.
    slash : bool
        Inject a diagonal slash, for shuffle-off / repeat-off states.
    repeat_one : bool
        Inject a '1' label, for repeat-one state.
    filled : bool
        If True and asset is 'heart', strips the inner cutout subpath
        so the heart renders completely filled.
    """
    # Build a cache key that encodes every dimension that affects the
    # rendered output, so different state combinations get distinct entries.
    state_suffix = (
        ("_m" if mirrored else "") + 
        ("_s" if slash else "") + 
        ("_1" if repeat_one else "") +
        ("_f" if filled else "")
    )
    cache_key = (asset_name + state_suffix, color, size)
    if cache_key in _CACHE:
        return _CACHE[cache_key]

    # Synthesised assets
    if asset_name == "back":
        svg_bytes = _generate_back_arrow(color)
        pixmap = _render(svg_bytes, size)
        _CACHE[cache_key] = pixmap
        return pixmap

    if asset_name == "prev":
        raw = _read_svg("next")
        svg_bytes = _recolor(_mirror_horizontal(raw), color)
        if slash:
            svg_bytes = _inject_slash(svg_bytes, color)
        pixmap = _render(svg_bytes, size)
        _CACHE[cache_key] = pixmap
        return pixmap

    if asset_name == "rewind":
        raw = _read_svg("forward")
        svg_bytes = _recolor(_mirror_horizontal(raw), color)
        if slash:
            svg_bytes = _inject_slash(svg_bytes, color)
        pixmap = _render(svg_bytes, size)
        _CACHE[cache_key] = pixmap
        return pixmap

    # Normal file-backed assets
    raw = _read_svg(asset_name)

    if asset_name == "heart" and filled:
        raw = b'<svg width="24" height="24" xmlns="http://www.w3.org/2000/svg"><path d="M12 21.35l-1.45-1.32C5.4 15.36 2 12.28 2 8.5 2 5.42 4.42 3 7.5 3c1.74 0 3.41.81 4.5 2.09C13.09 3.81 14.76 3 16.5 3 19.58 3 22 5.42 22 8.5c0 3.78-3.4 6.86-8.55 11.54L12 21.35z" fill="currentColor"/></svg>'

    if mirrored:
        raw = _mirror_horizontal(raw)

    svg_bytes = _recolor(raw, color)

    if slash:
        svg_bytes = _inject_slash(svg_bytes, color)

    if repeat_one:
        svg_bytes = _inject_repeat_one_label(svg_bytes, color)

    pixmap = _render(svg_bytes, size)
    _CACHE[cache_key] = pixmap
    return pixmap


def svg_icon(
    asset_name: str,
    color: str,
    size: int = 22,
    **kwargs,
) -> QIcon:
    """Convenience wrapper: same signature as svg_pixmap but returns a
    QIcon, for use with QPushButton.setIcon().
    """
    return QIcon(svg_pixmap(asset_name, color, size, **kwargs))


def clear_cache() -> None:
    """Invalidate the pixmap cache. Call this whenever the active theme
    changes so the next icon request re-renders in the new palette colors.
    """
    _CACHE.clear()


def get_default_cover(size: int, theme: dict, corner_radius: float = 4.0) -> QPixmap:
    """
    Returns a beautiful, theme-adaptive default album cover QPixmap
    with a solid background, rounded corners, and a centered disc/vinyl icon.
    """
    bg_color_str = theme.get("surface", "#1C1F26")
    icon_color_str = theme.get("text_secondary", "#9AA0AC")
    
    # We can cache this as well to avoid drawing on every single paintEvent
    cache_key = ("default_cover_gen", bg_color_str, icon_color_str, size, int(corner_radius))
    if cache_key in _CACHE:
        return _CACHE[cache_key]
    
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)
    
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    
    # Draw rounded background
    painter.setBrush(QColor(bg_color_str))
    painter.setPen(Qt.PenStyle.NoPen)
    painter.drawRoundedRect(QRectF(0, 0, size, size), corner_radius, corner_radius)
    
    # Render the disc icon centered inside
    disc_size = int(size * 0.55)
    disc_size = max(16, min(disc_size, size - 4))
    
    disc_px = svg_pixmap("disc", icon_color_str, disc_size)
    if disc_px and not disc_px.isNull():
        offset = (size - disc_size) / 2.0
        painter.drawPixmap(QRectF(offset, offset, disc_size, disc_size), disc_px, QRectF(disc_px.rect()))
        
    painter.end()
    _CACHE[cache_key] = pixmap
    return pixmap
