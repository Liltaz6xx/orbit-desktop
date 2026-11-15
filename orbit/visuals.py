"""A perspective-projected filament sphere with a responsive glass glow."""

import math

import numpy as np
from PySide6.QtCore import QElapsedTimer, QLineF, QPointF, QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QConicalGradient, QMovie, QPainter, QPainterPath, QPen, QRadialGradient
from PySide6.QtWidgets import QWidget

from .config import ASSETS

# Angular speed, radius multiplier, surface distortion and glow strength.
STATES = {
    "idle": (0.27, 1.00, 0.023, 0.62),
    "thinking": (0.80, 1.16, 0.055, 1.00),
    "speaking": (0.46, 1.12, 0.045, 0.85),
    "executing": (0.61, 1.09, 0.042, 0.78),
}
FILAMENTS = ((240, 154, 233), (244, 192, 254), (214, 191, 255), (177, 189, 255),
             (153, 218, 255), (181, 238, 255), (225, 243, 255))
LIGHT_LEVELS = (14, 30, 57, 92, 137, 185, 232)
CAMERA_DISTANCE = 4.1
PROJECTION_SCALE = math.sqrt(CAMERA_DISTANCE ** 2 - 1)


def filament_mesh():
    """Make a sphere of short, staggered tangent lines in model space."""
    rows = []
    for row, theta in enumerate(np.linspace(0.068, math.pi - 0.068, 55)):
        count = max(8, round(100 * math.sin(theta)))
        spacing = math.tau / count
        longitude = np.arange(count) * spacing + (row % 2) * spacing * 0.5
        longitude += 0.55 * math.cos(theta) + 0.17 * math.sin(3 * theta)
        ends = longitude[:, None] + np.array([-0.15, 0.15]) * spacing
        stagger = 0.009 * math.sin(5 * theta) + 0.003
        latitude = theta + np.array([-stagger, stagger])
        rows.append(np.stack((np.sin(latitude) * np.cos(ends),
                              np.broadcast_to(np.cos(latitude), ends.shape),
                              np.sin(latitude) * np.sin(ends)), axis=-1))
    return np.concatenate(rows)


