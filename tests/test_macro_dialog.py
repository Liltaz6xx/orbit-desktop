"""Regression checks for the macro recorder dialog lifecycle."""

import os
import unittest
from concurrent.futures import Future
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from PySide6.QtWidgets import QApplication

from orbit.input_macros import InputEvent, InputMacroStore
from orbit.macro_dialog import MacroDialog

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


class FakeSession:
    def __init__(self):
        self.future = Future()
        self.event_count = 0
        self.closed = False

    def start_recording(self):
        return self.future

    def close(self):
        self.closed = True


class MacroDialogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_close_hidden_dialog_stops_recording(self):
        with TemporaryDirectory() as directory, patch("orbit.macro_dialog.COUNTDOWN_SECONDS", 0):
            store = InputMacroStore(Path(directory) / "macros.sqlite3")
            dialog = MacroDialog(store=store, session_factory=FakeSession)
            dialog.show()
            dialog.record.click()
            dialog.tick()
            self.assertTrue(dialog.indicator.isVisible())
            self.assertTrue(dialog.isHidden())
            dialog.close()
            self.assertTrue(dialog.session.closed)
            self.assertFalse(dialog.timer.isActive())
            self.assertTrue(dialog.indicator.isHidden())

    def test_reject_replay_without_foreground_target(self):
        with TemporaryDirectory() as directory, patch("orbit.macro_dialog.COUNTDOWN_SECONDS", 0):
            store = InputMacroStore(Path(directory) / "macros.sqlite3")
            events = (InputEvent(100, "move", (42, 19)),)
            store.save("sample", events)
            dialog = MacroDialog(store=store, session_factory=FakeSession)
            dialog.needs_target = True
            dialog.show()
            with patch("orbit.macro_dialog.has_replay_target", return_value=False):
                dialog.begin("replay", events)
                dialog.tick()
            self.assertTrue(dialog.isVisible())
            self.assertTrue(dialog.indicator.isHidden())
            self.assertIn("Switch to the target app", dialog.status.text())
            dialog.close()
