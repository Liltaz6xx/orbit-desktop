"""Per-turn state and cancellation shared by the background workers."""

import queue
import threading
from dataclasses import dataclass, field
from time import perf_counter
from typing import TYPE_CHECKING

from PySide6.QtCore import QObject, Signal

from .preferences import Preferences

if TYPE_CHECKING:
    from .artifacts import Artifact, ArtifactRequest


class OrbitEvents(QObject):
    subsystem = Signal(str, str)
    approval = Signal(int, object)
    generated = Signal(int, str, str, bool)
    speech_started = Signal(int, str)
    caption = Signal(int, str)
    speech_finished = Signal(int, str, str)
    saved = Signal(int, str)


class Cancellation:
    def __init__(self):
        self.event = threading.Event()
        self.lock = threading.Lock()
        self.interrupt = None
        self.completed = False

    def is_set(self):
        return self.event.is_set()

    def bind(self, interrupt):
        with self.lock:
            self.interrupt = interrupt
            if interrupt is not None and self.event.is_set():
                interrupt()

    def set(self):
        with self.lock:
            if self.completed:
                return False
            self.event.set()
            if self.interrupt is not None:
                self.interrupt()
            return True

    def complete(self):
        """Resolve the race between cancellation and archiving a finished turn."""
        with self.lock:
            if self.event.is_set():
                return False
            self.completed = True
            return True


class AudioMeter:
    # A single playback producer publishes a level for the active request.
    sample = (0, 0.0)
    turn_id = 0

    @property
    def level(self):
        turn_id, level = self.sample
        return level if turn_id == self.turn_id else 0.0

    def update(self, turn_id, level):
        self.sample = (turn_id, level)


def put_until(queue_, item, *stops):
    while not any(stop.is_set() for stop in stops):
        try:
            queue_.put(item, timeout=0.04)
            return True
        except queue.Full:
            continue
    return False


@dataclass
class OrbitTurn:
    id: int
    message: str
    stop: Cancellation = field(default_factory=Cancellation)
    text: queue.Queue = field(default_factory=lambda: queue.Queue(maxsize=8))
    audio: queue.Queue = field(default_factory=lambda: queue.Queue(maxsize=4))
    audio_failed: threading.Event = field(default_factory=threading.Event)
    started_at: float = field(default_factory=perf_counter)
    generated: bool = False
    played: bool = False
    answer: str = ""
    notice: str = ""
    persist: bool = False
    context_revision: int | None = None
    preferences: Preferences = field(default_factory=Preferences)
    from_microphone: bool = False
    artifact_request: "ArtifactRequest | None" = None
    artifact: "Artifact | None" = None

    def speak(self, phrase):
        return put_until(self.text, phrase, self.stop, self.audio_failed)


@dataclass(frozen=True)
class Approval:
    title: str
    description: str
    kind: str
    value: object
