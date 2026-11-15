"""Manage recordings and show their state while another app has focus."""

import os
import sqlite3
import sys
from time import monotonic

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QCursor
from PySide6.QtWidgets import (
    QApplication, QDialog, QFrame, QHBoxLayout, QLabel, QLineEdit, QListWidget,
    QListWidgetItem, QMessageBox, QPushButton, QVBoxLayout, QWidget,
)

from .input_macros import (
    MAX_RECORD_SECONDS, STOP_KEY_LABEL, InputMacroSession, InputMacroStore, normalize_macro_name,
)

COUNTDOWN_SECONDS = 3
MACRO_STYLE = """
    QDialog#MacroDialog, QWidget#MacroIndicator {
        background: #10151D; color: #EDF3FC;
    }
    QLabel#MacroTitle { font: 600 23px 'Segoe UI'; color: #F3F7FF; }
    QLabel#MacroHeading { font: 600 14px 'Segoe UI'; color: #EDF3FC; }
    QLabel#MacroMuted { color: #A8B6CB; font: 13px 'Segoe UI'; }
    QLabel#MacroError { color: #FFC2B8; font: 13px 'Segoe UI'; }
    QLabel#MacroActivity { color: #FFBCB8; font: 700 14px 'Segoe UI'; }
    QFrame#MacroPanel { background: #161E29; border: 1px solid #2B394D; border-radius: 12px; }
    QListWidget#MacroList, QLineEdit#MacroName {
        background: #111923; color: #F3F7FF; border: 1px solid #314057;
        border-radius: 8px; padding: 5px; selection-background-color: #2F5076;
        selection-color: #FFFFFF;
    }
    QListWidget#MacroList::item { padding: 7px 10px; border-radius: 5px; }
    QListWidget#MacroList::item:selected { background: #2F5076; color: #FFFFFF; }
    QListWidget#MacroList::item:hover:!selected { background: #202F43; }
    QPushButton#MacroPrimary {
        background: #BCD7FF; border: 1px solid #BCD7FF; border-radius: 8px;
        color: #101C30; font: 600 13px 'Segoe UI'; padding: 7px 13px;
    }
    QPushButton#MacroPrimary:hover { background: #D8E7FF; }
    QPushButton#MacroPrimary:focus { border-color: #FFFFFF; }
    QPushButton#MacroPrimary:disabled { background: #252F3E; border-color: #374356; color: #9AA9BE; }
"""


def text_label(text="", style="MacroMuted"):
    label = QLabel(text, objectName=style)
    label.setTextFormat(Qt.TextFormat.PlainText)
    label.setWordWrap(True)
    return label


def summary(events):
    count = len(events)
    seconds = events[-1].time_ms / 1000 if events else 0
    return f"{count} {'input' if count == 1 else 'inputs'} · {seconds:.1f} s"


def has_replay_target():
    from ctypes import POINTER, WinDLL, byref
    from ctypes.wintypes import DWORD, HWND

    user32 = WinDLL("user32")
    user32.GetForegroundWindow.argtypes = ()
    user32.GetForegroundWindow.restype = HWND
    user32.GetWindowThreadProcessId.argtypes = (HWND, POINTER(DWORD))
    user32.GetWindowThreadProcessId.restype = DWORD
    foreground = user32.GetForegroundWindow()
    if not foreground:
        return False
    process = DWORD()
    user32.GetWindowThreadProcessId(foreground, byref(process))
    return process.value not in (0, os.getpid())


