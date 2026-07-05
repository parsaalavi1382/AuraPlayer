"""
App-wide visual theme.

Design intent: most desktop music players default to dark for a reason
-- album art and the visualiser read better against a dark surface than
a light one, and long library lists are easier to scan with less
overall glare. Rather than rely on default Qt widget chrome (which
looks unmistakably like "a Qt app"), each theme below defines one
deliberate palette, applied via a single stylesheet template, so every
view shares the same visual language regardless of which theme is active.

Four themes are offered:
  - dark (default): near-black with a violet accent, built in Step 2.
  - light: a clean, genuinely light theme -- not just the dark palette
    with colors flipped. Light themes need MORE contrast restraint
    (text isn't pure black, surfaces aren't pure white) or they read as
    harsh; tuned for that here.
  - midnight_blue: a cooler, deep-navy variant for users who find true
    black too stark -- same dark-theme ergonomics, different mood.
  - warm_amber: a warm, low-blue-light dark theme with an amber/orange
    accent instead of violet -- suits evening listening.

Step 4 additions:
  - #seekBarTime QLabel rule (time labels flanking the seek groove)
  - #playerScreen background rule (the full-screen overlay)
  - All rules use theme variables so every theme is covered.
"""

from __future__ import annotations

THEMES: dict[str, dict[str, str]] = {
    "dark": {
        "label": "Dark",
        "bg": "#14161A",
        "surface": "#1C1F26",
        "surface_hover": "#262A33",
        "surface_selected": "#2A2440",
        "border": "#2E323C",
        "text_primary": "#EDEFF2",
        "text_secondary": "#9AA0AC",
        "accent": "#6C5CE7",
        "accent_hover": "#8475F0",
        "danger": "#E05C5C",
    },
    "light": {
        "label": "Light",
        "bg": "#F7F7F9",
        "surface": "#FFFFFF",
        "surface_hover": "#EFEFF4",
        "surface_selected": "#E6E1FB",
        "border": "#DCDCE3",
        "text_primary": "#1C1E22",
        "text_secondary": "#6B7280",
        "accent": "#6C5CE7",
        "accent_hover": "#5848C2",
        "danger": "#D43F3F",
    },
    "midnight_blue": {
        "label": "Midnight Blue",
        "bg": "#0B1220",
        "surface": "#121B2E",
        "surface_hover": "#1B2740",
        "surface_selected": "#1E2F52",
        "border": "#22304A",
        "text_primary": "#E7ECF7",
        "text_secondary": "#8B97AE",
        "accent": "#3D8BFF",
        "accent_hover": "#5FA0FF",
        "danger": "#E0625C",
    },
    "warm_amber": {
        "label": "Warm Amber",
        "bg": "#1A1512",
        "surface": "#241D18",
        "surface_hover": "#332821",
        "surface_selected": "#3D2C1A",
        "border": "#3A2F27",
        "text_primary": "#F4ECE3",
        "text_secondary": "#B3A18E",
        "accent": "#E08A3C",
        "accent_hover": "#EFA257",
        "danger": "#E0615C",
    },
}

DEFAULT_THEME = "dark"

FONT_FAMILY = "Segoe UI, -apple-system, sans-serif"


def apply_theme_vars(stylesheet: str, theme: dict[str, str]) -> str:
    import re
    def replace_var(match):
        var_name = match.group(1)
        var_name_clean = var_name.replace("-", "_")
        return theme.get(var_name_clean, match.group(0))
    return re.sub(r"var\(--([\w-]+)\)", replace_var, stylesheet)


def theme_choices() -> list[tuple[str, str]]:
    order = ["dark", "light", "midnight_blue", "warm_amber"]
    return [(key, THEMES[key]["label"]) for key in order if key in THEMES]


