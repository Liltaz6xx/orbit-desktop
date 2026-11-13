"""Versioned SQLite storage and explicit commands for the Maker's memory."""

import re
import sqlite3
import unicodedata
from contextlib import contextmanager
from pathlib import Path

from .config import MAX_MEMORY_LENGTH, MAX_RELEVANT_MEMORIES, MAX_CONVERSATION_PAIRS

STOP_WORDS = {
    "a", "an", "the", "i", "im", "i'm", "my", "me", "you", "your",
    "that", "this", "is", "are", "was", "were", "and", "or", "of",
    "for", "to", "in", "on", "it", "with", "about", "do", "does",
    "did", "have", "has", "what", "which", "how", "who", "can",
    "remember", "forget", "memory", "note", "please", "orbit",
    "maker", "tell", "from", "at", "be", "as", "we", "our",
}

SCHEMA_VERSION = 2


def keywords(text):
    terms = set()
    for word in re.findall(r"[^\W_]+", unicodedata.normalize("NFKC", text).casefold()):
        if len(word) < 2 or word in STOP_WORDS:
            continue
        # Very light plural normalisation: projects -> project.
        if len(word) > 4 and word.endswith("s") and not word.endswith("ss"):
            word = word[:-1]
        terms.add(word)
    return terms


class MemoryStore:
    """SQLite connections are short-lived and safe across worker threads."""

    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            version = db.execute("PRAGMA user_version").fetchone()[0]
            if version == SCHEMA_VERSION:
                self.validate_schema(db)
                return
            if version not in {0, 1}:
                raise sqlite3.DatabaseError("Unsupported ORBIT memory schema.")
            db.execute("""
                CREATE TABLE IF NOT EXISTS memories (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    content TEXT NOT NULL,
                    category TEXT NOT NULL,
                    normalised TEXT NOT NULL UNIQUE,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
            """)
            db.execute("""
                CREATE TABLE IF NOT EXISTS conversations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_text TEXT NOT NULL,
                    assistant_text TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
            """)
            db.execute("CREATE INDEX IF NOT EXISTS idx_conversation_recent ON conversations(id DESC)")
            db.execute("CREATE INDEX IF NOT EXISTS idx_memory_recent ON memories(updated_at DESC, id DESC)")
            db.execute("CREATE TABLE IF NOT EXISTS context_revision (id INTEGER PRIMARY KEY CHECK(id = 1), value INTEGER NOT NULL)")
            db.execute("INSERT OR IGNORE INTO context_revision(id, value) VALUES (1, 0)")
            self.validate_schema(db)
            db.execute(f"PRAGMA user_version={SCHEMA_VERSION}")

    @contextmanager
    def connection(self):
        db = sqlite3.connect(self.path, timeout=2)
        try:
            db.row_factory = sqlite3.Row
            db.execute("PRAGMA secure_delete=ON")
            yield db
            db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    @staticmethod
    def validate_schema(db, *, require_revision=True):
        db.execute("SELECT id, content, category, normalised, created_at, updated_at FROM memories LIMIT 0")
        db.execute("SELECT id, user_text, assistant_text, created_at FROM conversations LIMIT 0")
        if require_revision and db.execute("SELECT value FROM context_revision WHERE id = 1").fetchone() is None:
            raise sqlite3.DatabaseError("Conversation revision is missing.")

    def save_memory(self, content):
        content = re.sub(r"\s+", " ", content).strip().strip(" .")
        if not content:
            raise ValueError("Please tell me what to remember.")
        if len(content) > MAX_MEMORY_LENGTH:
            raise ValueError("That note is too long. Please shorten it.")

        normalised = content.casefold()
        category = "note"
        if re.search(r"\b(prefer|preference|favourite|favorite|like to)\b", content, re.I):
            category = "preference"
        elif re.search(r"\b(project|building|developing|working on|creating)\b", content, re.I):
            category = "project"

        with self.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            key = unicodedata.normalize("NFKC", normalised).casefold()
            for row in db.execute("SELECT id, normalised FROM memories"):
                if unicodedata.normalize("NFKC", row["normalised"]).casefold() == key:
                    db.execute("UPDATE memories SET updated_at = CURRENT_TIMESTAMP WHERE id = ?", (row["id"],))
                    return row["id"], False
            cursor = db.execute("INSERT INTO memories(content, category, normalised) VALUES (?, ?, ?)",
                                (content, category, normalised))
            return cursor.lastrowid, True

    def memories(self, limit=300):
        with self.connection() as db:
            return [dict(row) for row in db.execute(
                "SELECT id, content, category, updated_at FROM memories "
                "ORDER BY updated_at DESC, id DESC LIMIT ?", (limit,)
            ).fetchall()]

    def memory_by_id(self, memory_id):
        with self.connection() as db:
            row = db.execute(
                "SELECT id, content, category FROM memories WHERE id = ?",
                (memory_id,),
            ).fetchone()
            return dict(row) if row else None

    def memory_count(self):
        with self.connection() as db:
            return db.execute("SELECT COUNT(*) FROM memories").fetchone()[0]

    def search(self, question, limit=MAX_RELEVANT_MEMORIES):
        terms = keywords(question)
        if not terms:
            return []

        scored = []
        for note in self.memories(limit=-1):
            note_terms = keywords(note["content"])
            overlap = len(terms & note_terms)
            if overlap:
                scored.append((overlap / len(note_terms) ** 0.35, note))

        return [n for _, n in sorted(scored, key=lambda pair: pair[0], reverse=True)[:limit]]

    def relevant_memories(self, question, limit=MAX_RELEVANT_MEMORIES):
        return self.search(question, limit)

    def find_to_forget(self, description):
        description = description.strip().casefold()
        requested = keywords(description)
        if not requested:
            return []
        matches = []
        for note in self.memories(limit=-1):
            content = note["content"].casefold()
            note_terms = keywords(content)
            overlap = len(requested & note_terms)
            if description in content or content in description:
                score = 100 + overlap
            elif requested and requested.issubset(note_terms):
                score = 50 + overlap
            elif overlap >= 2:
                score = overlap
            else:
                continue
            matches.append((score, note))
        return [note for score, note in sorted(matches, key=lambda x: x[0], reverse=True)]

    def related_for_deletion(self, target):
        # Include equivalent or expanded copies, without deleting facts that
        # merely mention the same topic.
        content = target["content"].casefold()
        terms = keywords(content)
        related = []
        for note in self.memories(limit=-1):
            if note["id"] == target["id"]:
                continue
            other = note["content"].casefold()
            other_terms = keywords(other)
            if ((len(content) >= 12 and content in other)
                    or (len(other) >= 12 and other in content)
                    or (len(terms) >= 2 and terms == other_terms)):
                related.append(note)
        return related

    def forget_memories(self, targets):
        """Remove selected facts and archived context in a single transaction."""
        if not targets:
            return False
        with self.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            # Verify that the confirmation still describes the selected records.
            for note in targets:
                row = db.execute("SELECT content FROM memories WHERE id = ?", (note["id"],)).fetchone()
                if not row or row["content"] != note["content"]:
                    return False
            db.executemany("DELETE FROM memories WHERE id = ?", ((note["id"],) for note in targets))
            self.clear_history(db)
            return True

    def delete_memory(self, memory_id):
        note = self.memory_by_id(memory_id)
        return bool(note and self.forget_memories([note, *self.related_for_deletion(note)]))

    def revision(self):
        with self.connection() as db:
            return db.execute("SELECT value FROM context_revision WHERE id = 1").fetchone()[0]

    def record_turn(self, question, answer, stop=None, *, revision=None):
        if not question.strip() or not answer.strip():
            return False
        with self.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            if revision is not None:
                current = db.execute("SELECT value FROM context_revision WHERE id = 1").fetchone()[0]
                if current != revision:
                    return False
            if stop is not None and stop.is_set():
                return False
            db.execute(
                "INSERT INTO conversations(user_text, assistant_text) VALUES (?, ?)",
                (question, answer),
            )
            return True

    def recent_turns(self, count=MAX_CONVERSATION_PAIRS):
        with self.connection() as db:
            rows = db.execute(
                "SELECT user_text, assistant_text FROM conversations "
                "ORDER BY id DESC LIMIT ?", (count,),
            ).fetchall()
        return [dict(row) for row in reversed(rows)]

    def conversation_count(self):
        with self.connection() as db:
            return int(db.execute("SELECT COUNT(*) FROM conversations").fetchone()[0])

    def clear_conversations(self):
        with self.connection() as db:
            self.clear_history(db)

    def clear_everything(self):
        with self.connection() as db:
            db.execute("DELETE FROM memories")
            self.clear_history(db)

    @staticmethod
    def clear_history(db):
        db.execute("DELETE FROM conversations")
        db.execute("UPDATE context_revision SET value = value + 1 WHERE id = 1")


