"""Offscreen Qt smoke tests with fake generation, speech and Windows actions."""

import os
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QMessageBox

from orbit.config import Settings
from orbit.memory import MemoryStore
from orbit.preferences import Preferences
from orbit.window import OrbitWindow


class WindowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.scratch = tempfile.TemporaryDirectory()
        self.addCleanup(self.scratch.cleanup)
        self.voice = Mock()
        self.voice.synthesize.return_value = (None, 0)
        self.audio = Mock()
        audio = patch("orbit.workers.windows_speak", self.audio)
        audio.start()
        self.addCleanup(audio.stop)
        self.controller = Mock()
        self.controller.execute.return_value = "Windows accepted the request, Maker."
        self.settings = Settings(database_path=Path(self.scratch.name) / "smoke.sqlite3")
        self.win = self.open_window()

    def open_window(self):
        window = OrbitWindow(self.settings, controller=self.controller, voice=self.voice)
        window.show()
        self.app.processEvents()
        self.addCleanup(self.close_window, window)
        return window

    def close_window(self, window):
        window.close()
        for thread in window.workers.threads:
            thread.join(2)
            self.assertFalse(thread.is_alive())

    def until(self, condition):
        deadline = time.monotonic() + 4
        while not condition() and time.monotonic() < deadline:
            self.app.processEvents()
            QTest.qWait(5)
        self.assertTrue(condition())

    def send(self, text):
        self.win.entry.setText(text)
        self.win.send_message()

    def confirm(self, button):
        self.until(lambda: self.win.approval_dialog is not None)
        self.win.approval_dialog.button(button).click()
        self.until(lambda: self.win.turn is None)

    def test_startup_resize_and_shutdown(self):
        self.until(lambda: self.voice.preload.called)
        self.win.resize(480, 460)
        self.app.processEvents()
        self.assertEqual(self.win.status.text(), "Ready, Maker")
        self.assertFalse(self.win.visual.grab().isNull())
        self.assertLessEqual(self.win.composer.width(), 644)

    def test_local_tools_and_subtitle_at_compact_size(self):
        from orbit.input_macros import InputMacroStore
        from orbit.models import OrbitTurn

        self.win.resize(480, 460)
        self.win.turn = OrbitTurn(999, "Example")
        self.win.on_caption(999, "This phrase is being spoken.")
        self.app.processEvents()
        self.assertTrue(self.win.subtitle.isVisible())
        self.assertLess(self.win.visual.geometry().bottom(), self.win.status.geometry().top())
        self.win.interrupt()
        self.assertFalse(self.win.subtitle.isVisible())
        self.win.on_caption(999, "Cancelled audio")
        self.assertFalse(self.win.subtitle.isVisible())

        self.win.show_history()
        self.win.history_dialog.reject()
        self.assertIsNone(self.win.history_dialog)
        store = InputMacroStore(Path(self.scratch.name) / "recordings.db")
        with patch("orbit.macro_dialog.InputMacroStore", return_value=store):
            self.win.show_macros()
        self.assertFalse(self.win.entry.isEnabled())
        self.win.macro_dialog.close()
        self.assertIsNone(self.win.macro_dialog)
        self.assertTrue(self.win.entry.isEnabled())

    def test_created_file_requires_review_and_a_selected_path(self):
        from orbit.artifacts import Artifact

        output = Path(self.scratch.name) / "draft.md"
        draft = Artifact("study_guide", "Moon craters", body="Review the effect of impacts.")
        with patch("orbit.conversation.generate_artifact", return_value=draft) as generate:
            self.send("Make revision notes about Moon craters.")
            self.until(lambda: self.win.last_artifact is draft and self.win.reply_dialog is not None)
            self.assertEqual(generate.call_args.args[1].kind, "study_guide")
        self.assertFalse(output.exists())
        with patch("orbit.create_dialog.QFileDialog.getSaveFileName", return_value=(str(output), "")):
            self.win.reply_dialog.save()
        self.assertIn("Review the effect of impacts.", output.read_text(encoding="utf-8"))

    def test_immediate_replacement_and_stale_signal_rejection(self):
        entered = threading.Event()

        def fake_stream(_messages, _callback, cancel):
            entered.set()
            cancel.event.wait(3)
            return "Stale reply"

        self.win.workers.conversation.ai.client.stream = fake_stream
        self.send("A prompt for Ollama")
        self.until(entered.is_set)
        stale_id = self.win.turn.id
        self.win.interrupt()
        self.send("Who made you?")
        self.win.events.generated.emit(stale_id, "A stale answer", "", False)
        self.win.events.speech_started.emit(stale_id, "Stale audio")
        self.until(lambda: self.win.turn is None)
        self.assertIn("Liltaz6xx created ORBIT", self.win.last_reply)
        self.assertEqual(self.win.workers.conversation.ai.store.conversation_count(), 0)

    def test_action_prompt_session_scope_and_repeat_lock(self):
        self.send("Open Notepad")
        self.confirm(QMessageBox.StandardButton.No)
        self.controller.execute.assert_not_called()
        self.send("Open Notepad")
        self.confirm(QMessageBox.StandardButton.Yes)
        self.controller.execute.assert_called_once_with("open_app", "notepad", approved=True)
        self.send("Open Notepad")
        self.until(lambda: self.win.turn is None)
        for _ in range(2):
            self.send("Lock my PC")
            self.confirm(QMessageBox.StandardButton.No)
        self.assertEqual(self.controller.execute.call_count, 2)

    def test_memory_confirmation_and_restart(self):
        self.send("Remember that my rover is silver")
        self.until(lambda: self.win.turn is None)
        self.assertIn("Saved as memory", self.win.last_reply)
        self.send("Forget memory 1")
        self.confirm(QMessageBox.StandardButton.No)
        self.assertEqual(self.win.workers.conversation.ai.store.memory_count(), 1)
        self.close_window(self.win)
        self.win = self.open_window()
        self.send("Search memories for rover")
        self.until(lambda: self.win.turn is None)
        self.assertIn("rover is silver", self.win.last_reply)
        self.send("Forget memory 1")
        self.confirm(QMessageBox.StandardButton.Yes)
        self.assertEqual(self.win.workers.conversation.ai.store.memory_count(), 0)

    def test_clear_confirmation_and_unsupported_actions(self):
        store = MemoryStore(self.settings.database_path)
        store.record_turn("A test prompt", "A stored reply.")
        store.save_memory("I like tea")
        self.send("Clear conversation")
        self.confirm(QMessageBox.StandardButton.No)
        self.assertEqual(store.conversation_count(), 1)
        self.send("Clear conversation")
        self.confirm(QMessageBox.StandardButton.Yes)
        self.assertEqual(store.conversation_count(), 0)
        self.assertEqual(store.memory_count(), 1)
        self.send("Forget everything")
        self.confirm(QMessageBox.StandardButton.Yes)
        self.assertEqual(store.memory_count(), 0)
        self.send("Execute PowerShell")
        self.until(lambda: self.win.turn is None)
        self.assertIn("approved Windows command", self.win.last_reply)
        self.controller.execute.assert_not_called()

    def test_audio_failure_leaves_reply_readable(self):
        self.audio.side_effect = OSError("unavailable")
        self.send("Who made you?")
        self.until(lambda: self.win.turn is None)
        self.assertIn("Liltaz6xx created ORBIT", self.win.last_reply)
        self.win.show_reply()
        self.assertIsNotNone(self.win.reply_dialog)
        self.assertIn("Speech could not play", self.win.detail.text())

    def test_custom_name_and_macro_approval(self):
        self.win.preferences = Preferences(name="Nova", macros={"work": ("open Notepad", "open Calculator")})
        self.win.apply_preferences()
        self.assertEqual(self.win.windowTitle(), "Nova")
        self.send("What is your name?")
        self.until(lambda: self.win.turn is None)
        self.assertIn("Nova", self.win.last_reply)
        self.send("run macro work")
        self.until(lambda: self.win.approval_dialog is not None)
        self.assertIn("Calculator", self.win.approval_dialog.text())
        self.confirm(QMessageBox.StandardButton.No)
        self.controller.execute.assert_not_called()
        self.send("run macro work")
        self.confirm(QMessageBox.StandardButton.Yes)
        self.assertEqual([call.args for call in self.controller.execute.call_args_list],
                         [("open_app", "notepad"), ("open_app", "calculator")])