def build_stylesheet(theme_name: str = DEFAULT_THEME) -> str:
    c = THEMES.get(theme_name, THEMES[DEFAULT_THEME])
    return f"""
        QMainWindow, QWidget {{
            background-color: {c['bg']};
            color: {c['text_primary']};
            font-family: {FONT_FAMILY};
            font-size: 13px;
        }}

        QLabel {{
            background: transparent;
        }}

        QWidget#bottomBarArtistContainer, QWidget#playerArtistContainer {{
            background-color: transparent;
            background: transparent;
            border: none;
        }}

        QLabel#bottomBarTitle {{
            font-weight: 600;
        }}

        QLabel#clickableLabel:hover, QLabel#playerTitle:hover, QLabel#playerArtist:hover, QLabel#bottomBarArtist:hover, QLabel#bottomBarTitle:hover {{
            text-decoration: underline;
        }}

        QTabWidget::pane {{
            border: none;
            border-top: 1px solid {c['border']};
            top: -1px;
        }}

        QTabBar::tab {{
            background: transparent;
            color: {c['text_secondary']};
            padding: 10px 18px;
            font-size: 13px;
            font-weight: 600;
            border: none;
        }}

        QTabBar::tab:selected {{
            color: {c['text_primary']};
            border-bottom: 2px solid {c['accent']};
        }}

        QTabBar::tab:hover:!selected {{
            color: {c['text_primary']};
        }}

        QTableView, QListView {{
            background-color: {c['bg']};
            border: none;
            gridline-color: {c['border']};
            outline: none;
            color: {c['text_primary']};
            selection-background-color: {c['surface_selected']};
            selection-color: {c['text_primary']};
        }}

        QTableView::item, QListView::item {{
            padding: 6px;
            border-bottom: 1px solid {c['border']};
        }}

        QTableView::item:hover, QListView::item:hover {{
            background-color: {c['surface_hover']};
        }}

        QTableView::item:selected, QListView::item:selected {{
            background-color: {c['surface_selected']};
        }}

        QHeaderView::section {{
            background-color: {c['bg']};
            color: {c['text_secondary']};
            padding: 8px;
            border: none;
            border-bottom: 1px solid {c['border']};
            border-right: 1px solid {c['border']};
            font-weight: 600;
            font-size: 12px;
            text-transform: uppercase;
        }}

        QPushButton {{
            background-color: {c['surface']};
            color: {c['text_primary']};
            border: 1px solid {c['border']};
            border-radius: 6px;
            padding: 7px 14px;
            font-weight: 600;
        }}

        QPushButton:hover {{
            background-color: {c['surface_hover']};
        }}

        QPushButton:pressed {{
            background-color: {c['surface_selected']};
        }}

        QPushButton#accentButton {{
            background-color: {c['accent']};
            border: none;
            color: white;
        }}

        QPushButton#accentButton:hover {{
            background-color: {c['accent_hover']};
        }}

        QPushButton#iconButton {{
            background-color: transparent;
            border: none;
            border-radius: 18px;
            padding: 6px;
        }}

        QPushButton#iconButton:hover {{
            background-color: {c['surface_hover']};
        }}

        QLineEdit {{
            background-color: {c['surface']};
            border: 1px solid {c['border']};
            border-radius: 6px;
            padding: 7px 10px;
            color: {c['text_primary']};
        }}

        QLineEdit:focus {{
            border: 1px solid {c['accent']};
        }}

        QScrollBar:vertical {{
            background: transparent;
            width: 10px;
            margin: 0;
        }}

        QScrollBar::handle:vertical {{
            background: {c['border']};
            border-radius: 5px;
            min-height: 24px;
        }}

        QScrollBar::handle:vertical:hover {{
            background: {c['surface_hover']};
        }}

        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
            height: 0;
        }}

        QSlider {{
            background: transparent;
            background-color: transparent;
            border: none;
        }}

        QSlider::groove:horizontal {{
            background: {c['border']};
            height: 4px;
            border-radius: 2px;
        }}

        QSlider::handle:horizontal {{
            background: {c['text_primary']};
            width: 12px;
            height: 12px;
            margin: -4px 0;
            border-radius: 6px;
        }}

        QSlider::sub-page:horizontal {{
            background: {c['accent']};
            border-radius: 2px;
        }}

        QLabel#sectionLabel {{
            color: {c['text_secondary']};
            font-size: 12px;
            font-weight: 700;
            letter-spacing: 1px;
            text-transform: uppercase;
        }}

        QLabel#emptyStateTitle {{
            color: {c['text_primary']};
            font-size: 16px;
            font-weight: 600;
        }}

        QLabel#emptyStateSubtitle {{
            color: {c['text_secondary']};
            font-size: 13px;
        }}

        QLabel#hintLabel {{
            color: {c['text_secondary']};
            font-size: 12px;
        }}

        QLabel#separatorDefaultHint {{
            color: {c['text_secondary']};
            font-size: 11px;
            font-style: italic;
        }}

        QLabel#seekBarTime {{
            color: {c['text_secondary']};
            font-size: 11px;
        }}

        QFrame#bottomBar {{
            background-color: {c['surface']};
            border-top: 1px solid {c['border']};
        }}

        QFrame#bottomBar QWidget {{
            background: transparent;
            background-color: transparent;
        }}

        QLabel#bottomBarArt {{
            background-color: {c['surface_hover']};
            border-radius: 4px;
            color: {c['text_secondary']};
        }}

        QLabel#bottomBarArtist {{
            color: {c['text_secondary']};
            font-size: 12px;
        }}

        QProgressBar#bottomBarProgress {{
            background-color: transparent;
            border: none;
        }}

        QProgressBar#bottomBarProgress::chunk {{
            background-color: {c['accent']};
        }}

        QFrame#topBar {{
            background-color: {c['bg']};
            border-bottom: 1px solid {c['border']};
        }}
    """
