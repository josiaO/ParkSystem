"""Aspect-preserving video canvas, independent of streams and recognition."""

from PySide6.QtCore import QRect, QSize, Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPixmap
from PySide6.QtWidgets import QLabel, QSizePolicy


class VideoCanvas(QLabel):
    clicked = Signal()
    pressed = Signal(object)
    moved = Signal(object)
    released = Signal(object)

    def __init__(self, text="", parent=None):
        super().__init__(text, parent)
        self._frame = QPixmap()
        self.fill_view = False
        self.corner_widget = None
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Expanding)

    def sizeHint(self):
        return QSize(320, 240)

    def minimumSizeHint(self):
        return QSize(120, 100)

    def setPixmap(self, pixmap):
        self._frame = pixmap
        self.update()

    def pixmap(self):
        return self._frame

    def setText(self, text):
        self._frame = QPixmap()
        super().setText(text)
        self.update()

    def image_rect(self):
        if self._frame.isNull():
            return QRect()
        mode = Qt.AspectRatioMode.KeepAspectRatioByExpanding if self.fill_view else Qt.AspectRatioMode.KeepAspectRatio
        size = self._frame.size().scaled(self.contentsRect().size(), mode)
        rect = QRect(0, 0, size.width(), size.height())
        rect.moveCenter(self.contentsRect().center())
        return rect

    def set_fill_view(self, enabled):
        self.fill_view = enabled
        self.update()

    def set_corner_widget(self, widget):
        self.corner_widget = widget
        widget.setParent(self)
        widget.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self._place_corner_widget()
        widget.show()

    def _place_corner_widget(self):
        if self.corner_widget is None:
            return
        width = min(240, max(140, self.width() * 3 // 10))
        height = min(105, max(64, width // 3 + 22))
        self.corner_widget.setGeometry(max(0, self.width()-width-8), max(0, self.height()-height-8), width, height)
        self.corner_widget.raise_()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._place_corner_widget()

    def clear(self):
        self._frame = QPixmap()
        super().clear()
        self.update()

    def normalized_point(self, pos):
        rect = self.image_rect()
        if rect.isEmpty():
            return None
        return (max(0.0, min(1.0, (pos.x()-rect.x()) / rect.width())),
                max(0.0, min(1.0, (pos.y()-rect.y()) / rect.height())))

    def paintEvent(self, event):
        if self._frame.isNull():
            super().paintEvent(event)
            return
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor("#090e16"))
        painter.drawPixmap(self.image_rect(), self._frame)

    def mousePressEvent(self, event):
        self.setFocus()
        self.pressed.emit(event.pos())
        self.clicked.emit()

    def mouseMoveEvent(self, event):
        self.moved.emit(event.pos())

    def mouseReleaseEvent(self, event):
        self.released.emit(event.pos())

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Space):
            self.clicked.emit()
        else:
            super().keyPressEvent(event)
