"""Checks that browsing and clearing history use the existing local archive."""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PySide6.QtWidgets import QApplication, QMessageBox

from orbit.history_dialog import HistoryDialog
from orbit.memory import MemoryStore


class HistoryDialogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication(["orbit-history-test", "-platform", "offscreen"])

    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.path = Path(temporary.name) / "archive.sqlite3"

    def test_reading_absent_archive_does_not_create_it(self):
        self.assertEqual(MemoryStore.history_page(self.path), [])
        self.assertFalse(self.path.exists())

    def test_history_searches_both_sides_and_pages_before_id(self):
        store = MemoryStore(self.path)
        store.record_turn("Ältere Frage", "Answer one")
        store.record_turn("Second question", "Ältere Antwort")
        store.record_turn("Third question", "Neither matches")
        newest_match, = store.history_page(self.path, "ÄLTERE", limit=1)
        self.assertEqual(newest_match["user_text"], "Second question")
        older_match, = store.history_page(self.path, "ältere", before=newest_match["id"])
        self.assertEqual(older_match["user_text"], "Ältere Frage")
        self.assertTrue(older_match["created_at"])

    def test_history_renders_literal_text_and_clears_only_after_confirmation(self):
        store = MemoryStore(self.path)
        store.save_memory("A separate note")
        store.record_turn("A question", "<b>Literal markup</b>\nA second line")
        revision = store.revision()
        dialog = HistoryDialog(self.path)
        self.addCleanup(dialog.close)
        self.assertIn("<b>Literal markup</b>\nA second line", dialog.transcript.toPlainText())

        with patch.object(QMessageBox, "question", return_value=QMessageBox.StandardButton.No):
            dialog.clear_history()
        self.assertEqual(store.conversation_count(), 1)

        with patch.object(QMessageBox, "question", return_value=QMessageBox.StandardButton.Yes):
            dialog.clear_history()
        self.assertEqual(store.conversation_count(), 0)
        self.assertEqual(store.memory_count(), 1)
        self.assertGreater(store.revision(), revision)
        self.assertIn("Completed conversations", dialog.transcript.toPlainText())
