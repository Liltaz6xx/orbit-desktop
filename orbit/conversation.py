"""Handle typed requests and prepare approvals on the conversation worker."""

import logging
import sqlite3

from .actions import ACTION_TARGETS, fast_action_route, identity_response, unsupported_action_request
from .ai import OllamaError, OrbitAI
from .memory import MemoryStore, memory_command
from .models import Approval

log = logging.getLogger(__name__)


class Conversation:
    def __init__(self, settings, controller, events, approve):
        self.settings = settings
        self.controller = controller
        self.events = events
        self.approve = approve
        self.ai = OrbitAI(None, settings)

    def open_memory(self):
        try:
            self.ai.store = MemoryStore(self.settings.database_path)
        except (OSError, sqlite3.Error) as exc:
            log.error("event=memory_open_failed error=%s", type(exc).__name__)
            self.events.subsystem.emit("memory", "Memory unavailable. Check the database path and permissions.")

    def answer(self, turn):
        command = memory_command(turn.message)
        if command:
            return self.memory(turn, *command), "", False
        identity = identity_response(turn.message)
        if identity:
            return identity, "", False
        action = fast_action_route(turn.message)
        if action:
            return self.windows(turn, *action), "", False
        if unsupported_action_request(turn.message):
            return "I couldn't match that to an approved Windows command, Maker.", "", False

        messages, notice, turn.context_revision = self.ai.build_messages(turn.message)
        try:
            reply = self.ai.client.stream(messages, turn.speak, turn.stop)
        except OllamaError as exc:
            if turn.stop.is_set():
                return "", "", False
            log.warning("event=ollama_error turn=%d detail=%s", turn.id, exc)
            reply = f"I had trouble with Ollama, Maker. {exc}"
            turn.speak(reply)
            return reply, str(exc), False
        return reply, notice, True

    def windows(self, turn, action, target):
        label = ACTION_TARGETS[action][target]
        if not self.approve(turn, Approval(
            "Windows permission", f"Allow ORBIT to {label}?" if action == "lock_pc"
            else f"Allow ORBIT to open {label}?", "windows", (action, target),
        )):
            return "Action declined, Maker."
        if turn.stop.is_set():
            return ""
        try:
            reply = self.controller.execute(action, target, approved=True)
            log.info("event=windows_action turn=%d action=%s target=%s", turn.id, action, target)
            return reply
        except ImportError as exc:
            return f"Windows information needs {exc.name or 'psutil'}. Run Setup_ORBIT.bat, Maker."
        except FileNotFoundError:
            return f"I couldn't find {label} on this computer, Maker."
        except OSError as exc:
            code = getattr(exc, "winerror", None)
            log.warning("event=windows_action_failed action=%s target=%s winerror=%s", action, target, code)
            return f"Windows couldn't complete the request for {label}, Maker."

    def memory(self, turn, command, value):
        store = self.ai.store
        if store is None:
            return "My local memory is unavailable, Maker. Run Check ORBIT to inspect the database."
        if command == "remember":
            try:
                mid, created = store.save_memory(value)
            except ValueError as exc:
                return str(exc)
            if created:
                return f"Saved as memory number {mid}, Maker."
            return f"I already have that saved as memory number {mid}, Maker."
        if command == "list":
            count = store.memory_count()
            notes = store.memories(8)
            return (f"I have {count} saved memories, Maker. {format_notes(notes)}" if notes
                    else "I have no saved memories, Maker. Say ‘remember that’ followed by the fact.")
        if command == "search":
            notes = store.search(value, limit=5)
            return format_notes(notes) if notes else "I found no matching saved memories, Maker."
        if command == "clear_chat":
            if self.approve(turn, Approval(
                "Clear conversation history", "Permanently delete all conversation history? Saved facts are kept.",
                "memory", None,
            )) and not turn.stop.is_set():
                store.clear_conversations()
                return "I cleared our conversation history, Maker."
            return "Deletion declined, Maker."
        if command == "clear_all":
            if self.approve(turn, Approval(
                "Clear all memories", "Permanently delete all saved facts and conversation history?",
                "memory", None,
            )) and not turn.stop.is_set():
                store.clear_everything()
                return "I cleared all saved facts and conversation history, Maker."
            return "Deletion declined, Maker."

        if command == "forget_id":
            number = int(value)
            target = store.memory_by_id(number) if number < 2**63 else None
        else:
            matches = store.find_to_forget(value)
            if len(matches) > 1:
                numbers = ", ".join(str(note["id"]) for note in matches[:8])
                return f"I found several possible memories, Maker. Their numbers are {numbers}. Choose a memory number."
            target = matches[0] if matches else None
        if target is None:
            return "I couldn't find that saved memory, Maker. Ask me to list memories for their numbers."
        related = store.related_for_deletion(target)
        notes = [target, *related]
        description = ("Permanently delete the selected fact, matching saved notes and all conversation history?\n\n"
                       + format_notes(notes))
        if not self.approve(turn, Approval("Forget saved memory", description, "memory", None)) or turn.stop.is_set():
            return "Deletion declined, Maker."
        if store.forget_memories(notes):
            return f"I deleted memory {target['id']} and cleared our conversation history, Maker." if not related else (
                f"I deleted {len(notes)} matching saved memories and cleared our conversation history, Maker."
            )
        return "The saved notes changed before I could delete them, Maker. Please try again."


def format_notes(notes):
    return " ".join(f"Memory {note['id']}. {note['content']}." for note in notes)
