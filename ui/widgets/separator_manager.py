"""
Separator management widget: redesign of the old single-line "custom
separator" text box, per feedback that it wasn't clear how to use.

Behavior:
  - Every known separator (5 defaults + any custom ones added) shows as
    a row: [checkbox] "separator text" [edit] [X]
  - Checkbox enables/disables that separator for splitting, without
    forgetting it (Settings.disabled_separators tracks this).
  - Default separators (",", "&", "/", "feat.", ";") cannot be removed
    or edited -- only enabled/disabled -- since deleting a default with
    no easy way back would be an easy way to footgun yourself. They
    show no [edit]/[X] buttons, which itself communicates this rather
    than needing an explanatory tooltip.
  - Custom separators (anything added via the input field) can be
    edited in place (double-click the label, or the ✎ button) or
    removed (✕ button).
  - Add a new separator by typing in the input field and either
    clicking "Add" or pressing Enter.
"""

from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QCheckBox, QPushButton,
    QLineEdit, QFrame, QMessageBox, QScrollArea,
)

DEFAULT_SEPARATORS = [",", "&", "/", "feat.", ";"]


class _SeparatorRow(QFrame):
    """One row in the separator list: checkbox + label/editor + edit/remove buttons."""

    toggled = pyqtSignal(str, bool)         # separator text, enabled
    removed = pyqtSignal(str)                # separator text (old value)
    edited = pyqtSignal(str, str)            # old text, new text

    def __init__(self, separator: str, enabled: bool, is_default: bool, parent=None):
        super().__init__(parent)
        self.separator = separator
        self.is_default = is_default
        self._editing = False

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 2, 0, 2)
        layout.setSpacing(8)

        self.checkbox = QCheckBox()
        self.checkbox.setChecked(enabled)
        self.checkbox.toggled.connect(lambda checked: self.toggled.emit(self.separator, checked))
        layout.addWidget(self.checkbox)

        display_text = "space" if separator == " " else separator
        self.label = QLabel(f'"{display_text}"')
        self.label.setMinimumWidth(90)
        layout.addWidget(self.label)

        self.edit_field = QLineEdit(separator)
        self.edit_field.hide()
        self.edit_field.returnPressed.connect(self._commit_edit)
        layout.addWidget(self.edit_field)

        layout.addStretch()

        if is_default:
            hint = QLabel("default")
            hint.setObjectName("separatorDefaultHint")
            layout.addWidget(hint)
        else:
            self.edit_btn = QPushButton("✎")
            self.edit_btn.setObjectName("iconButton")
            self.edit_btn.setFixedSize(28, 28)
            self.edit_btn.setToolTip("Edit this separator")
            self.edit_btn.clicked.connect(self._start_edit)
            layout.addWidget(self.edit_btn)

            self.remove_btn = QPushButton("✕")
            self.remove_btn.setObjectName("iconButton")
            self.remove_btn.setFixedSize(28, 28)
            self.remove_btn.setToolTip("Remove this separator")
            self.remove_btn.clicked.connect(lambda: self.removed.emit(self.separator))
            layout.addWidget(self.remove_btn)

            # Double-click the label is also an edit shortcut, per spec.
            self.label.mouseDoubleClickEvent = lambda event: self._start_edit()

    def _start_edit(self) -> None:
        self._editing = True
        self.label.hide()
        self.edit_field.setText(self.separator)
        self.edit_field.show()
        self.edit_field.setFocus()
        self.edit_field.selectAll()

    def _commit_edit(self) -> None:
        new_value = self.edit_field.text().strip()
        old_value = self.separator
        self.edit_field.hide()
        self.label.show()
        self._editing = False
        if not new_value or new_value == old_value:
            return
        self.edited.emit(old_value, new_value)


