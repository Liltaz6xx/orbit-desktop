"""Incremental speech segmentation and the Kokoro inference engine."""

import inspect
import logging
import os
import re
from time import perf_counter

from .config import VOICE_LANGUAGE, VOICE_NAME, VOICE_SPEED, voice_files

log = logging.getLogger(__name__)
SENTENCE = re.compile(r"""[.!?]+['"”)]*(?=\s)""")
CLAUSE = re.compile(r"[,;:](?=\s)")
ABBREVIATION = re.compile(r"(?:\b(?:Mr|Mrs|Ms|Dr|Prof|St|vs|etc)|\b[A-Za-z](?:\.[A-Za-z])*)\.$", re.I)


def prepare_for_speech(text):
    text = re.sub(r"(?s)\x60\x60\x60.*?(?:\x60\x60\x60|$)", "I have some technical details for that.", text)
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
    text = re.sub(r"[*_\x60#]", "", text)
    text = re.sub(r"(?m)^\s*[-•]\s+", "", text)
    text = "".join(c for c in text if c.isprintable() or c.isspace())
    return re.sub(r"\s+", " ", text).strip()


class SpeechSegmenter:
    def __init__(self):
        self.buffer = ""
        self.first_chunk = True

    def feed(self, text):
        self.buffer += text
        segments = []
        while self.buffer:
            minimum, maximum = (16, 56) if self.first_chunk else (40, 112)
            fence = self.buffer.find("\x60\x60\x60")
            if fence >= 0:
                if fence:
                    segment = prepare_for_speech(self.buffer[:fence])
                    if segment:
                        segments.append(segment)
                        self.first_chunk = False
                end = self.buffer.find("\x60\x60\x60", fence + 3)
                self.buffer = self.buffer[end + 3:] if end >= 0 else self.buffer[fence:]
                if end < 0:
                    break
                segments.append("I have some technical details for that.")
                self.first_chunk = False
                continue
            sample = self.buffer[:maximum + 1]
            boundary = next(
                (match.end() for match in SENTENCE.finditer(sample)
                 if match.end() >= minimum and not ABBREVIATION.search(sample[:match.end()])),
                0,
            )
            if not boundary and len(self.buffer) > maximum:
                boundary = max((m.end() for m in CLAUSE.finditer(sample) if m.end() >= minimum), default=0)
                boundary = boundary or sample.rfind(" ")
                if boundary < minimum:
                    # A single long word or URL can exceed the target chunk size.
                    boundary = self.buffer.find(" ", maximum)
                    if boundary == -1:
                        break
            if not boundary:
                break
            segment = prepare_for_speech(self.buffer[:boundary])
            self.buffer = self.buffer[boundary:].lstrip()
            if segment:
                segments.append(segment)
                self.first_chunk = False
        return segments

    def flush(self):
        remaining = prepare_for_speech(self.buffer)
        self.buffer = ""
        return [remaining] if remaining else []


def clean_audio(samples, rate, pause_seconds):
    import numpy as np

    audio = np.array(samples, dtype=np.float32, copy=True).reshape(-1)
    if not audio.size or not np.isfinite(audio).all() or not np.any(audio):
        raise ValueError("Kokoro returned empty or invalid audio.")
    # Only trim near-digital silence outside a generous margin for quiet phonemes.
    active = np.flatnonzero(np.abs(audio) > 0.00025)
    if active.size:
        margin = int(rate * 0.055)
        audio = audio[max(0, active[0] - margin):active[-1] + margin + 1]
    fade = min(int(rate * 0.004), len(audio) // 4)
    if fade > 1:
        audio[:fade] *= np.linspace(0, 1, fade, dtype=np.float32)
        audio[-fade:] *= np.linspace(1, 0, fade, dtype=np.float32)
    return np.pad(audio, (0, int(rate * pause_seconds)))


class VoiceUnavailable(RuntimeError):
    pass


class OrbitVoice:
    """Owned by the synthesis worker for the lifetime of the application."""

    def __init__(self):
        self.engine = None
        self.parameters = set()
        self.voice_name = VOICE_NAME
        self.language = VOICE_LANGUAGE

    def load(self):
        if self.engine is not None:
            return
        model, library = voice_files()
        missing = [path.name for path in (model, library) if not path.is_file()]
        if missing:
            raise VoiceUnavailable("Missing voice assets: " + ", ".join(missing))
        try:
            import onnxruntime as ort
            from kokoro_onnx import Kokoro
        except ImportError as exc:
            raise VoiceUnavailable("Kokoro needs " + (exc.name or "kokoro-onnx") + ". Run Setup_ORBIT.bat.") from None
        started = perf_counter()
        # Kokoro debug output can include phonemes derived from private replies.
        logging.getLogger("kokoro_onnx").setLevel(logging.WARNING)
        cpu_only = set(ort.get_available_providers()) <= {"AzureExecutionProvider", "CPUExecutionProvider"}
        if cpu_only and not os.getenv("ONNX_PROVIDER"):
            options = ort.SessionOptions()
            options.intra_op_num_threads = min(8, os.cpu_count() or 1)
            # Let Ollama use these cores while speech synthesis is idle.
            options.add_session_config_entry("session.intra_op.allow_spinning", "0")
            session = ort.InferenceSession(str(model), options, providers=["CPUExecutionProvider"])
            self.engine = Kokoro.from_session(session, str(library))
        else:
            self.engine = Kokoro(str(model), str(library))
        self.parameters = set(inspect.signature(self.engine.create).parameters)
        log.info("event=kokoro_loaded model=%s elapsed_ms=%.0f", model.name, (perf_counter() - started) * 1000)

    def synthesize(self, text):
        self.load()
        arguments = {"voice": self.voice_name, "speed": VOICE_SPEED, "lang": self.language}
        for name, value in {"trim": False, "sentence_pause": 0.16, "clause_pause": 0.07}.items():
            if name in self.parameters:
                arguments[name] = value
        started = perf_counter()
        samples, rate = self.engine.create(text, **arguments)
        pause = 0.055 if text.rstrip("'”\"").endswith((".", "!", "?")) else 0.02
        audio = clean_audio(samples, rate, pause)
        elapsed = perf_counter() - started
        duration = len(audio) / rate
        log.info("event=kokoro_synthesis elapsed_ms=%.0f audio_ms=%.0f rtf=%.3f chars=%d",
                 elapsed * 1000, duration * 1000, elapsed / duration, len(text))
        return audio, rate

    def preload(self):
        self.synthesize("Ready.")
