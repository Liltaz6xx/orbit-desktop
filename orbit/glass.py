"""Paint the stage and its translucent controls with Qt."""

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QLinearGradient, QPainter, QPainterPath, QPen, QRadialGradient
from PySide6.QtWidgets import QFrame

from .theme import BG


def paint_stage(widget):
    with QPainter(widget) as painter:
        painter.fillRect(widget.rect(), QColor(BG))
        width, height = widget.width(), widget.height()
        size = min(width, height)
        for x, y, radius, color, alpha in (
            (0.48, 0.40, 0.62, "#443671", 75),
            (0.15, 0.18, 0.40, "#40215D", 58),
            (0.64, 0.96, 0.68, "#4230A0", 61),
            (0.90, 0.50, 0.55, "#173D67", 55),
        ):
            tint = QColor(color)
            tint.setAlpha(alpha)
            shade = QRadialGradient(width * x, height * y, size * radius)
            shade.setColorAt(0, tint)
            tint.setAlpha(0)
            shade.setColorAt(1, tint)
            painter.fillRect(widget.rect(), shade)


class GlassPanel(QFrame):
    def __init__(self, name, radius, parent=None):
        super().__init__(parent, objectName=name)
        self.radius = radius

    def paintEvent(self, event):
        box = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        shape = QPainterPath()
        shape.addRoundedRect(box, self.radius, self.radius)
        with QPainter(self) as painter:
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            tint = QLinearGradient(box.topLeft(), box.bottomRight())
            tint.setColorAt(0, QColor(101, 104, 154, 86))
            tint.setColorAt(0.53, QColor(27, 29, 51, 178))
            tint.setColorAt(1, QColor(77, 63, 135, 116))
            painter.fillPath(shape, tint)
            highlight = QLinearGradient(box.topLeft(), box.bottomLeft())
            highlight.setColorAt(0, QColor(234, 226, 255, 48))
            highlight.setColorAt(0.28, QColor(211, 210, 255, 8))
            highlight.setColorAt(1, QColor(235, 218, 255, 0))
            painter.fillPath(shape, highlight)
            rim = QLinearGradient(box.topLeft(), box.bottomRight())
            rim.setColorAt(0, QColor(233, 214, 255, 216 if self.property("focused") else 146))
            rim.setColorAt(0.52, QColor(170, 164, 223, 47))
            rim.setColorAt(1, QColor(113, 173, 240, 103))
            painter.setPen(QPen(rim, 1))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawPath(shape)
