"""A fixed set of workers for conversation, synthesis and audio playback."""

import logging
import queue
import sqlite3
import threading

from .audio import AudioChunk, AudioDeviceError, play_stream, windows_speak
from .conversation import Conversation
from .models import put_until
from .voice import OrbitVoice, VoiceUnavailable, SpeechSegmenter

log = logging.getLogger(__name__)


class OrbitWorkers:
    def __init__(self, settings, events, meter, controller, voice=None):
        self.events = events
        self.meter = meter
        self.voice = voice if voice is not None else OrbitVoice()
        self.conversation = Conversation(settings, controller, events, self.request_approval)
        self.changed = threading.Condition()
        self.current = None
        self.closed = False
        self.approval = None
        self.completed_playback = 0
        self.playback_done = threading.Event()
        self.threads = [
            threading.Thread(name="ORBIT conversation", target=self.run_conversation, daemon=True),
            threading.Thread(name="ORBIT synthesis", target=self.run_synthesis, daemon=True),
            threading.Thread(name="ORBIT playback", target=self.run_playback),
        ]

    def start(self):
        for thread in self.threads:
            thread.start()

    def submit(self, turn):
        with self.changed:
            self.current = turn
            self.changed.notify_all()

    def cancel(self, turn):
        if not turn.stop.set():
            return False
        with self.changed:
            self.changed.notify_all()
        return True

    def close(self):
        with self.changed:
            self.closed = True
            if self.current is not None:
                self.current.stop.set()
            self.changed.notify_all()
        # Playback owns the OS audio stream and fallback subprocess. The process
        # keeps running until that worker closes both, even after Qt exits.
        if self.threads[-1].is_alive():
            self.playback_done.wait(0.30)

    def turns(self):
        previous = None
        while True:
            with self.changed:
                self.changed.wait_for(lambda: self.closed or self.current is not previous)
                if self.closed:
                    return
                previous = self.current
            if not previous.stop.is_set():
                yield previous

    def request_approval(self, turn, approval):
        with self.changed:
            self.approval = (turn.id, None)
        self.events.approval.emit(turn.id, approval)
        with self.changed:
            self.changed.wait_for(lambda: self.closed or turn.stop.is_set() or self.approval[1] is not None)
            decision = self.approval[1]
            self.approval = None
            return bool(decision and not turn.stop.is_set())

    def decide(self, turn_id, decision):
        with self.changed:
            if self.approval == (turn_id, None):
                self.approval = (turn_id, decision)
                self.changed.notify_all()

    def run_conversation(self):
        conversation = self.conversation
        conversation.open_memory()
        try:
            for turn in self.turns():
                self.generate(turn)
        finally:
            conversation.ai.client.close()

    def generate(self, turn):
        try:
            answer, notice, persist = self.conversation.answer(turn)
            if answer and not persist and not notice:
                segmenter = SpeechSegmenter()
                for phrase in segmenter.feed(answer) + segmenter.flush():
                    if not turn.speak(phrase):
                        break
        except (sqlite3.Error, OSError) as exc:
            log.error("event=request_storage_error turn=%d error=%s", turn.id, type(exc).__name__)
            answer = "I couldn't access local memory, Maker. Check the database in ORBIT's diagnostics."
            notice, persist = "Local memory access failed.", False
            turn.speak(answer)
        except Exception as exc:
            log.error("event=request_failed turn=%d error=%s", turn.id, type(exc).__name__)
            answer = "I couldn't complete that request, Maker."
            notice, persist = "Request failed. Check the ORBIT log.", False
            turn.speak(answer)

        if turn.stop.is_set():
            return
        put_until(turn.text, None, turn.stop, turn.audio_failed)
        store = self.conversation.ai.store
        should_save = bool(answer and persist and turn.context_revision is not None)
        self.events.generated.emit(turn.id, answer, notice, should_save)
        if not should_save:
            return

        # Archive completed replies after playback (or after an audio failure
        # leaves the single reply available on screen).
        with self.changed:
            self.changed.wait_for(
                lambda: self.closed or turn.stop.is_set() or self.completed_playback >= turn.id
            )
        warning = ""
        try:
            if turn.stop.complete():
                saved = store.record_turn(turn.message, answer, turn.stop, revision=turn.context_revision)
                if not saved:
                    warning = "Conversation history changed while ORBIT was replying."
        except (OSError, sqlite3.Error) as exc:
            log.warning("event=conversation_save_failed turn=%d error=%s", turn.id, type(exc).__name__)
            warning = "Reply available. Conversation history could not be saved."
        self.events.saved.emit(turn.id, warning)

    def run_synthesis(self):
        use_kokoro = True
        try:
            self.voice.preload()
        except Exception as exc:
            use_kokoro = False
            self.voice_error(exc)
        for turn in self.turns():
            if isinstance(self.voice, OrbitVoice):
                self.voice.voice_name = turn.preferences.voice
                self.voice.language = turn.preferences.language
            while not turn.stop.is_set() and not turn.audio_failed.is_set():
                try:
                    phrase = turn.text.get(timeout=0.04)
                except queue.Empty:
                    continue
                if phrase is None:
                    break
                chunk = AudioChunk(phrase)
                if use_kokoro:
                    try:
                        chunk.samples, chunk.rate = self.voice.synthesize(phrase)
                    except Exception as exc:
                        use_kokoro = False
                        self.voice_error(exc)
                if not put_until(turn.audio, chunk, turn.stop, turn.audio_failed):
                    break
            put_until(turn.audio, None, turn.stop, turn.audio_failed)

    def voice_error(self, exc):
        detail = str(exc) if isinstance(exc, VoiceUnavailable) else "Kokoro initialization or synthesis failed."
        log.error("event=kokoro_unavailable error=%s detail=%s", type(exc).__name__, detail)
        self.events.subsystem.emit("voice", detail + " Using Windows speech.")

    def run_playback(self):
        try:
            for turn in self.turns():
                self.play(turn)
        finally:
            self.playback_done.set()

    def play(self, turn):
        backend, error = "", ""
        use_windows = False

        def started(name):
            nonlocal backend
            if backend != name and not turn.stop.is_set():
                backend = name
                self.events.speech_started.emit(turn.id, name)

        def caption(text):
            self.events.caption.emit(turn.id, text)

        try:
            item = None
            while not turn.stop.is_set():
                if item is None:
                    try:
                        item = turn.audio.get(timeout=0.04)
                    except queue.Empty:
                        continue
                    if item is None:
                        break
                if use_windows or item.rate == 0:
                    started("Windows voice")
                    caption(item.text)
                    windows_speak(item.text, turn.stop)
                    item = None
                else:
                    try:
                        item = play_stream(item, turn, self.meter, started, caption)
                    except AudioDeviceError as exc:
                        log.warning("event=audio_device_fallback turn=%d detail=%s", turn.id, exc)
                        self.events.subsystem.emit("audio", str(exc) + " Trying Windows speech.")
                        use_windows = True
                    else:
                        if item is None:
                            break
        except Exception as exc:
            turn.audio_failed.set()
            error = "Speech could not play. Open the reply to read it."
            log.error("event=playback_failed turn=%d error=%s", turn.id, type(exc).__name__)
        finally:
            self.meter.update(turn.id, 0.0)
            self.events.speech_finished.emit(turn.id, backend, error)
            with self.changed:
                self.completed_playback = turn.id
                self.changed.notify_all()
