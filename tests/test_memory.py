"""Standard-library unit tests for ORBIT's SQLite memory subsystem."""
import tempfile
import unittest
import sqlite3
from pathlib import Path

from orbit.memory import SCHEMA_VERSION, MemoryStore, memory_command
from orbit.ai import OrbitAI


class MemoryTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.store = MemoryStore(Path(self.tempdir.name) / 'orbit_memory.sqlite3')

    def tearDown(self):
        self.tempdir.cleanup()

    def test_memory_persists_across_connections(self):
        first, created = self.store.save_memory("I'm developing a robotics project in Python")
        self.assertTrue(created)
        reopened = MemoryStore(Path(self.tempdir.name) / 'orbit_memory.sqlite3')
        records = reopened.memories()
        self.assertEqual(records[0]['id'], first)
        self.assertIn('Python', records[0]['content'])

    def test_duplicate_is_not_resaved(self):
        a, new_a = self.store.save_memory('I like Python')
        b, new_b = self.store.save_memory('i LIKE python.')
        self.assertTrue(new_a)
        self.assertFalse(new_b)
        self.assertEqual(a, b)
        self.assertEqual(len(self.store.memories()), 1)

    def test_relevant_memory(self):
        self.store.save_memory('I am building a Python robotics project')
        self.store.save_memory('I enjoy tea')
        results = self.store.relevant_memories('What robotics project am I building?')
        self.assertIn('robotics', results[0]['content'])

    def test_find_for_forgetting(self):
        saved_id, _ = self.store.save_memory('I am building a Python robotics project')
        matching = self.store.find_to_forget('building a Python robotics project')
        self.assertEqual(matching[0]['id'], saved_id)
        self.assertTrue(self.store.delete_memory(saved_id))
        self.assertEqual(len(self.store.memories()), 0)

    def test_prevent_ambiguous_stopword_forget(self):
        self.store.save_memory('I am learning Python')
        self.assertEqual(self.store.find_to_forget('the'), [])

    def test_conversations_persist(self):
        self.store.record_turn('What is Python?', 'A programming language.')
        restored = MemoryStore(Path(self.tempdir.name) / 'orbit_memory.sqlite3')
        ai = OrbitAI(restored)
        self.assertEqual(len(ai.history), 2)
        self.assertEqual(ai.history[1]['content'], 'A programming language.')

    def test_clear_conversation_preserves_fact(self):
        self.store.save_memory('I prefer a dark theme')
        self.store.record_turn('Hello', 'Hello, Maker.')
        self.store.clear_conversations()
        self.assertEqual(self.store.conversation_count(), 0)
        self.assertEqual(len(self.store.memories()), 1)

    def test_clear_everything(self):
        self.store.save_memory('I prefer a dark theme')
        self.store.record_turn('Hello', 'Hello, Maker.')
        self.store.clear_everything()
        self.assertEqual(self.store.memories(), [])
        self.assertEqual(self.store.recent_turns(), [])

    def test_commands(self):
        self.assertEqual(memory_command('ORBIT, remember that I prefer tea')[0], 'remember')
        self.assertEqual(memory_command('ORBIT, forget memory number 2'), ('forget_id', '2'))
        self.assertEqual(memory_command('Forget everything'), ('clear_all', ''))
        self.assertEqual(memory_command('Clear conversation'), ('clear_chat', ''))
        self.assertEqual(memory_command('What do you remember about me?'), ('list', ''))

    def test_legacy_schema_preserves_existing_records_and_ids(self):
        mid, _ = self.store.save_memory("My rover is silver")
        self.store.record_turn("Describe my rover", "Your rover is silver.")
        with self.store.connection() as db:
            db.execute("DROP TABLE context_revision")
            db.execute("PRAGMA user_version=0")
        restored = MemoryStore(self.store.path)
        self.assertEqual(restored.memory_by_id(mid)["content"], "My rover is silver")
        self.assertEqual(restored.recent_turns()[0]["assistant_text"], "Your rover is silver.")
        with restored.connection() as db:
            self.assertEqual(db.execute("PRAGMA user_version").fetchone()[0], SCHEMA_VERSION)

    def test_forget_removes_matching_notes_history_and_stale_writes(self):
        mid, _ = self.store.save_memory("My rover is silver")
        self.store.save_memory("My rover is silver with black wheels")
        self.store.save_memory("My rover runs Linux")
        self.store.record_turn("What colour is my rover?", "It is silver.")
        ai = OrbitAI(self.store)
        revision = self.store.revision()
        self.assertTrue(self.store.delete_memory(mid))
        self.assertEqual(ai.history, [])
        self.assertFalse(self.store.record_turn("What colour is my rover?", "Silver", revision=revision))
        reopened = MemoryStore(self.store.path)
        self.assertEqual(reopened.search("silver"), [])
        self.assertEqual(reopened.memory_count(), 1)

    def test_corrupt_database_is_preserved(self):
        path = Path(self.tempdir.name) / "corrupt.sqlite3"
        original = b"existing invalid data"
        path.write_bytes(original)
        with self.assertRaises(sqlite3.DatabaseError):
            MemoryStore(path)
        self.assertEqual(path.read_bytes(), original)


if __name__ == '__main__':
    unittest.main()