class MacroDialog(QDialog):
    """Create and replay explicitly named keyboard and mouse recordings."""

    def __init__(self, parent=None, store=None, session_factory=None):
        super().__init__(parent, objectName="MacroDialog")
        self.setStyleSheet(MACRO_STYLE)
        self.setWindowTitle("Macro recorder")
        self.setMinimumSize(560, 430)
        self.store = store if store is not None else InputMacroStore()
        self.session = (session_factory or InputMacroSession)()
        self.supported = sys.platform == "win32" or session_factory is not None
        self.needs_target = sys.platform == "win32" and session_factory is None
        self.recordings = {}
        self.pending = ()
        self.future = None
        self.activity = ""
        self.replay_events = ()
        self.countdown_end = 0.0
        self.timer = QTimer(self, interval=100)
        self.timer.timeout.connect(self.tick)
        self.build()
        self.refresh()
        if not self.supported:
            self.set_error("Keyboard and mouse macros are available on Windows.")

    def build(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 20, 22, 20)
        layout.setSpacing(12)
        layout.addWidget(text_label("Macro recorder", "MacroTitle"))
        layout.addWidget(text_label("Record a desktop action once, then replay its keyboard and mouse inputs."))

        panel = QFrame(objectName="MacroPanel")
        library = QVBoxLayout(panel)
        library.setContentsMargins(14, 14, 14, 14)
        heading = QHBoxLayout()
        heading.addWidget(text_label("Saved recordings", "MacroHeading"), 1)
        self.record = QPushButton("New recording", objectName="MacroPrimary")
        self.record.clicked.connect(self.record_clicked)
        heading.addWidget(self.record)
        library.addLayout(heading)
        self.empty = text_label("No recordings yet. Start one, switch to the app, and do the steps you want to replay.")
        library.addWidget(self.empty)
        self.items = QListWidget(objectName="MacroList")
        self.items.setAccessibleName("Saved macro recordings")
        self.items.currentItemChanged.connect(self.update_controls)
        self.items.itemDoubleClicked.connect(self.replay_clicked)
        library.addWidget(self.items, 1)
        actions = QHBoxLayout()
        self.detail = text_label()
        actions.addWidget(self.detail, 1)
        self.delete = QPushButton("Delete")
        self.delete.clicked.connect(self.delete_clicked)
        actions.addWidget(self.delete)
        self.replay = QPushButton("Replay", objectName="MacroPrimary")
        self.replay.clicked.connect(self.replay_clicked)
        actions.addWidget(self.replay)
        library.addLayout(actions)
        layout.addWidget(panel, 1)

        self.review = QFrame(objectName="MacroPanel")
        review = QVBoxLayout(self.review)
        review.setContentsMargins(14, 12, 14, 12)
        self.review_heading = text_label("", "MacroHeading")
        review.addWidget(self.review_heading)
        form = QHBoxLayout()
        self.name = QLineEdit(objectName="MacroName")
        self.name.setAccessibleName("Name your recording")
        self.name.setPlaceholderText("Name your recording")
        self.name.setMaxLength(40)
        self.name.returnPressed.connect(self.save_clicked)
        self.name.textChanged.connect(self.update_controls)
        form.addWidget(self.name, 1)
        discard = QPushButton("Discard")
        discard.clicked.connect(self.discard_clicked)
        form.addWidget(discard)
        self.save = QPushButton("Save", objectName="MacroPrimary")
        self.save.clicked.connect(self.save_clicked)
        form.addWidget(self.save)
        review.addLayout(form)
        self.review.hide()
        layout.addWidget(self.review)

        layout.addWidget(text_label(
            f"{STOP_KEY_LABEL} stops recording or replay. Recordings stay on this PC and include typed text. "
            "Avoid entering passwords while recording."
        ))
        self.status = text_label()
        self.status.setAccessibleName("Macro status")
        self.status.hide()
        layout.addWidget(self.status)

        self.indicator = QWidget(
            self,
            Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.WindowDoesNotAcceptFocus | Qt.WindowType.WindowTransparentForInput,
            objectName="MacroIndicator",
        )
        self.indicator.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.indicator.setAccessibleName("ORBIT macro activity")
        hud = QVBoxLayout(self.indicator)
        hud.setContentsMargins(17, 12, 17, 12)
        hud.setSpacing(2)
        self.indicator_status = text_label("", "MacroActivity")
        self.indicator_hint = text_label(f"Press {STOP_KEY_LABEL} to stop")
        hud.addWidget(self.indicator_status)
        hud.addWidget(self.indicator_hint)
        self.indicator.setFixedWidth(248)

    def set_status(self, message, *, error=False):
        self.status.setObjectName("MacroError" if error else "MacroMuted")
        self.status.style().unpolish(self.status)
        self.status.style().polish(self.status)
        self.status.setText(message)
        self.status.setVisible(bool(message))

    def set_error(self, message):
        self.set_status(message, error=True)

    def selected_name(self):
        item = self.items.currentItem()
        return item.data(Qt.ItemDataRole.UserRole) if item is not None else None

    def refresh(self, select=None):
        previous = select or self.selected_name()
        try:
            self.recordings = self.store.load()
        except (OSError, sqlite3.Error, ValueError) as exc:
            self.set_error(str(exc) if isinstance(exc, ValueError) else "Could not read the local macro library.")
            self.recordings = {}
        self.items.clear()
        for name in sorted(self.recordings):
            item = QListWidgetItem(name)
            item.setData(Qt.ItemDataRole.UserRole, name)
            self.items.addItem(item)
            if name == previous:
                self.items.setCurrentItem(item)
        if self.items.currentRow() == -1 and self.items.count():
            self.items.setCurrentRow(0)
        self.items.setVisible(bool(self.recordings))
        self.empty.setVisible(not self.recordings)
        self.update_controls()

    def update_controls(self):
        selected = self.recordings.get(self.selected_name(), ())
        idle = not self.activity and not self.pending
        self.record.setEnabled(idle and self.supported)
        self.replay.setEnabled(bool(selected) and idle and self.supported)
        self.delete.setEnabled(bool(selected) and idle)
        self.save.setEnabled(bool(self.pending and self.name.text().strip()))
        self.detail.setText(summary(selected) if selected else "")

    def record_clicked(self):
        self.begin("record")

    def replay_clicked(self):
        if not self.replay.isEnabled():
            return
        name = self.selected_name()
        events = self.recordings[name]
        message = (
            f"Replay “{name}”?\n\nSwitch to the target app during the countdown. "
            "Use the same screen arrangement as when you recorded. "
            f"Press {STOP_KEY_LABEL} to stop replay."
        )
        if self.confirm("Replay macro", message):
            self.begin("replay", events)

    def confirm(self, title, message):
        yes = QMessageBox.StandardButton.Yes
        return QMessageBox.question(self, title, message, yes | QMessageBox.StandardButton.No,
                                    QMessageBox.StandardButton.No) == yes

    def begin(self, activity, events=()):
        if self.activity or self.pending or not self.supported:
            return
        self.activity = activity
        self.replay_events = events
        self.countdown_end = monotonic() + COUNTDOWN_SECONDS
        self.set_status("")
        self.update_controls()
        self.hide()
        screen = QApplication.screenAt(QCursor.pos()) or QApplication.primaryScreen()
        if screen is not None:
            available = screen.availableGeometry()
            self.indicator.move(available.right() - self.indicator.width() - 14, available.top() + 14)
        self.update_countdown()
        self.indicator.show()
        self.timer.start()

    def update_countdown(self):
        remaining = max(1, int(self.countdown_end - monotonic() + 0.999))
        verb = "Recording" if self.activity == "record" else "Replay"
        self.indicator_status.setText(f"{verb} starts in {remaining}")
        self.indicator_hint.setText("Switch to the target app now")

    def tick(self):
        if self.future is None:
            if monotonic() < self.countdown_end:
                self.update_countdown()
                return
            try:
                if self.activity == "record":
                    self.future = self.session.start_recording()
                    self.indicator_status.setText("● Recording keyboard and mouse")
                    self.indicator_hint.setText(f"{STOP_KEY_LABEL} to stop · Up to {MAX_RECORD_SECONDS} s")
                else:
                    if self.needs_target and not has_replay_target():
                        raise ValueError("Switch to the target app during the countdown to replay the macro.")
                    self.future = self.session.start_playback(self.replay_events)
                    self.indicator_status.setText("▶ Replaying macro")
                    self.indicator_hint.setText(f"Press {STOP_KEY_LABEL} to stop")
            except (OSError, RuntimeError, ValueError) as exc:
                self.finish_activity()
                self.set_error(str(exc))
            return
        if not self.future.done():
            if self.activity == "record":
                self.indicator_hint.setText(f"{self.session.event_count} inputs · {STOP_KEY_LABEL} to stop")
            return
        future, activity = self.future, self.activity
        self.finish_activity()
        try:
            result = future.result()
        except (OSError, RuntimeError, ValueError) as exc:
            self.set_error(str(exc))
            return
        if activity == "replay":
            self.set_status("Replay ended.")
        elif result:
            self.pending = result
            self.review_heading.setText(f"Review recording · {summary(result)}")
            self.review.show()
            self.name.clear()
            self.name.setFocus()
            self.update_controls()
        else:
            self.set_status("No keyboard or mouse inputs were recorded.")

    def finish_activity(self):
        self.timer.stop()
        self.indicator.hide()
        self.activity = ""
        self.future = None
        self.replay_events = ()
        self.show()
        self.raise_()
        self.activateWindow()
        self.update_controls()

    def save_clicked(self):
        if not self.pending:
            return
        try:
            name = normalize_macro_name(self.name.text())
            if name in self.recordings and not self.confirm("Replace recording", f"Replace “{name}”?"):
                return
            self.store.save(name, self.pending)
        except (OSError, sqlite3.Error, ValueError) as exc:
            self.set_error(str(exc) if isinstance(exc, ValueError) else "Could not save the recording.")
            return
        self.clear_review()
        self.set_status(f"Saved “{name}”.")
        self.refresh(select=name)

    def clear_review(self):
        self.pending = ()
        self.review.hide()
        self.name.clear()
        self.update_controls()

    def discard_clicked(self):
        self.clear_review()
        self.set_status("Recording discarded.")

    def delete_clicked(self):
        name = self.selected_name()
        if not name or not self.confirm("Delete recording", f"Delete “{name}”?"):
            return
        try:
            self.store.delete(name)
        except (OSError, sqlite3.Error, ValueError):
            self.set_error("Could not delete the recording.")
            return
        self.set_status(f"Deleted “{name}”.")
        self.refresh()

    def closeEvent(self, event):
        # Qt skips QDialog.reject() when a hidden dialog is closed.
        if self.activity:
            self.reject()
            event.accept()
        else:
            super().closeEvent(event)

    def done(self, result):
        self.timer.stop()
        self.indicator.hide()
        self.session.close()
        super().done(result)
