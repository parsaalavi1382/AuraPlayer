"""
LyricsPanel widget: displays synced (.lrc) and unsynced (.txt, embedded) lyrics.
Features smooth scrolling, karaoke-style highlighting of active lines,
manual scroll sync recovery via direct click or sync button, and an embedded lyrics editor dialog.
"""

from __future__ import annotations

import os
import re
from PyQt6.QtCore import Qt, pyqtSignal, QPropertyAnimation, QEasingCurve
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QScrollArea,
    QFrame, QTextEdit, QDialog, QDialogButtonBox, QMessageBox, QSizePolicy,
)
from PyQt6.QtGui import QFont, QColor, QPainter, QLinearGradient, QPen

from core.library_store import LibraryStore
from core.models import Track
from mutagen import File as MutagenFile
from mutagen.id3 import ID3
from mutagen.mp4 import MP4


def parse_line_syllables(text: str, default_start_time: float) -> tuple[str, list[dict] | None]:
    tag_pattern = re.compile(r'<(\d+):(\d+(?:\.\d+)?)[>]?>')
    matches = list(tag_pattern.finditer(text))
    if not matches:
        return text, None

    syllables = []
    if matches[0].start() > 0:
        pre_text = text[0:matches[0].start()]
        if pre_text.strip():
            syllables.append({"text": pre_text, "time": default_start_time})

    for idx, match in enumerate(matches):
        try:
            minutes = int(match.group(1))
            seconds = float(match.group(2))
            total_seconds = minutes * 60 + seconds
        except (ValueError, TypeError):
            total_seconds = default_start_time

        start_idx = match.end()
        end_idx = matches[idx+1].start() if idx + 1 < len(matches) else len(text)
        s_text = text[start_idx:end_idx]
        syllables.append({"text": s_text, "time": total_seconds})

    clean_text = tag_pattern.sub('', text)
    return clean_text, syllables


def parse_lrc(lrc_text: str) -> list[tuple[float, str, list[dict] | None]]:
    lines = lrc_text.splitlines()
    raw_lyrics = []
    pattern = re.compile(r'\[(\d+):(\d+(?:\.\d+)?)]')

    for line in lines:
        line = line.strip()
        if not line:
            continue
        matches = list(pattern.finditer(line))
        if not matches:
            continue

        last_match_end = matches[-1].end()
        text = line[last_match_end:].strip()

        for m in matches:
            try:
                minutes = int(m.group(1))
                seconds = float(m.group(2))
                total_seconds = minutes * 60 + seconds
                raw_lyrics.append((total_seconds, text))
            except (ValueError, TypeError):
                continue

    grouped = {}
    for ts, text in raw_lyrics:
        key = round(ts, 2)
        if key not in grouped:
            grouped[key] = []
        grouped[key].append(text)

    lyrics = []
    for ts in sorted(grouped.keys()):
        merged_text = "\n".join(grouped[ts])
        clean_text, syllables = parse_line_syllables(merged_text, ts)
        lyrics.append((ts, clean_text, syllables))

    return lyrics


