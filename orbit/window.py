"""Minimal PySide6 interface for typed requests and spoken replies."""

from itertools import count
from concurrent.futures import Future
from threading import Event, Thread
from time import perf_counter
import logging

from PySide6.QtCore import QEvent, Qt, QTimer
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QApplication, QDialog, QDialogButtonBox, QFrame, QHBoxLayout, QLabel, QLineEdit,
    QMessageBox, QPushButton, QStyle, QTextEdit, QVBoxLayout, QWidget,
)

from .actions import ActionPermissions, WindowsController
from .config import APP_VERSION, ROOT, load_settings
from .discord_presence import APPLICATION_ID, DiscordPresence
from .listener import VoiceListener
from .models import AudioMeter, OrbitEvents, OrbitTurn
from .preferences import Preferences, read_preferences
from .settings_dialog import SettingsDialog
from .theme import STYLESHEET, apply_window_frame
from .updater import download_update, installed_copy, latest_update, launch_after_exit
from .visuals import OrbitVisual
from .workers import OrbitWorkers

log = logging.getLogger(__name__)
TURN_IDS = count(1)


class OrbitWindow(QWidget):
    def __init__(self, settings=None, *, controller=None, voice=None, preferences=None):
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
        self.discord_dialog = None
        self.settings_dialog = None
        self.presence = DiscordPresence(self)
        self.notices = {}
        try:
            self.preferences = preferences if preferences is not None else read_preferences()
        except ValueError as exc:
            self.preferences = Preferences()
            self.notices["settings"] = str(exc)
        self.listener = VoiceListener(self)
        self.listener.status.connect(lambda text: self.on_subsystem("microphone", text))
        self.listener.heard.connect(self.submit_spoken, Qt.ConnectionType.QueuedConnection)
        self.listen_after_stop = QTimer(self, singleShot=True, interval=600)
        self.listen_after_stop.timeout.connect(self.resume_listener)
        self.permissions = ActionPermissions()
        self.meter = AudioMeter()
        self.update_job = None
        self.installing_update = False
        self.update_cancel = Event()
        self.update_poll = QTimer(self, interval=150)
        self.update_poll.timeout.connect(self.finish_update_job)
        self.update_checks = QTimer(self, interval=60 * 60 * 1000)
        self.update_checks.timeout.connect(self.check_for_update)
        self.events = OrbitEvents(self)
        self.events.subsystem.connect(self.on_subsystem)
        self.events.approval.connect(self.on_approval)
        self.events.generated.connect(self.on_generated)
        self.events.speech_started.connect(self.on_speech_started)
        self.events.caption.connect(self.on_caption)
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
        self.apply_preferences()
        if installed_copy(ROOT) and QApplication.platformName() == "windows":
            self.update_checks.start()
            QTimer.singleShot(2000, self.check_for_update)
        if QApplication.platformName() == "windows":
            self.presence.start(APPLICATION_ID)

    def showEvent(self, event):
        super().showEvent(event)
        if QApplication.platformName() == "windows":
            apply_window_frame(self)

    def build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(30, 22, 30, 19)
        root.setSpacing(0)
        header = QHBoxLayout()
        self.brand = QLabel("ORBIT", objectName="Brand")
        self.brand.setMinimumWidth(0)
        header.addWidget(self.brand)
        header.addStretch()
        header.setSpacing(7)
        settings_button = self.header_button("Settings", QStyle.StandardPixmap.SP_FileDialogDetailedView)
        settings_button.clicked.connect(self.show_settings)
        header.addWidget(settings_button)
        discord = self.header_button("Discord", QStyle.StandardPixmap.SP_MessageBoxInformation)
        discord.setAccessibleName("Discord activity status")
        discord.clicked.connect(self.show_discord)
        header.addWidget(discord)
        self.update_button = self.header_button("Update", QStyle.StandardPixmap.SP_BrowserReload)
        self.update_button.clicked.connect(lambda: self.check_for_update(manual=True))
        header.addWidget(self.update_button)
        header.addSpacing(14)
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
        self.subtitle = QLabel(objectName="Subtitle")
        self.subtitle.setTextFormat(Qt.TextFormat.PlainText)
        self.subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.subtitle.setWordWrap(True)
        self.subtitle.hide()
        root.addWidget(self.subtitle)
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

    def header_button(self, label, icon):
        button = QPushButton(self.style().standardIcon(icon), label, objectName="HeaderAction")
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        return button

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
        self.submit_message(self.entry.text())

    def submit_spoken(self, message):
        if self.preferences.listening and self.settings_dialog is None:
            self.submit_message(message, from_microphone=True)

    def submit_message(self, message, *, from_microphone=False):
        message = message.strip()
        if self.closing or self.installing_update or self.turn is not None or not message:
            return
        turn = OrbitTurn(next(TURN_IDS), message, preferences=self.preferences, from_microphone=from_microphone)
        self.turn = turn
        self.listen_after_stop.stop()
        self.listener.stop()
        self.meter.turn_id = turn.id
        if not from_microphone:
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
        if self.turn is None and self.status.text() in {"Ready, Maker", "Stopped"}:
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

    def on_caption(self, turn_id, text):
        turn = self.current_turn(turn_id)
        if turn is not None and not turn.played:
            self.subtitle.setText(text)
            self.subtitle.show()

    def on_speech_finished(self, turn_id, _backend, error):
        turn = self.current_turn(turn_id)
        if turn is not None:
            turn.played = True
            self.subtitle.clear()
            self.subtitle.hide()
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
        self.resume_listener()

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

    def resume_listener(self):
        if (self.preferences.listening and not self.closing and self.turn is None
                and self.settings_dialog is None and QApplication.platformName() == "windows"):
            self.listener.start(self.preferences.name)

    def apply_preferences(self):
        name = self.preferences.name
        self.setWindowTitle(name)
        self.brand.setToolTip(name)
        self.brand.setText(self.brand.fontMetrics().elidedText(name, Qt.TextElideMode.ElideRight, 108))
        self.entry.setAccessibleName(f"Message to {name}")
        self.entry.setPlaceholderText(f"Message {name}")
        self.notices.pop("microphone", None)
        if self.turn is None:
            self.detail.setText(self.ready_detail())
        self.resume_listener()

    def start_update_job(self, label, function, finished):
        future = Future()
        self.update_job = (future, finished)
        self.update_button.setText(label)
        self.update_button.setEnabled(False)

        def run():
            try:
                future.set_result(function())
            except Exception as exc:
                future.set_exception(exc)

        Thread(target=run, name="ORBIT update", daemon=True).start()
        self.update_poll.start()

    def finish_update_job(self):
        future, finished = self.update_job
        if not future.done():
            return
        self.update_poll.stop()
        self.update_job = None
        self.update_button.setText("Update")
        self.update_button.setEnabled(True)
        finished(future)

    def check_for_update(self, manual=False):
        if self.closing or self.update_job is not None:
            return
        if manual and not installed_copy(ROOT):
            QMessageBox.information(self, "ORBIT update", "Install ORBIT with Windows Setup to use in-app updates.")
            return

        def checked(future):
            try:
                update = future.result()
            except Exception as exc:
                log.warning("event=update_check_failed error=%s", type(exc).__name__)
                if manual:
                    QMessageBox.warning(self, "ORBIT update", "Could not check GitHub for an update. Try again later.")
                return
            if update is None:
                if manual:
                    QMessageBox.information(self, "ORBIT update", "You have the latest build.")
                return
            self.update_button.setText("Update available")
            if manual:
                self.confirm_update(update)

        self.start_update_job("Checking…", lambda: latest_update(APP_VERSION), checked)

    def confirm_update(self, update):
        yes = QMessageBox.StandardButton.Yes
        if self.turn is not None:
            QMessageBox.information(self, "ORBIT update", "Finish or stop the current request to update.")
            return
        if QMessageBox.question(self, "ORBIT update",
                                f"Install ORBIT {update.version}? ORBIT will close and reopen after the update.",
                                yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No) != yes:
            return

        def ready(future):
            installer = None
            try:
                installer = future.result()
                launch_after_exit(installer)
            except Exception as exc:
                self.installing_update = False
                log.warning("event=update_install_failed error=%s", type(exc).__name__)
                if installer is not None:
                    installer.unlink(missing_ok=True)
                    installer.parent.rmdir()
                QMessageBox.warning(self, "ORBIT update", "Could not download or start the verified installer.")
                return
            self.close()

        self.installing_update = True
        self.start_update_job("Downloading…", lambda: download_update(update, self.update_cancel), ready)

    def show_settings(self):
        if self.settings_dialog is not None:
            self.settings_dialog.raise_()
            return
        self.listener.stop()
        dialog = SettingsDialog(self.preferences, self)
        self.settings_dialog = dialog
        dialog.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)

        def closed(result):
            self.settings_dialog = None
            if result == QDialog.DialogCode.Accepted:
                self.preferences = dialog.preferences
                self.notices.pop("settings", None)
            self.apply_preferences()

        dialog.finished.connect(closed)
        dialog.open()

    def show_discord(self):
        if self.discord_dialog is not None:
            self.discord_dialog.raise_()
            self.discord_dialog.activateWindow()
            return
        dialog = QDialog(self)
        self.discord_dialog = dialog
        dialog.setWindowTitle("Discord activity")
        dialog.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        dialog.finished.connect(lambda: setattr(self, "discord_dialog", None))
        layout = QVBoxLayout(dialog)
        hint = QLabel("ORBIT advertises its activity while the app is open. "
                      "Visibility follows the activity-sharing settings in Discord. "
                      "Conversations and saved memories stay local.")
        hint.setWordWrap(True)
        layout.addWidget(hint)
        feedback = QLabel(self.presence.status)
        feedback.setWordWrap(True)
        layout.addWidget(feedback)
        self.presence.status_changed.connect(feedback.setText)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(dialog.close)
        layout.addWidget(buttons)
        dialog.resize(410, dialog.sizeHint().height())
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
        self.subtitle.clear()
        self.subtitle.hide()
        if self.approval_dialog is not None:
            self.approval_dialog.reject()
        self.meter.turn_id = 0
        log.info("event=turn_cancelled turn=%d", turn.id)
        self.set_state("Stopped", self.ready_detail())
        self.update_send()
        self.entry.setFocus()
        self.listen_after_stop.start()

    def closeEvent(self, event):
        self.closing = True
        self.update_checks.stop()
        self.update_poll.stop()
        self.update_cancel.set()
        self.listen_after_stop.stop()
        self.listener.stop()
        self.presence.stop()
        self.turn = None
        if self.approval_dialog is not None:
            self.approval_dialog.reject()
        self.workers.close()
        event.accept()
