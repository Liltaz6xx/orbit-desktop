"""Small, high-DPI line icons for the ORBIT workspace."""

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPen, QPixmap


def action_icon(name):
    image = QPixmap(48, 48)
    image.fill(Qt.GlobalColor.transparent)
    with QPainter(image) as painter:
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.scale(2, 2)
        painter.setPen(QPen(QColor("#B9D6E3"), 1.65, Qt.PenStyle.SolidLine,
                            Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))

        def line(*points):
            painter.drawPolyline([QPointF(x, y) for x, y in points])

        if name == "settings":
            for y, x in ((6, 9), (12, 15), (18, 11)):
                line((3, y), (x - 2, y))
                line((x + 2, y), (21, y))
                painter.drawEllipse(QPointF(x, y), 2, 2)
        elif name == "discord":
            painter.drawRoundedRect(QRectF(3, 5, 18, 13), 3, 3)
            line((8, 18), (6, 21))
            for x in (8, 12, 16):
                painter.drawPoint(QPointF(x, 11.5))
        elif name == "update":
            painter.drawArc(QRectF(4, 4, 16, 16), 42 * 16, 295 * 16)
            line((20, 4), (20, 9), (15, 9))
        elif name == "history":
            painter.drawEllipse(QRectF(4, 4, 16, 16))
            line((12, 7), (12, 12), (15, 14))
        elif name == "macros":
            painter.drawEllipse(QRectF(3, 3, 18, 18))
            painter.setBrush(QColor("#9FE2D3"))
            painter.drawEllipse(QRectF(8.5, 8.5, 7, 7))
        elif name == "reply":
            line((6, 3), (15, 3), (19, 7), (19, 21), (6, 21), (6, 3))
            line((14, 3), (14, 8), (19, 8))
            line((9, 12), (16, 12))
            line((9, 16), (16, 16))
    image.setDevicePixelRatio(2)
    return QIcon(image)
