"""Minimal PySide6 interface for typed requests and spoken replies."""

from itertools import count
from time import perf_counter
import logging

from PySide6.QtCore import QEvent, Qt
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QApplication, QDialog, QDialogButtonBox, QFrame, QHBoxLayout, QLabel, QLineEdit,
    QMessageBox, QPushButton, QTextEdit, QVBoxLayout, QWidget,
)

from .actions import ActionPermissions, WindowsController
from .config import APP_VERSION, load_settings
from .models import AudioMeter, OrbitEvents, OrbitTurn
from .theme import STYLESHEET, apply_window_frame
from .visuals import OrbitVisual
from .workers import OrbitWorkers

log = logging.getLogger(__name__)
TURN_IDS = count(1)


class OrbitWindow(QWidget):
    def __init__(self, settings=None, *, controller=None, voice=None):
        super().__init__()
        self.setObjectName("Root")
        self.setWindowTitle("ORBIT")
        self.resize(960, 690)
        self.setMinimumSize(480, 460)
        self.turn = None
        self.closing = False
        self.approval_dialog = None
        self.last_reply = ""
        self.reply_dialog = None
        self.notices = {}
        self.permissions = ActionPermissions()
        self.meter = AudioMeter()
        self.events = OrbitEvents(self)
        self.events.subsystem.connect(self.on_subsystem)
        self.events.approval.connect(self.on_approval)
        self.events.generated.connect(self.on_generated)
        self.events.speech_started.connect(self.on_speech_started)
        self.events.speech_finished.connect(self.on_speech_finished)
        self.events.saved.connect(self.on_saved)
        self.build_ui()
        self.setStyleSheet(STYLESHEET)
        self.entry.setFocus()
        self.escape = QShortcut(QKeySequence("Escape"), self)
        self.escape.activated.connect(self.interrupt)
        self.workers = OrbitWorkers(settings or load_settings(), self.events, self.meter,
                                    controller if controller is not None else WindowsController(), voice)
        self.workers.start()

    def showEvent(self, event):
        super().showEvent(event)
        if QApplication.platformName() == "windows":
            apply_window_frame(self)

    def build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(30, 22, 30, 19)
        root.setSpacing(0)
        header = QHBoxLayout()
        brand = QLabel("ORBIT", objectName="Brand")
        header.addWidget(brand)
        header.addStretch()
        header.addWidget(QLabel(f"v{APP_VERSION}", objectName="Version"))
        root.addLayout(header)

        self.visual = OrbitVisual(self.meter, self)
        root.addWidget(self.visual, 1)
        self.status = QLabel("Ready, Maker", objectName="Status")
        self.status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        root.addWidget(self.status)
        root.addSpacing(5)
        self.detail = QLabel(objectName="Detail")
        self.detail.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.detail.setWordWrap(True)
        self.detail.setMinimumHeight(32)
        root.addWidget(self.detail)
        root.addSpacing(14)

        composer_area = QHBoxLayout()
        composer_area.addStretch()
        self.composer = QFrame(objectName="Composer")
        self.composer.setMaximumWidth(644)
        self.composer.setFixedHeight(60)
        row = QHBoxLayout(self.composer)
        row.setContentsMargins(17, 8, 8, 8)
        row.setSpacing(8)
        self.entry = QLineEdit(objectName="Entry")
        self.entry.setAccessibleName("Message to ORBIT")
        self.entry.setPlaceholderText("Message ORBIT")
        self.entry.setMaxLength(2000)
        self.entry.setMinimumHeight(40)
        self.entry.installEventFilter(self)
        self.entry.returnPressed.connect(self.send_message)
        self.entry.textChanged.connect(self.update_send)
        self.send = QPushButton("Send", objectName="Send")
        self.send.setFixedHeight(40)
        self.send.setMinimumWidth(76)
        self.send.setCursor(Qt.CursorShape.PointingHandCursor)
        self.send.clicked.connect(self.send_or_stop)
        row.addWidget(self.entry, 1)
        row.addWidget(self.send)
        composer_area.addWidget(self.composer, 24)
        composer_area.addStretch()
        root.addLayout(composer_area)
        root.addSpacing(8)

        footer = QHBoxLayout()
        self.hint = QLabel("Enter to send", objectName="Hint")
        self.reply = QPushButton("Read reply", objectName="Reply")
        self.reply.setCursor(Qt.CursorShape.PointingHandCursor)
        self.reply.clicked.connect(self.show_reply)
        self.reply.hide()
        footer.addWidget(self.hint)
        footer.addStretch()
        footer.addWidget(self.reply)
        footer_widget = QWidget()
        footer_widget.setLayout(footer)
        footer.setContentsMargins(4, 0, 4, 0)
        footer_widget.setMaximumWidth(644)
        footer_widget.setFixedHeight(21)
        footer_area = QHBoxLayout()
        footer_area.addStretch()
        footer_area.addWidget(footer_widget, 24)
        footer_area.addStretch()
        root.addLayout(footer_area)
        self.update_send()

    def eventFilter(self, watched, event):
        if watched is self.entry and event.type() in (QEvent.Type.FocusIn, QEvent.Type.FocusOut):
            self.composer.setProperty("focused", event.type() == QEvent.Type.FocusIn)
            self.composer.style().unpolish(self.composer)
            self.composer.style().polish(self.composer)
            self.composer.update()
        return super().eventFilter(watched, event)

    def set_state(self, title, detail, mode="idle"):
        self.status.setText(title)
        self.detail.setText(detail)
        self.visual.set_mode(mode)

    def update_send(self):
        active = self.turn is not None
        self.send.setText("Stop" if active else "Send")
        self.send.setEnabled(active or bool(self.entry.text().strip()))
        self.hint.setText("Esc to stop" if active else "Enter to send")

    def send_or_stop(self):
        if self.turn is not None:
            self.interrupt()
        else:
            self.send_message()

    def send_message(self):
        message = self.entry.text().strip()
        if self.closing or self.turn is not None or not message:
            return
        turn = OrbitTurn(next(TURN_IDS), message)
        self.turn = turn
        self.meter.turn_id = turn.id
        self.entry.clear()
        self.last_reply = ""
        if self.reply_dialog is not None:
            self.reply_dialog.close()
        self.reply.hide()
        self.set_state("Thinking", "Processing your request locally", "thinking")
        self.update_send()
        self.workers.submit(turn)

    def current_turn(self, turn_id):
        if not self.closing and self.turn is not None and self.turn.id == turn_id:
            return self.turn
        return None

    def on_subsystem(self, name, detail):
        if self.closing:
            return
        self.notices[name] = detail
        if self.turn is None and self.status.text() == "Ready, Maker":
            self.detail.setText(self.ready_detail())

    def ready_detail(self):
        return " ".join(self.notices.values())

    def on_approval(self, turn_id, approval):
        turn = self.current_turn(turn_id)
        if turn is None:
            return
        if approval.kind == "windows":
            action, target = approval.value
            if not self.permissions.needs_confirmation(action, target):
                self.set_state("Executing", "Running a Windows action", "executing")
                self.workers.decide(turn_id, True)
                return
        self.set_state("Awaiting approval", approval.title, "thinking")
        box = QMessageBox(QMessageBox.Icon.Question, approval.title, approval.description,
                          QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, self)
        box.setTextFormat(Qt.TextFormat.PlainText)
        box.setDefaultButton(QMessageBox.StandardButton.No)
        box.setEscapeButton(QMessageBox.StandardButton.No)
        box.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.approval_dialog = box

        def finished(result):
            self.approval_dialog = None
            if self.current_turn(turn_id) is None:
                return
            yes = result == QMessageBox.StandardButton.Yes
            if yes:
                if approval.kind == "windows":
                    self.permissions.approve(*approval.value)
                self.set_state("Executing", approval.title, "executing")
            self.workers.decide(turn_id, yes)

        box.finished.connect(finished)
        box.open()
        if QApplication.platformName() == "windows":
            apply_window_frame(box)

    def on_generated(self, turn_id, answer, notice, persist):
        turn = self.current_turn(turn_id)
        if turn is not None:
            turn.generated = True
            turn.answer = answer
            turn.notice = notice or turn.notice
            turn.persist = persist
            self.maybe_finish(turn)

    def on_speech_started(self, turn_id, backend):
        turn = self.current_turn(turn_id)
        if turn is not None:
            self.set_state("Speaking", backend, "speaking")

    def on_speech_finished(self, turn_id, _backend, error):
        turn = self.current_turn(turn_id)
        if turn is not None:
            turn.played = True
            if error:
                turn.notice = error
            self.maybe_finish(turn)

    def on_saved(self, turn_id, warning):
        turn = self.current_turn(turn_id)
        if turn is not None:
            turn.persist = False
            if warning:
                turn.notice = warning
            self.maybe_finish(turn)

    def maybe_finish(self, turn):
        if not turn.generated or not turn.played or turn.persist:
            return
        log.info("event=turn_finished turn=%d elapsed_ms=%.0f", turn.id,
                 (perf_counter() - turn.started_at) * 1000)
        self.turn = None
        self.meter.turn_id = 0
        self.last_reply = turn.answer
        self.reply.setVisible(bool(self.last_reply))
        self.set_state("Ready, Maker", turn.notice or self.ready_detail())
        self.update_send()
        self.entry.setFocus()

    def show_reply(self):
        if not self.last_reply:
            return
        if self.reply_dialog is not None:
            self.reply_dialog.raise_()
            self.reply_dialog.activateWindow()
            return
        dialog = QDialog(self)
        self.reply_dialog = dialog
        dialog.finished.connect(self.on_reply_closed)
        dialog.setWindowTitle("ORBIT reply")
        dialog.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        dialog.resize(540, 320)
        layout = QVBoxLayout(dialog)
        body = QTextEdit(dialog)
        body.setReadOnly(True)
        body.setPlainText(self.last_reply)
        layout.addWidget(body)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(dialog.close)
        layout.addWidget(buttons)
        dialog.open()
        if QApplication.platformName() == "windows":
            apply_window_frame(dialog)

    def on_reply_closed(self):
        self.reply_dialog = None

    def interrupt(self):
        turn = self.turn
        if turn is None or not self.workers.cancel(turn):
            return
        self.turn = None
        if self.approval_dialog is not None:
            self.approval_dialog.reject()
        self.meter.turn_id = 0
        log.info("event=turn_cancelled turn=%d", turn.id)
        self.set_state("Stopped", self.ready_detail())
        self.update_send()
        self.entry.setFocus()

    def closeEvent(self, event):
        self.closing = True
        self.turn = None
        if self.approval_dialog is not None:
            self.approval_dialog.reject()
        self.workers.close()
        event.accept()
