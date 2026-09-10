from PyQt6.QtWidgets import QDialog, QVBoxLayout, QLabel, QProgressBar, QPushButton, QMessageBox
from core.updater import UpdateDownloaderWorker, apply_update

class UpdateProgressDialog(QDialog):
    def __init__(self, assets: list[dict], parent=None):
        super().__init__(parent)
        self.setWindowTitle("Downloading Update")
        self.setFixedSize(400, 150)
        
        layout = QVBoxLayout(self)
        
        self.status_label = QLabel("Initializing download...")
        layout.addWidget(self.status_label)
        
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        layout.addWidget(self.progress_bar)
        
        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.clicked.connect(self._on_cancel)
        layout.addWidget(self.cancel_btn)
        
        self.worker = UpdateDownloaderWorker(assets, self)
        self.worker.progress.connect(self._on_progress)
        self.worker.finished.connect(self._on_finished)
        self.worker.error.connect(self._on_error)
        
        self.worker.start()

    def _on_progress(self, percentage: int, message: str):
        self.progress_bar.setValue(percentage)
        self.status_label.setText(message)

    def _on_finished(self, success: bool, path: str):
        if success:
            self.status_label.setText("Installing update...")
            self.cancel_btn.setEnabled(False)
            apply_update(path, self.worker.target_state)
            self.accept()
        else:
            QMessageBox.critical(self, "Update Failed", "Failed to prepare update.")
            self.reject()

    def _on_error(self, err_msg: str):
        QMessageBox.critical(self, "Update Error", err_msg)
        self.reject()

    def _on_cancel(self):
        self.worker.terminate()
        self.worker.wait()
        self.reject()
