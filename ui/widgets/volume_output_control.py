"""
Volume slider + output device selector.

Per spec, both live on the Player Screen (Step 4), bottom-right corner
-- this widget is built now, ahead of the full Player Screen, so Step 4
can drop it in directly rather than building it from scratch then.
Deliberately NOT added to the Step 2 bottom bar, since the spec places
these controls on the Player Screen specifically, not the always-visible
mini-player.

This widget is engine-agnostic the same way BottomBar is: it only emits
signals and exposes setters. MainWindow (or, later, the Player Screen)
owns the actual connection to a PlaybackEngine instance.
"""

from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import QWidget, QHBoxLayout, QSlider, QLabel, QComboBox, QSizePolicy
from PyQt6.QtMultimedia import QAudioDevice


class VolumeOutputControl(QWidget):
    volume_changed = pyqtSignal(float)        # 0.0 - 1.0
    output_device_selected = pyqtSignal(object)  # QAudioDevice

    def __init__(self, parent=None):
        super().__init__(parent)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        # --- Output device selector (🎧) ---
        self.device_label = QLabel("🎧")
        self.device_label.setToolTip("Output device")
        layout.addWidget(self.device_label)

        self.device_combo = QComboBox()
        self.device_combo.setMinimumWidth(140)
        self.device_combo.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)
        layout.addWidget(self.device_combo)

        self._devices: list[QAudioDevice] = []
        self.device_combo.currentIndexChanged.connect(self._on_device_combo_changed)
        # Guard against currentIndexChanged firing while we're
        # repopulating the combo box programmatically (e.g. on refresh)
        # -- that's not a real user selection and must not re-emit.
        self._populating = False

        # --- Volume slider (🔊), far right per spec ---
        self.volume_label = QLabel("🔊")
        self.volume_label.setToolTip("Volume")
        layout.addWidget(self.volume_label)

        self.volume_slider = QSlider(Qt.Orientation.Horizontal)
        self.volume_slider.setMinimum(0)
        self.volume_slider.setMaximum(100)
        self.volume_slider.setFixedWidth(110)
        self.volume_slider.valueChanged.connect(self._on_slider_changed)
        layout.addWidget(self.volume_slider)

    # ---------- Output device ----------

    def set_available_devices(self, devices: list[QAudioDevice], current: QAudioDevice | None) -> None:
        """Repopulates the dropdown. Called once at startup and again
        if the system's device list changes (e.g. headphones plugged
        in) -- callers wire QMediaDevices.audioOutputsChanged for that,
        this widget just renders whatever list it's given.
        """
        self._populating = True
        self.device_combo.clear()
        self._devices = list(devices)

        for device in self._devices:
            label = device.description()
            if device.isDefault():
                label += " (default)"
            self.device_combo.addItem(label)

        if current is not None:
            current_id = bytes(current.id())
            for i, device in enumerate(self._devices):
                if bytes(device.id()) == current_id:
                    self.device_combo.setCurrentIndex(i)
                    break
        self._populating = False

    def _on_device_combo_changed(self, index: int) -> None:
        if self._populating:
            return
        if 0 <= index < len(self._devices):
            self.output_device_selected.emit(self._devices[index])

    # ---------- Volume ----------

    def set_volume(self, volume: float) -> None:
        """Updates the slider WITHOUT re-emitting volume_changed -- used
        when the engine's volume changes from elsewhere (e.g. restored
        on startup) so this widget doesn't echo the change back as if
        the user had dragged the slider.
        """
        self.volume_slider.blockSignals(True)
        self.volume_slider.setValue(int(round(volume * 100)))
        self.volume_slider.blockSignals(False)

    def _on_slider_changed(self, value: int) -> None:
        self.volume_changed.emit(value / 100.0)