class LyricLabel(QLabel):
    seek_requested = pyqtSignal(float)

    def __init__(self, text: str, timestamp: float, end_time: float, idx: int, syllables: list[dict] | None, theme_colors: dict, is_synced: bool, parent=None):
        super().__init__(parent)
        self.raw_text = text
        self.timestamp = timestamp
        self.end_time = end_time
        self.idx = idx
        self._current_position = 0.0
        self.theme_colors = theme_colors
        self.is_synced = is_synced
        self.is_active = False
        self.hovered = False

        self.syllables = []
        if syllables:
            for idx_s, s in enumerate(syllables):
                s_time = s["time"]
                if idx_s + 1 < len(syllables):
                    s_end = syllables[idx_s+1]["time"]
                else:
                    s_end = end_time
                if s_end < s_time:
                    s_end = s_time + 1.0
                self.syllables.append({
                    "text": s["text"],
                    "time": s_time,
                    "end_time": s_end,
                    "char_start": 0,
                    "char_end": 0
                })
            
            current_char_idx = 0
            for s in self.syllables:
                s_len = len(s["text"])
                s["char_start"] = current_char_idx
                s["char_end"] = current_char_idx + s_len
                current_char_idx += s_len

        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self.setMinimumWidth(50)
        self.setWordWrap(True)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setMouseTracking(True)
        
        if self.is_synced:
            self.setCursor(Qt.CursorShape.PointingHandCursor)
        else:
            self.setCursor(Qt.CursorShape.ArrowCursor)

        self.setText(self.raw_text)
        self.update_appearance(0.0)

    def mouseMoveEvent(self, event) -> None:
        if not self.is_synced:
            super().mouseMoveEvent(event)
            return

        if not self.hovered:
            self.hovered = True
            self.update_appearance(self._current_position)
            self.setCursor(Qt.CursorShape.PointingHandCursor)
        
        super().mouseMoveEvent(event)

    def leaveEvent(self, event) -> None:
        if not self.is_synced:
            super().leaveEvent(event)
            return
        
        if self.hovered:
            self.hovered = False
            self.update_appearance(self._current_position)
            self.setCursor(Qt.CursorShape.ArrowCursor)
        
        super().leaveEvent(event)

    def mousePressEvent(self, event) -> None:
        if not self.is_synced:
            super().mousePressEvent(event)
            return
        
        if event.button() == Qt.MouseButton.LeftButton:
            self.seek_requested.emit(self.timestamp)
            event.accept()
            return
        
        super().mousePressEvent(event)

    def set_active(self, active: bool, position_seconds: float) -> None:
        self.is_active = active
        self.update_appearance(position_seconds)

    def update_appearance(self, position_seconds: float) -> None:
        self._current_position = position_seconds
        self.setText(self.raw_text)
        self.update_style()
        self.update()

    def update_style(self) -> None:
        accent = self.theme_colors.get('accent', '#6C5CE7')
        text_secondary = self.theme_colors.get('text_secondary', '#9AA0AC')
        text_primary = self.theme_colors.get('text_primary', '#EDEFF2')

        font = QFont("Segoe UI", 16 if self.is_active else 13, QFont.Weight.Bold if self.is_active else QFont.Weight.Normal)
        if self.hovered and self.is_synced:
            font.setUnderline(True)
        self.setFont(font)

        if self.is_active:
            if not self.syllables:
                self.setStyleSheet(f"color: {accent}; font-weight: bold; background-color: transparent; border: none; padding: 6px 12px;")
            else:
                self.setStyleSheet(f"background-color: transparent; border: none; padding: 6px 12px;")
        else:
            color = text_primary if (self.hovered and self.is_synced) else text_secondary
            self.setStyleSheet(f"color: {color}; background-color: transparent; border: none; padding: 6px 12px;")

    def paintEvent(self, event) -> None:
        if self.is_active and self.syllables:
            painter = QPainter(self)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)

            total_chars = len(self.raw_text)
            progress_char_fraction = 0.0
            if total_chars > 0:
                completed_chars = 0.0
                for s in self.syllables:
                    s_len = s["char_end"] - s["char_start"]
                    if self._current_position >= s["end_time"]:
                        completed_chars += s_len
                    elif self._current_position <= s["time"]:
                        pass
                    else:
                        duration = s["end_time"] - s["time"]
                        frac = (self._current_position - s["time"]) / duration if duration > 0 else 0.0
                        completed_chars += frac * s_len
                progress_char_fraction = completed_chars / total_chars

            font = self.font()
            if self.hovered and self.is_synced:
                font.setUnderline(True)
            painter.setFont(font)

            rect = self.rect().adjusted(12, 6, -12, -6)
            
            text_width = self.fontMetrics().horizontalAdvance(self.raw_text)
            x_start = max(12, (self.width() - text_width) // 2)
            x_end = min(self.width() - 12, x_start + text_width)
            
            progress_x = x_start + progress_char_fraction * (x_end - x_start)
            p_frac = progress_x / self.width() if self.width() > 0 else 0.0
            p_frac = max(0.0, min(1.0, p_frac))
            
            transition_width = 15 / self.width() if self.width() > 0 else 0.05
            p_end = min(1.0, p_frac + transition_width)
            
            gradient = QLinearGradient(0, 0, self.width(), 0)
            accent_color = QColor(self.theme_colors.get('accent', '#6C5CE7'))
            text_color = QColor(self.theme_colors.get('text_secondary', '#9AA0AC'))
            
            gradient.setColorAt(0.0, accent_color)
            gradient.setColorAt(p_frac, accent_color)
            gradient.setColorAt(p_end, text_color)
            gradient.setColorAt(1.0, text_color)
            
            pen = QPen()
            pen.setBrush(gradient)
            painter.setPen(pen)
            
            align = Qt.AlignmentFlag.AlignCenter | Qt.TextFlag.TextWordWrap
            painter.drawText(rect, align, self.raw_text)
            painter.end()
        else:
            super().paintEvent(event)


class LyricsEditorDialog(QDialog):
    def __init__(self, track_title: str, current_lyrics: str, theme_colors: dict, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"Edit Lyrics — {track_title}")
        
        import os
        from PyQt6.QtGui import QIcon
        logo_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "assets", "logo.png")
        if os.path.exists(logo_path):
            self.setWindowIcon(QIcon(logo_path))

        self.resize(500, 550)

        bg = theme_colors.get("surface", "#1C1F26")
        text = theme_colors.get("text_primary", "#EDEFF2")
        border = theme_colors.get("border", "#2E323C")
        accent = theme_colors.get("accent", "#6C5CE7")

        self.setStyleSheet(f"""
            QDialog {{
                background-color: {theme_colors.get("bg", "#14161A")};
                color: {text};
            }}
            QLabel {{
                color: {text};
            }}
            QTextEdit {{
                background-color: {bg};
                color: {text};
                border: 1px solid {border};
                border-radius: 6px;
                padding: 8px;
                font-family: Consolas, Monaco, monospace;
                font-size: 13px;
            }}
            QPushButton {{
                background-color: {bg};
                color: {text};
                border: 1px solid {border};
                border-radius: 6px;
                padding: 6px 14px;
                font-weight: bold;
            }}
            QPushButton:hover {{
                background-color: {theme_colors.get("surface_hover", "#262A33")};
            }}
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        info_lbl = QLabel(
            "Paste synced lyrics (.lrc) with [mm:ss.xx] timestamps, or plain text.\n"
            "Synced lyrics will scroll automatically during playback."
        )
        info_lbl.setFont(QFont("Segoe UI", 10))
        info_lbl.setWordWrap(True)
        info_lbl.setStyleSheet(f"color: {theme_colors.get('text_secondary', '#9AA0AC')};")
        layout.addWidget(info_lbl)

        self.editor = QTextEdit()
        self.editor.setPlainText(current_lyrics)
        layout.addWidget(self.editor, stretch=1)

        self.buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        layout.addWidget(self.buttons)

    def get_lyrics_text(self) -> str:
        return self.editor.toPlainText()


class LyricsPanel(QFrame):
    def __init__(self, store: LibraryStore, engine, parent=None):
        super().__init__(parent)
        self.store = store
        self.engine = engine

        self._current_track_path: str | None = None
        self._parsed_lyrics: list[tuple[float, str, list[dict] | None]] = []
        self._raw_lyrics = ""
        self._is_synced = False
        self._active_lyric_idx = -1

        self._user_scrolling = False
        self._is_auto_scrolling = False
        self._scroll_anim: QPropertyAnimation | None = None
        self._theme_colors: dict = {}

        self.setObjectName("lyricsPanel")
        self.setFrameShape(QFrame.Shape.NoFrame)

        self._build_ui()
        self._wire_signals()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.scroll_area = QScrollArea(self)
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        # اسکرول‌بار فعال شد
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)

        self.scroll_content = QWidget()
        self.lyrics_layout = QVBoxLayout(self.scroll_content)
        self.lyrics_layout.setContentsMargins(16, 120, 16, 120)
        self.lyrics_layout.setSpacing(16)

        self.scroll_area.setWidget(self.scroll_content)
        layout.addWidget(self.scroll_area, stretch=1)

        controls_bar = QHBoxLayout()
        controls_bar.setContentsMargins(16, 8, 16, 16)
        controls_bar.setSpacing(12)

        # بازگشت دکمه Sync
        self.sync_btn = QPushButton("Sync ↑")
        self.sync_btn.setFixedSize(70, 30)
        self.sync_btn.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
        self.sync_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.sync_btn.hide()
        controls_bar.addWidget(self.sync_btn)

        controls_bar.addStretch()

        self.edit_btn = QPushButton("✏ Edit")
        self.edit_btn.setFixedSize(70, 30)
        self.edit_btn.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
        self.edit_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        controls_bar.addWidget(self.edit_btn)

        self.bottom_overlay = QWidget(self)
        self.bottom_overlay.setLayout(controls_bar)
        self.bottom_overlay.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        layout.addWidget(self.bottom_overlay)

    def _wire_signals(self) -> None:
        self.edit_btn.clicked.connect(self._on_edit_clicked)
        self.sync_btn.clicked.connect(self._on_sync_clicked)
        self.scroll_area.verticalScrollBar().valueChanged.connect(self._on_scroll_value_changed)

        self.engine.position_changed.connect(self._on_position_changed)
        self.engine.track_changed.connect(self.load_track_lyrics)

    def apply_theme(self, theme_colors: dict) -> None:
        self._theme_colors = theme_colors
        bg = theme_colors.get("surface", "#1C1F26")
        border = theme_colors.get("border", "#2E323C")
        accent = theme_colors.get("accent", "#6C5CE7")
        text = theme_colors.get("text_primary", "#EDEFF2")

        self.scroll_area.setStyleSheet("background: transparent;")
        self.scroll_content.setStyleSheet("background: transparent;")

        button_style = f"""
            QPushButton {{
                background-color: {bg};
                color: {text};
                border: 1px solid {border};
                border-radius: 15px;
                font-weight: bold;
            }}
            QPushButton:hover {{
                background-color: {theme_colors.get("surface_hover", "#262A33")};
                border-color: {accent};
            }}
        """
        self.edit_btn.setStyleSheet(button_style)
        self.sync_btn.setStyleSheet(button_style)

        self._rebuild_lyrics_ui()

    def load_track_lyrics(self, track_path: str) -> None:
        self._current_track_path = track_path
        self._parsed_lyrics = []
        self._raw_lyrics = ""
        self._is_synced = False
        self._active_lyric_idx = -1
        self._user_scrolling = False
        self.sync_btn.hide()

        if not track_path:
            self._rebuild_lyrics_ui()
            return

        base_path, _ = os.path.splitext(track_path)
        lrc_path = base_path + ".lrc"
        txt_path = base_path + ".txt"

        if os.path.exists(lrc_path):
            try:
                with open(lrc_path, "r", encoding="utf-8", errors="ignore") as f:
                    self._raw_lyrics = f.read()
                self._parsed_lyrics = parse_lrc(self._raw_lyrics)
                self._is_synced = True
            except Exception as e:
                print(f"Error reading LRC: {e}")

        if not self._parsed_lyrics and os.path.exists(txt_path):
            try:
                with open(txt_path, "r", encoding="utf-8", errors="ignore") as f:
                    self._raw_lyrics = f.read()
                self._parsed_lyrics = [(0.0, line.strip(), None) for line in self._raw_lyrics.splitlines() if line.strip()]
                self._is_synced = False
            except Exception as e:
                print(f"Error reading TXT: {e}")

        if not self._parsed_lyrics:
            self._raw_lyrics = self._read_embedded_lyrics(track_path)
            if self._raw_lyrics:
                if "[" in self._raw_lyrics and "]" in self._raw_lyrics:
                    self._parsed_lyrics = parse_lrc(self._raw_lyrics)
                    self._is_synced = True
                else:
                    self._parsed_lyrics = [(0.0, line.strip(), None) for line in self._raw_lyrics.splitlines() if line.strip()]
                    self._is_synced = False

        self._rebuild_lyrics_ui()

    def _read_embedded_lyrics(self, track_path: str) -> str:
        try:
            audio = MutagenFile(track_path)
            if audio is None:
                return ""

            if isinstance(audio, ID3) or (hasattr(audio, "tags") and audio.tags and isinstance(audio.tags, ID3)):
                tags = audio.tags if hasattr(audio, "tags") and audio.tags else audio
                for key in tags.keys():
                    if key.startswith("USLT"):
                        return tags[key].text
            elif hasattr(audio, "keys"):
                for key in ["lyrics", "unsynced lyrics", "unsyncedlyrics", "lyric"]:
                    for k in audio.keys():
                        if k.lower() == key:
                            val = audio[k]
                            if isinstance(val, list) and val:
                                return val[0]
                            return str(val)
            elif isinstance(audio, MP4) or (hasattr(audio, "tags") and isinstance(audio.tags, MP4)):
                tags = audio.tags if hasattr(audio, "tags") and audio.tags else audio
                if "\xa9lyr" in tags:
                    val = tags["\xa9lyr"]
                    if isinstance(val, list) and val:
                        return val[0]
                    return str(val)
        except Exception as e:
            print(f"Error reading embedded lyrics: {e}")
        return ""

    def _rebuild_lyrics_ui(self) -> None:
        while self.lyrics_layout.count() > 0:
            item = self.lyrics_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

        if not self._parsed_lyrics:
            lbl = QLabel(
                "No lyrics available offline.\n"
                "Tap '✏ Edit' to add lyrics for this track."
            )
            lbl.setFont(QFont("Segoe UI", 12))
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lbl.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
            lbl.setMinimumWidth(50)
            lbl.setStyleSheet(f"color: {self._theme_colors.get('text_secondary', '#9AA0AC')}; line-height: 1.5;")
            lbl.setWordWrap(True)
            self.lyrics_layout.addWidget(lbl)
            return

        for i, (timestamp, text, syllables) in enumerate(self._parsed_lyrics):
            if i + 1 < len(self._parsed_lyrics):
                end_time = self._parsed_lyrics[i+1][0]
            else:
                end_time = timestamp + 4.0
            lbl = LyricLabel(text, timestamp, end_time, i, syllables, self._theme_colors, self._is_synced, self)
            lbl.seek_requested.connect(self._on_seek_requested)
            self.lyrics_layout.addWidget(lbl)

    def _on_sync_clicked(self) -> None:
        """برگشت دستی اسکرول با دکمه"""
        self._user_scrolling = False
        self.sync_btn.hide()
        self._scroll_to_active(smooth=True)

    def _on_seek_requested(self, timestamp: float) -> None:
        """برگشت اسکرول و سینک با کلیک روی متن"""
        self.engine.seek(timestamp)
        self.engine.play()

        self._user_scrolling = False
        self.sync_btn.hide()

        active_idx = -1
        for i, (ts, text, syllables) in enumerate(self._parsed_lyrics):
            if timestamp >= ts:
                active_idx = i
            else:
                break

        if active_idx != self._active_lyric_idx:
            self._active_lyric_idx = active_idx
            self._update_highlights(timestamp)
            if not self._user_scrolling:
                self._scroll_to_active(smooth=True)

    def _on_position_changed(self, position_seconds: float, duration_seconds: float) -> None:
        if not self._parsed_lyrics or not self._is_synced or not self.isVisible():
            return

        active_idx = -1
        for i, (timestamp, text, syllables) in enumerate(self._parsed_lyrics):
            if position_seconds >= timestamp:
                active_idx = i
            else:
                break

        if active_idx != self._active_lyric_idx:
            self._active_lyric_idx = active_idx
            self._update_highlights(position_seconds)
            if not self._user_scrolling:
                self._scroll_to_active(smooth=True)
        else:
            if active_idx >= 0 and active_idx < self.lyrics_layout.count():
                widget = self.lyrics_layout.itemAt(active_idx).widget()
                if isinstance(widget, LyricLabel) and widget.syllables:
                    widget.update_appearance(position_seconds)

    def _update_highlights(self, position_seconds: float = 0.0) -> None:
        for i in range(self.lyrics_layout.count()):
            widget = self.lyrics_layout.itemAt(i).widget()
            if isinstance(widget, LyricLabel):
                widget.set_active(i == self._active_lyric_idx, position_seconds)

    def _scroll_to_active(self, smooth: bool = True) -> None:
        if self._active_lyric_idx < 0 or self._active_lyric_idx >= self.lyrics_layout.count():
            return

        widget = self.lyrics_layout.itemAt(self._active_lyric_idx).widget()
        if not widget:
            return

        widget_y = widget.y()
        widget_h = widget.height()
        scroll_h = self.scroll_area.height()
        target_value = widget_y - (scroll_h - widget_h) // 2

        scrollbar = self.scroll_area.verticalScrollBar()
        target_value = max(scrollbar.minimum(), min(target_value, scrollbar.maximum()))

        if smooth:
            self._is_auto_scrolling = True
            self._scroll_anim = QPropertyAnimation(scrollbar, b"value")
            self._scroll_anim.setDuration(320)
            self._scroll_anim.setEasingCurve(QEasingCurve.Type.OutCubic)
            self._scroll_anim.setStartValue(scrollbar.value())
            self._scroll_anim.setEndValue(target_value)
            self._scroll_anim.finished.connect(self._on_scroll_anim_finished)
            self._scroll_anim.start()
        else:
            scrollbar.setValue(target_value)

    def _on_scroll_anim_finished(self) -> None:
        self._is_auto_scrolling = False

    def _on_scroll_value_changed(self, value: int) -> None:
        if self._is_auto_scrolling:
            return
        if self._parsed_lyrics and self._is_synced and self._active_lyric_idx >= 0:
            self._user_scrolling = True
            self.sync_btn.show()

    def _on_edit_clicked(self) -> None:
        if not self._current_track_path:
            QMessageBox.warning(self, "No Track", "Please play a track to edit its lyrics.")
            return

        track = self.store.get_track(self._current_track_path)
        title = track.title if track else "Unknown Track"

        dlg = LyricsEditorDialog(title, self._raw_lyrics, self._theme_colors, self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            new_text = dlg.get_lyrics_text().strip()
            self._save_lyrics_to_disk(new_text)

    def _save_lyrics_to_disk(self, text: str) -> None:
        if not self._current_track_path:
            return

        base_path, _ = os.path.splitext(self._current_track_path)
        is_synced = "[" in text and "]" in text
        ext = ".lrc" if is_synced else ".txt"
        target_path = base_path + ext
        other_path = base_path + (".txt" if is_synced else ".lrc")

        try:
            if text:
                with open(target_path, "w", encoding="utf-8") as f:
                    f.write(text)
            else:
                if os.path.exists(target_path):
                    os.remove(target_path)

            if os.path.exists(other_path):
                os.remove(other_path)

            self.load_track_lyrics(self._current_track_path)
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to save lyrics file:\n{e}")