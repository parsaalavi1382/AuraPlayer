from PyQt6.QtWidgets import QLabel
from PyQt6.QtCore import Qt, QRectF
from PyQt6.QtGui import QPainter, QPixmap
from PyQt6.QtCore import Qt, QRectF, QRect

def paint_pixmap_aspect_fill(painter: QPainter, target_rect: QRect, pixmap: QPixmap):
    if not pixmap or pixmap.isNull():
        return

    target_w = target_rect.width()
    target_h = target_rect.height()
    
    pm_size = pixmap.deviceIndependentSize()
    pm_w = pm_size.width()
    pm_h = pm_size.height()
    
    if pm_w == 0 or pm_h == 0 or target_w == 0 or target_h == 0:
        return

    scale_w = target_w / pm_w
    scale_h = target_h / pm_h
    scale = max(scale_w, scale_h)

    src_w = target_w / scale
    src_h = target_h / scale
    src_x = (pm_w - src_w) / 2
    src_y = (pm_h - src_h) / 2
    
    source_rect = QRectF(src_x, src_y, src_w, src_h)
    
    # We must translate the target rect so it paints at the right location in the painter
    target_rect_f = QRectF(target_rect.x(), target_rect.y(), target_w, target_h)

    painter.drawPixmap(target_rect_f, pixmap, source_rect)


class AspectLabel(QLabel):
    """
    A QLabel replacement that scales its pixmap keeping its aspect ratio,
    preventing images from stretching or squishing when resized.
    It properly respects high-DPI device pixel ratios to maintain original quality.
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self._pixmap = None

    def setScaledContents(self, scaled: bool):
        # We handle scaling ourselves in paintEvent
        pass

    def setPixmap(self, p):
        self._pixmap = p
        super().setPixmap(p)
        self.update()

    def paintEvent(self, event):
        if not self._pixmap or self._pixmap.isNull():
            super().paintEvent(event)
            return

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)

        paint_pixmap_aspect_fill(painter, self.rect(), self._pixmap)