class OrbitVisual(QWidget):
    def __init__(self, meter, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(130)
        self.meter = meter
        self.mode = "idle"
        self.motion_enabled = True
        self.audio_level = 0.0
        self.angle = 0.78
        self.phase = 0.0
        self.speed, self.scale, self.warp, self.glow = STATES[self.mode]
        self.mesh = filament_mesh()
        self.outline = np.linspace(0, math.tau, 97)[:-1]
        self.pens = self.make_pens()
        self.clock = QElapsedTimer()
        self.timer = QTimer(self, interval=40)
        self.timer.timeout.connect(self.tick)
        self.aurora = QMovie(str(ASSETS / "orbit_aurora.gif"), b"gif", self)
        self.aurora.setCacheMode(QMovie.CacheMode.CacheAll)

    @staticmethod
    def make_pens():
        pens = []
        for alpha in LIGHT_LEVELS:
            for rgb in FILAMENTS:
                pen = QPen(QColor(*rgb, alpha))
                pen.setWidthF(0.64 + alpha / 550)
                pen.setCapStyle(Qt.PenCapStyle.RoundCap)
                pens.append(pen)
        return pens

    def set_mode(self, mode):
        if self.mode != mode:
            self.mode = mode
            self.timer.setInterval(40 if mode == "idle" else 33)
            if not self.motion_enabled:
                self.speed, self.scale, self.warp, self.glow = STATES[mode]
                self.update()

    def set_motion_enabled(self, enabled):
        self.motion_enabled = enabled
        if enabled and self.isVisible() and not self.window().isMinimized():
            self.start_motion()
        else:
            self.stop_motion()
            self.audio_level = 0.0
            self.speed, self.scale, self.warp, self.glow = STATES[self.mode]
            self.update()

    def start_motion(self):
        self.clock.start()
        self.timer.start()
        if self.aurora.isValid():
            self.aurora.start()

    def stop_motion(self):
        self.timer.stop()
        self.aurora.stop()

    def showEvent(self, event):
        super().showEvent(event)
        if self.motion_enabled:
            self.start_motion()
        elif self.aurora.isValid():
            self.aurora.jumpToFrame(0)

    def hideEvent(self, event):
        self.stop_motion()
        super().hideEvent(event)

    def base_radius(self):
        return min(self.width() * 0.293, self.height() * 0.341, 330)

    def tick(self):
        minimized = self.window().isMinimized()
        if self.aurora.state() == QMovie.MovieState.Running and minimized:
            self.aurora.setPaused(True)
        if minimized:
            return
        if self.aurora.state() == QMovie.MovieState.Paused:
            self.aurora.setPaused(False)
        dt = min(self.clock.restart() / 1000, 0.10)
        speed, scale, warp, glow = STATES[self.mode]
        blend = 1 - math.exp(-dt * 7)
        self.speed += (speed - self.speed) * blend
        self.scale += (scale - self.scale) * blend
        self.warp += (warp - self.warp) * blend
        self.glow += (glow - self.glow) * blend
        self.angle = (self.angle + self.speed * dt) % math.tau
        self.phase = (self.phase + (1.4 + self.speed) * dt) % math.tau
        target = self.meter.level if self.mode == "speaking" else 0.0
        response = 1 - math.exp(-dt * (23 if target > self.audio_level else 8))
        self.audio_level += (target - self.audio_level) * response
        radius = self.base_radius()
        self.update(QRectF(self.width() / 2 - radius * 2.28, 0,
                           radius * 4.56, self.height()).toAlignedRect())

    def draw_aurora(self, painter, radius):
        frame = self.aurora.currentPixmap()
        if frame.isNull():
            return
        painter.save()
        # The GIF is pure black outside the waves, so it can blend into any stage.
        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Screen)
        painter.setOpacity(0.36 + 0.20 * self.glow)
        painter.drawPixmap(QRectF(-radius * 2.24, -radius * 0.94, radius * 4.48, radius * 2.38),
                           frame, QRectF(frame.rect()))
        painter.restore()

    @staticmethod
    def glow_at(painter, x, y, radius, rgb, alpha):
        grad = QRadialGradient(x, y, radius)
        grad.setColorAt(0.0, QColor(*rgb, alpha))
        grad.setColorAt(0.32, QColor(*rgb, round(alpha * 0.60)))
        grad.setColorAt(0.66, QColor(*rgb, round(alpha * 0.19)))
        grad.setColorAt(1.0, QColor(*rgb, 0))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(grad)
        painter.drawEllipse(QPointF(x, y), radius, radius)

    def draw_atmosphere(self, painter, radius):
        self.glow_at(painter, -radius * 0.43, radius * 0.24, radius * 1.29,
                     (157, 68, 225), round(99 * self.glow))
        self.glow_at(painter, radius * 0.55, -radius * 0.28, radius * 0.92,
                     (53, 106, 246), round(98 * self.glow))
        self.glow_at(painter, -radius * 0.74, radius * 0.51, radius * 0.55,
                     (247, 111, 189), round(143 * self.glow))
        self.glow_at(painter, radius * 0.82, -radius * 0.41, radius * 0.51,
                     (68, 179, 240), round(103 * self.glow))
        self.glow_at(painter, radius * 0.22, radius * 0.80, radius * 0.60,
                     (118, 99, 252), round(86 * self.glow))

    def draw_shell(self, painter, radius):
        # Layer translucent specular edges; dark stretches leave the volume visible.
        rim = QConicalGradient(0, 0, 11 + 14 * math.sin(self.phase))
        for position, color in (
            (0.0, QColor(159, 216, 255, 167)),
            (0.13, QColor(164, 220, 255, 217)),
            (0.32, QColor(191, 165, 255, 34)),
            (0.48, QColor(242, 188, 252, 140)),
            (0.59, QColor(255, 215, 245, 250)),
            (0.70, QColor(206, 161, 255, 150)),
            (0.83, QColor(183, 184, 255, 43)),
            (1.0, QColor(159, 216, 255, 167)),
        ):
            rim.setColorAt(position, color)
        outline = self.shell_path(radius)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setOpacity(0.12 + 0.18 * self.glow)
        painter.setPen(QPen(rim, 7.0))
        painter.drawPath(outline)
        painter.setOpacity(0.23 + 0.24 * self.glow)
        painter.setPen(QPen(rim, 3.5))
        painter.drawPath(outline)
        painter.setOpacity(0.76 + 0.16 * self.glow)
        painter.setPen(QPen(rim, 1.35))
        painter.drawPath(outline)
        painter.setOpacity(1)

    def distortion(self, x, y, z):
        phase = self.phase
        warp = self.warp + 0.035 * self.audio_level
        return 1 + warp * (
            0.64 * np.sin(4 * y + 3 * x + phase) * np.cos(3 * z - phase)
            + 0.36 * np.sin(6 * x - 6 * y + 2 * phase)
        )

    def shell_path(self, radius):
        depth = 1 / CAMERA_DISTANCE
        span = math.sqrt(1 - depth ** 2)
        x, y = span * np.cos(self.outline), span * np.sin(self.outline)
        tilt = 0.36 + 0.08 * math.sin(self.angle)
        z_axis = depth * math.cos(tilt) - y * math.sin(tilt)
        world_y = y * math.cos(tilt) + depth * math.sin(tilt)
        world_x = x * math.cos(self.angle) - z_axis * math.sin(self.angle)
        world_z = z_axis * math.cos(self.angle) + x * math.sin(self.angle)
        deform = self.distortion(world_x, world_y, world_z)
        scale = radius * PROJECTION_SCALE * deform / (CAMERA_DISTANCE - depth * deform)
        outline = QPainterPath()
        for i, (sx, sy) in enumerate(zip(x * scale, -y * scale)):
            if i:
                outline.lineTo(sx, sy)
            else:
                outline.moveTo(sx, sy)
        outline.closeSubpath()
        return outline

    def project(self, radius):
        x, y, z = self.mesh.transpose(2, 0, 1)
        angle = self.angle
        distortion = self.distortion(x, y, z)
        sine, cosine = math.sin(angle), math.cos(angle)
        rotated_x = x * cosine + z * sine
        rotated_z = z * cosine - x * sine
        tilt = 0.36 + 0.08 * math.sin(angle)
        sine, cosine = math.sin(tilt), math.cos(tilt)
        rotated_y = y * cosine - rotated_z * sine
        depth = rotated_z * cosine + y * sine

        # Keep the outline centered as the front hemisphere moves toward the camera.
        # The normalization makes the undeformed sphere touch its glass rim.
        factor = PROJECTION_SCALE * distortion / (CAMERA_DISTANCE - depth * distortion)
        coordinates = np.stack((rotated_x * factor * radius, -rotated_y * factor * radius), axis=-1)
        return coordinates.reshape(-1, 4), rotated_x[:, 0], rotated_y[:, 0], depth[:, 0]

    def draw_filaments(self, painter, radius):
        coordinates, x, y, z = self.project(radius)
        palette = len(FILAMENTS)
        material = (0.54 + 0.34 * x + 0.15 * y + 0.14 * np.sin(3 * y + 1.7 * z + 0.6 * self.phase))
        color = np.clip((material * palette).astype(int), 0, palette - 1)
        front = np.clip((z + 0.20) / 1.2, 0.0, 1.0)
        specular = np.exp(-((x + 0.68 + y * 0.59) / 0.36) ** 2)
        edge = (1 - np.abs(z)) ** 4
        brightness = (0.18 + front * (0.46 + 0.41 * specular) +
                      edge * (0.19 + 0.18 * specular) + 0.08 * self.glow)
        light = np.clip((brightness * len(LIGHT_LEVELS)).astype(int), 0, len(LIGHT_LEVELS) - 1)
        groups = light * palette + color
        for group, pen in enumerate(self.pens):
            subset = coordinates[groups == group]
            if subset.size:
                painter.setPen(pen)
                painter.drawLines([QLineF(*line) for line in subset.tolist()])

    def paintEvent(self, event):
        with QPainter(self) as painter:
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
            painter.translate(self.width() / 2, self.height() / 2)
            base = self.base_radius()
            radius = base * (self.scale + 0.095 * self.audio_level)
            self.draw_aurora(painter, base)
            self.draw_atmosphere(painter, radius)
            self.draw_shell(painter, radius)
            self.draw_filaments(painter, radius)