class SeparatorManagerWidget(QWidget):
    """
    Public interface for SettingsDialog:
      - load(all_separators, disabled_separators)
      - get_active_separators() -> list[str] (what to save back)
    """

    def __init__(self, parent=None):
        super().__init__(parent)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(8)

        hint = QLabel(
            'Used to split a tag like "A & B feat. C" into separate artists. '
            "Uncheck a separator to stop using it without losing it."
        )
        hint.setObjectName("hintLabel")
        hint.setWordWrap(True)
        outer.addWidget(hint)

        # Scroll area in case the user adds many custom separators.
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setMaximumHeight(220)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.rows_container = QWidget()
        self.rows_layout = QVBoxLayout(self.rows_container)
        self.rows_layout.setContentsMargins(0, 0, 0, 0)
        self.rows_layout.setSpacing(2)
        self.rows_layout.addStretch()
        scroll.setWidget(self.rows_container)
        outer.addWidget(scroll)

        add_row = QHBoxLayout()
        self.add_input = QLineEdit()
        self.add_input.setPlaceholderText('Add a separator, e.g. | or x')
        self.add_input.returnPressed.connect(self._on_add_clicked)
        add_row.addWidget(self.add_input)
        self.add_btn = QPushButton("Add")
        self.add_btn.setObjectName("accentButton")
        self.add_btn.clicked.connect(self._on_add_clicked)
        add_row.addWidget(self.add_btn)
        outer.addLayout(add_row)

        self._all_separators: list[str] = []
        self._disabled: set[str] = set()
        self._rows: dict[str, _SeparatorRow] = {}

    # ---------- Public API ----------

    def load(self, all_separators: list[str], disabled_separators: list[str]) -> None:
        self._all_separators = list(all_separators)
        self._disabled = set(disabled_separators)
        self._rebuild_rows()

    def get_all_separators(self) -> list[str]:
        return list(self._all_separators)

    def get_disabled_separators(self) -> list[str]:
        return [s for s in self._all_separators if s in self._disabled]

    def get_active_separators(self) -> list[str]:
        return [s for s in self._all_separators if s not in self._disabled]

    # ---------- Internal ----------

    def _rebuild_rows(self) -> None:
        # Clear existing rows
        for row in self._rows.values():
            row.setParent(None)
        self._rows.clear()

        # Remove the trailing stretch, rebuild, re-add stretch
        while self.rows_layout.count():
            item = self.rows_layout.takeAt(0)
            if item.widget():
                item.widget().setParent(None)

        for sep in self._all_separators:
            is_default = sep in DEFAULT_SEPARATORS
            enabled = sep not in self._disabled
            row = _SeparatorRow(sep, enabled, is_default)
            row.toggled.connect(self._on_row_toggled)
            row.removed.connect(self._on_row_removed)
            row.edited.connect(self._on_row_edited)
            self._rows[sep] = row
            self.rows_layout.addWidget(row)

        self.rows_layout.addStretch()

    def _on_row_toggled(self, separator: str, enabled: bool) -> None:
        if enabled:
            self._disabled.discard(separator)
        else:
            self._disabled.add(separator)

    def _on_row_removed(self, separator: str) -> None:
        if separator in DEFAULT_SEPARATORS:
            return  # safety net; UI already hides the button for defaults
        reply = QMessageBox.question(
            self, "Remove separator?",
            f'Remove the separator "{separator}"? Tracks will need to be '
            "rescanned/re-edited to reflect this change.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        if separator in self._all_separators:
            self._all_separators.remove(separator)
        self._disabled.discard(separator)
        self._rebuild_rows()

    def _on_row_edited(self, old_value: str, new_value: str) -> None:
        if old_value in DEFAULT_SEPARATORS:
            return  # safety net; defaults aren't editable in the UI
        if new_value in self._all_separators:
            QMessageBox.information(
                self, "Already exists",
                f'"{new_value}" is already in your separator list.'
            )
            return
        idx = self._all_separators.index(old_value) if old_value in self._all_separators else None
        if idx is not None:
            self._all_separators[idx] = new_value
        if old_value in self._disabled:
            self._disabled.discard(old_value)
            self._disabled.add(new_value)
        self._rebuild_rows()

    def _on_add_clicked(self) -> None:
        new_sep = self.add_input.text().strip()
        if not new_sep:
            return
        if new_sep in self._all_separators:
            QMessageBox.information(
                self, "Already exists",
                f'"{new_sep}" is already in your separator list.'
            )
            self.add_input.clear()
            return
        self._all_separators.append(new_sep)
        self.add_input.clear()
        self._rebuild_rows()
