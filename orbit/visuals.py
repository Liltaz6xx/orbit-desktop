"""Artwork-backed orb animation, contained to its own paint region."""

import math

from PySide6.QtCore import QElapsedTimer, QPointF, QRectF, QSize, Qt, QTimer
from PySide6.QtGui import QColor, QPainter, QPen, QPixmap, QRadialGradient
from PySide6.QtWidgets import QWidget

from .config import ASSETS
from .theme import BG, MUTED

# Rotation speed, halo opacity and emphasis on the outer orbital path.
STATES = {
    "idle": (5.0, 0.58, 0.0),
    "thinking": (21.0, 0.88, 0.33),
    "speaking": (11.0, 0.72, 0.12),
    "executing": (31.0, 0.84, 1.0),
}


class OrbitVisual(QWidget):
    def __init__(self, meter, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(228)
        self.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent)
        self.meter = meter
        self.mode = "idle"
        self.audio_level = 0.0
        self.angle = 0.0
        self.speed, self.glow, self.emphasis = STATES[self.mode]
        self.clock = QElapsedTimer()
        self.core = QPixmap(str(ASSETS / "orbit_core.png"))
        self.halo = QPixmap(str(ASSETS / "orbit_halo.png"))
        self.scaled = None
        self.scale_key = None
        self.timer = QTimer(self, interval=33)
        self.timer.timeout.connect(self.tick)

    def set_mode(self, mode):
        if self.mode != mode:
            self.mode = mode
            self.timer.setInterval(45 if mode == "idle" else 33)

    def showEvent(self, event):
        super().showEvent(event)
        if not self.core.isNull() and not self.halo.isNull():
            self.clock.start()
            self.timer.start(45 if self.mode == "idle" else 33)

    def hideEvent(self, event):
        self.timer.stop()
        super().hideEvent(event)

    def image_size(self):
        return min(self.width() * 0.82, self.height() * 0.99, 530)

    def tick(self):
        if self.window().isMinimized():
            return
        dt = min(self.clock.restart() / 1000, 0.10)
        speed, glow, emphasis = STATES[self.mode]
        blend = 1 - math.exp(-dt * 7)
        self.speed += (speed - self.speed) * blend
        self.glow += (glow - self.glow) * blend
        self.emphasis += (emphasis - self.emphasis) * blend
        self.angle = (self.angle + self.speed * dt) % 1800
        target = self.meter.level
        decay = 1 - math.exp(-dt * (17 if target > self.audio_level else 7))
        self.audio_level += (target - self.audio_level) * decay
        radius = self.image_size() * 0.68 + 5
        self.update(QRectF(self.width() / 2 - radius, self.height() / 2 - radius,
                           2 * radius, 2 * radius).toAlignedRect())

    def scaled_art(self, size, dpr):
        key = (round(size * dpr), dpr)
        if self.scale_key != key:
            self.scale_key = key
            self.scaled = []
            for source, scale in ((self.core, 1.0), (self.halo, 1.15)):
                pixels = max(1, round(key[0] * scale))
                self.scaled.append(source.scaled(
                    QSize(pixels, pixels), Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                ))
        return self.scaled

    def draw_paths(self, painter, radius):
        painter.save()
        painter.rotate(-23)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        for width, height, alpha in ((1.44, 0.38, 35), (1.59, 0.24, 18)):
            w, h = radius * width, radius * height
            painter.setPen(QPen(QColor(201, 220, 246, alpha + round(55 * self.emphasis)), 0.9))
            painter.drawEllipse(QRectF(-w, -h, 2 * w, 2 * h))
        painter.setPen(Qt.PenStyle.NoPen)
        for index in range(4):
            a = math.radians(self.angle * 2) + index * math.tau / 4
            point = QPointF(math.cos(a) * radius * 1.44, math.sin(a) * radius * 0.38)
            painter.setBrush(QColor(215, 229, 248, 23 + round(self.emphasis * 35)))
            painter.drawEllipse(point, 4.0, 4.0)
            painter.setBrush(QColor(241, 246, 255, 190))
            painter.drawEllipse(point, 1.25, 1.25)
        painter.restore()

    def paintEvent(self, event):
        with QPainter(self) as painter:
            painter.fillRect(event.rect(), QColor(BG))
            if self.core.isNull() or self.halo.isNull():
                painter.setPen(QColor(MUTED))
                painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "Orb artwork unavailable")
                return
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
            painter.translate(self.width() / 2, self.height() / 2)
            size = self.image_size()
            core, halo = self.scaled_art(size, self.devicePixelRatioF())
            audio = self.audio_level
            pulse = 1 + 0.008 * math.sin(self.angle / 14) + 0.055 * audio
            radius = size * 0.382 * pulse

            atmosphere = QRadialGradient(QPointF(0, 0), radius * 1.65)
            atmosphere.setColorAt(0, QColor(160, 189, 224, 23 + round(34 * audio)))
            atmosphere.setColorAt(1, QColor(160, 189, 224, 0))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(atmosphere)
            painter.drawEllipse(QPointF(0, 0), radius * 1.65, radius * 1.65)
            self.draw_paths(painter, radius)

            for pixmap, width, rotation, opacity in (
                (halo, size * 1.15 * pulse, -self.angle * 0.6, min(1, self.glow + 0.25 * audio)),
                (core, size * pulse, self.angle, 0.98),
            ):
                painter.save()
                painter.rotate(rotation)
                painter.setOpacity(opacity)
                painter.drawPixmap(QRectF(-width / 2, -width / 2, width, width), pixmap, QRectF(pixmap.rect()))
                painter.restore()
