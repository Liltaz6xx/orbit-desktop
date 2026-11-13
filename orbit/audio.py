"""Buffered PortAudio playback and cancellable Windows speech fallback."""

import base64
import logging
import os
import queue
import subprocess
import threading
from contextlib import suppress
from dataclasses import dataclass
from time import perf_counter

from .config import AUDIO_LEVEL_GAIN

log = logging.getLogger(__name__)


@dataclass
class AudioChunk:
    text: str
    samples: object = None
    rate: int = 0


class AudioDeviceError(RuntimeError):
    pass


def play_stream(first, turn, meter, started):
    """Play same-rate Kokoro chunks in one stream. Return any fallback item."""
    try:
        import numpy as np
        import sounddevice as sd
    except ImportError as exc:
        raise AudioDeviceError("Install " + (exc.name or "sounddevice") + " with Setup_ORBIT.bat.") from None
    ended = threading.Event()
    chunk, next_item = first, None
    position = 0
    audio_frames = silence_frames = underflows = 0
    clean_end = False
    rate = first.rate

    def callback(out, frames, _time, status):
        nonlocal chunk, position, next_item, audio_frames, silence_frames, underflows, clean_end
        out.fill(0)
        if turn.stop.is_set():
            raise sd.CallbackAbort
        underflows += bool(status.output_underflow)
        filled = 0
        while filled < frames:
            if chunk is None:
                try:
                    chunk = turn.audio.get_nowait()
                except queue.Empty:
                    silence_frames += frames - filled
                    break
                if chunk is None or chunk.rate != rate:
                    next_item = chunk
                    clean_end = True
                    break
                position = 0
            count = min(frames - filled, len(chunk.samples) - position)
            out[filled:filled + count, 0] = chunk.samples[position:position + count]
            position += count
            filled += count
            if position == len(chunk.samples):
                chunk = None
        audio_frames += filled
        meter.update(turn.id, min(1.0, float(np.sqrt(np.mean(np.square(out)))) * AUDIO_LEVEL_GAIN))
        if clean_end:
            raise sd.CallbackStop

    opened = perf_counter()
    try:
        stream = sd.OutputStream(samplerate=rate, channels=1, dtype="float32", latency="low",
                                 callback=callback, finished_callback=ended.set)
    except sd.PortAudioError:
        raise AudioDeviceError("Kokoro could not open the default audio device.") from None
    try:
        if turn.stop.is_set():
            return None
        try:
            stream.start()
        except sd.PortAudioError:
            raise AudioDeviceError("Kokoro could not start audio playback.") from None
        started("Kokoro")
        log.info("event=audio_started turn=%d first_audio_ms=%.0f device_latency_ms=%.0f",
                 turn.id, (perf_counter() - turn.started_at) * 1000, stream.latency * 1000)
        while not ended.wait(0.02):
            if turn.stop.is_set():
                stream.abort()
                break
            if not stream.active:
                break
        if not clean_end and not turn.stop.is_set():
            raise RuntimeError("The audio stream stopped unexpectedly.")
        return next_item
    finally:
        with suppress(sd.PortAudioError):
            stream.close()
        meter.update(turn.id, 0.0)
        log.info("event=audio_closed turn=%d elapsed_ms=%.0f speech_ms=%.0f gap_ms=%.0f underflows=%d",
                 turn.id, (perf_counter() - opened) * 1000, audio_frames * 1000 / rate,
                 silence_frames * 1000 / rate, underflows)


WINDOWS_SPEECH_SCRIPT = r"""
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Speech
$speaker = New-Object System.Speech.Synthesis.SpeechSynthesizer
try {
    $speaker.SetOutputToDefaultAudioDevice()
    $speaker.Rate = -1
    $male = $speaker.GetInstalledVoices() |
        Where-Object { $_.Enabled -and $_.VoiceInfo.Gender.ToString() -eq 'Male' } |
        Sort-Object { $_.VoiceInfo.Culture.Name -ne 'en-GB' } | Select-Object -First 1
    if ($null -ne $male) { $speaker.SelectVoice($male.VoiceInfo.Name) }
    $message = [Text.Encoding]::UTF8.GetString([Convert]::FromBase64String([Console]::In.ReadToEnd()))
    $speaker.Speak($message)
} finally { $speaker.Dispose() }
"""


def windows_speak(text, stop):
    if os.name != "nt":
        raise RuntimeError("Windows speech is unavailable on this platform.")
    if stop.is_set():
        return
    system_root = os.environ.get("SystemRoot", r"C:\Windows")
    powershell = os.path.join(system_root, "System32", "WindowsPowerShell", "v1.0", "powershell.exe")
    command = base64.b64encode(WINDOWS_SPEECH_SCRIPT.encode("utf-16le")).decode("ascii")
    started = perf_counter()
    with subprocess.Popen(
        [powershell, "-NoProfile", "-NonInteractive", "-EncodedCommand", command],
        stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        creationflags=subprocess.CREATE_NO_WINDOW,
    ) as process:
        payload = base64.b64encode(text.encode("utf-8"))
        try:
            while not stop.is_set():
                try:
                    process.communicate(payload, timeout=0.04)
                    if process.returncode:
                        raise RuntimeError("Windows speech could not play on the default audio device.")
                    break
                except subprocess.TimeoutExpired:
                    payload = None
        finally:
            if process.poll() is None:
                process.kill()
                process.communicate()
    log.info("event=windows_speech elapsed_ms=%.0f", (perf_counter() - started) * 1000)
