"""
Settings dialog: music folder management + artist separator config,
per spec. This is the dialog that makes folder scanning testable from
the actual UI rather than only via the Step 1 console script.
"""

from __future__ import annotations

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QListWidget, QListWidgetItem,
    QPushButton, QFileDialog, QMessageBox, QComboBox,
)

from core.library_store import LibraryStore
from ui.widgets.separator_manager import SeparatorManagerWidget
from ui.theme import theme_choices

DEFAULT_SEPARATORS = [",", "&", "/", "feat.", ";"]


class SettingsDialog(QDialog):
    # Emitted with the list of newly-added folder paths, so the main
    # window can kick off a scan immediately without this dialog needing
    # to know anything about scanning/threading.
    folders_added = pyqtSignal(list)
    folder_removed = pyqtSignal(str)
    # Emitted when a manual sync is requested by clicking "Sync Now".
    sync_requested = pyqtSignal()
    # Emitted the instant the user picks a different theme (not gated
    # behind Save) so MainWindow can re-apply the stylesheet live.
    theme_changed = pyqtSignal(str)

    def __init__(self, store: LibraryStore, parent=None):
        super().__init__(parent)
        self.store = store
        self.setWindowTitle("Settings")
        self.setMinimumSize(480, 480)

        layout = QVBoxLayout(self)
        layout.setSpacing(16)

        # --- Folders section ---
        folders_label = QLabel("MUSIC FOLDERS")
        folders_label.setObjectName("sectionLabel")
        layout.addWidget(folders_label)

        self.folder_list = QListWidget()
        self.folder_list.setMinimumHeight(140)
        layout.addWidget(self.folder_list)

        folder_btn_row = QHBoxLayout()
        self.add_folder_btn = QPushButton("Add Folder")
        self.add_folder_btn.setObjectName("accentButton")
        self.remove_folder_btn = QPushButton("Remove Selected")
        self.sync_now_btn = QPushButton("Sync Now")
        folder_btn_row.addWidget(self.add_folder_btn)
        folder_btn_row.addWidget(self.remove_folder_btn)
        folder_btn_row.addWidget(self.sync_now_btn)
        folder_btn_row.addStretch()
        layout.addLayout(folder_btn_row)

        self.add_folder_btn.clicked.connect(self._on_add_folder)
        self.remove_folder_btn.clicked.connect(self._on_remove_folder)
        self.sync_now_btn.clicked.connect(self.sync_requested.emit)

        # --- Theme section ---
        theme_label = QLabel("THEME")
        theme_label.setObjectName("sectionLabel")
        layout.addWidget(theme_label)

        theme_row = QHBoxLayout()
        theme_row.addWidget(QLabel("App theme:"))
        self.theme_combo = QComboBox()
        for key, label in theme_choices():
            self.theme_combo.addItem(label, userData=key)
        current_theme = self.store.cache.settings.theme
        current_index = self.theme_combo.findData(current_theme)
        if current_index >= 0:
            self.theme_combo.setCurrentIndex(current_index)
        theme_row.addWidget(self.theme_combo)
        theme_row.addStretch()
        layout.addLayout(theme_row)

        self.theme_combo.currentIndexChanged.connect(self._on_theme_changed)

        # --- Separator section ---
        sep_label = QLabel("ARTIST SEPARATOR")
        sep_label.setObjectName("sectionLabel")
        layout.addWidget(sep_label)

        self.separator_manager = SeparatorManagerWidget()
        self.separator_manager.load(
            self.store.cache.settings.artist_separators,
            self.store.cache.settings.disabled_separators,
        )
        layout.addWidget(self.separator_manager)

        layout.addStretch()

        # --- Save / Cancel ---
        button_row = QHBoxLayout()
        button_row.addStretch()
        self.cancel_btn = QPushButton("Cancel")
        self.save_btn = QPushButton("Save")
        self.save_btn.setObjectName("accentButton")
        button_row.addWidget(self.cancel_btn)
        button_row.addWidget(self.save_btn)
        layout.addLayout(button_row)

        self.cancel_btn.clicked.connect(self.reject)
        self.save_btn.clicked.connect(self._on_save)

        self._refresh_folder_list()

    def _refresh_folder_list(self) -> None:
        self.folder_list.clear()
        for folder in self.store.cache.settings.music_folders:
            self.folder_list.addItem(QListWidgetItem(folder))

    def _on_add_folder(self) -> None:
        import os
        folder = QFileDialog.getExistingDirectory(self, "Select Music Folder")
        if not folder:
            return
        
        # Normalize selected path
        norm_folder = os.path.normpath(os.path.abspath(folder))
        
        # Check against normalized existing paths
        existing_normalized = [
            os.path.normpath(os.path.abspath(f))
            for f in self.store.cache.settings.music_folders
        ]
        
        if norm_folder in existing_normalized:
            QMessageBox.warning(
                self, "Already added",
                "This folder (or an equivalent path) is already added to your library."
            )
            return
            
        self.store.cache.settings.music_folders.append(norm_folder)
        self.store.cache.save()
        self._refresh_folder_list()
        self.folders_added.emit([norm_folder])

    def _on_remove_folder(self) -> None:
        item = self.folder_list.currentItem()
        if not item:
            return
        folder = item.text()
        reply = QMessageBox.question(
            self,
            "Remove folder?",
            f"Remove '{folder}' from your library?\n\n"
            "This removes all tracks sourced from this folder from your "
            "library, but does not delete any files from disk.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            self.store.remove_folder(folder)
            self._refresh_folder_list()
            self.folder_removed.emit(folder)

    def _on_theme_changed(self, _index: int) -> None:
        theme_key = self.theme_combo.currentData()
        if not theme_key:
            return
        self.store.cache.settings.theme = theme_key
        self.store.cache.save()
        self.theme_changed.emit(theme_key)

    def _on_save(self) -> None:
        active = self.separator_manager.get_active_separators()
        if not active:
            QMessageBox.warning(
                self, "No separator enabled",
                "Enable at least one separator so multi-artist tags can be split correctly."
            )
            return
        self.store.cache.settings.artist_separators = self.separator_manager.get_all_separators()
        self.store.cache.settings.disabled_separators = self.separator_manager.get_disabled_separators()
        self.store.cache.save()
        self.accept()