def memory_command(message):
    text = re.sub(r"^orbit\b[\s,.:]*", "", message.strip(), flags=re.I)
    text = re.sub(r"^please\s+", "", text, flags=re.I)
    plain = text.lower().strip(" .?!")

    if plain in {
        "clear conversation", "reset conversation", "forget this conversation",
        "start a new conversation", "clear chat history", "erase chat history",
    }:
        return "clear_chat", ""

    if plain in {
        "forget everything", "forget everything about me", "erase all memory",
        "delete all memories", "wipe all memory", "clear all memories",
        "forget everything you know about me",
    }:
        return "clear_all", ""

    if plain in {
        "list memories", "show saved memories", "what do you remember about me",
        "what have you remembered", "what have you saved about me",
        "what do you remember", "tell me what you remember",
    }:
        return "list", ""

    match = re.fullmatch(r"(?:forget|delete|remove)\s+(?:saved\s+)?memory\s+(?:number\s+)?#?([0-9]{1,19})", plain)
    if match:
        return "forget_id", match.group(1)

    match = re.match(
        r"^(?:remember\s+that|save\s+(?:this\s+fact(?:\s+that)?|that)|"
        r"make a note(?:\s+that)?|note\s+that)\s+(.+)$",
        text, re.I | re.S,
    )
    if match:
        return "remember", match.group(1).strip().rstrip(".")

    match = re.match(
        r"^(?:forget(?:\s+that)?|delete\s+(?:the\s+)?(?:fact\s+)?that|"
        r"remove\s+(?:the\s+)?memory(?:\s+about)?)\s+(.+)$",
        text, re.I | re.S,
    )
    if match:
        return "forget_text", match.group(1).strip().rstrip(".")

    match = re.fullmatch(r"(?:what do you remember about|search memories for) (.+)", plain)
    if match:
        return "search", match.group(1)

    return None
