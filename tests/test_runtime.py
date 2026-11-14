"""Configuration, import, streaming and speech regression checks."""

import importlib
import io
import json
import os
import pkgutil
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

import orbit
from orbit import config
from orbit.ai import OllamaClient, OllamaError, parse_stream
from orbit.config import CONFIG_PATH, DATABASE_PATH, PROFILE_DIR, ROOT, ConfigError, Settings, load_settings
from orbit.models import Cancellation
from orbit.voice import SpeechSegmenter, clean_audio


def frame(content, done=False):
    return (json.dumps({"message": {"content": content}, "done": done}) + "\n").encode()


class RuntimeTests(unittest.TestCase):
    def test_every_module_imports(self):
        for module in pkgutil.walk_packages(orbit.__path__, "orbit."):
            with self.subTest(module=module.name):
                importlib.import_module(module.name)
        for module in ("main", "scripts.check_environment"):
            importlib.import_module(module)

    def test_config_file_defaults_and_env_override(self):
        with tempfile.TemporaryDirectory() as temp, patch.dict(os.environ, clear=True):
            path = Path(temp) / "orbit.toml"
            self.assertEqual(load_settings(path).model, "qwen2.5:1.5b")
            path.write_text('[ollama]\nmodel="custom:small"\nmax_tokens=64\n', encoding="utf-8")
            self.assertEqual(load_settings(path).max_tokens, 64)
            with patch.dict(os.environ, ORBIT_OLLAMA_MODEL="example:latest"):
                self.assertEqual(load_settings(path).model, "example:latest")
            path.write_text("[ollama\n", encoding="utf-8")
            with self.assertRaises(ConfigError):
                load_settings(path)

    def test_profile_is_separate_from_release_directory(self):
        self.assertEqual(DATABASE_PATH.parent, PROFILE_DIR)
        self.assertEqual(CONFIG_PATH.parent, PROFILE_DIR)
        self.assertFalse(DATABASE_PATH.is_relative_to(ROOT))

    def test_voice_model_prefers_new_export_and_supports_old_cache(self):
        with tempfile.TemporaryDirectory() as temp:
            profile = Path(temp) / "profile"
            voice = profile / "voice"
            assets = Path(temp) / "assets"
            voice.mkdir(parents=True)
            assets.mkdir()
            legacy = voice / config.LEGACY_VOICE_MODEL
            library = voice / config.VOICE_LIBRARY
            fast = assets / config.VOICE_MODEL
            with patch.multiple(config, PROFILE_DIR=profile, ASSETS=assets):
                legacy.touch()
                library.touch()
                self.assertEqual(config.voice_files(), (legacy, library))
                fast.touch()
                self.assertEqual(config.voice_files(), (legacy, library))
                local_library = assets / config.VOICE_LIBRARY
                local_library.touch()
                self.assertEqual(config.voice_files(), (fast, local_library))
                installed = voice / config.VOICE_MODEL
                installed.touch()
                self.assertEqual(config.voice_files(), (installed, library))

    def test_config_rejects_cloud_and_invalid_types(self):
        for kwargs in (
            {"ollama_url": "https://ollama.com"}, {"ollama_url": "http://127.0.0.1@other.example"},
            {"model": "qwen:cloud"}, {"model": "qwen:3b-cloud"}, {"model": "bad; name"},
            {"max_tokens": True}, {"timeout": float("nan")},
        ):
            with self.subTest(kwargs=kwargs), self.assertRaises(ConfigError):
                Settings(**kwargs)

    def test_stream_parse_and_segment(self):
        chunks = []
        raw = frame("Here is the first sentence. ") + frame("Here is the second.") + frame("", True)
        self.assertEqual(parse_stream(io.BytesIO(raw), chunks.append, Cancellation()),
                         "Here is the first sentence. Here is the second.")
        self.assertEqual(chunks, ["Here is the first sentence.", "Here is the second."])

    def test_invalid_streams(self):
        for raw in (b'[]\n', b'{invalid\n', b'{"done":true,"message":[]}\n',
                    b'{"done":"false"}\n', b'{"error":"private detail"}\n', frame("", True), frame("Truncated")):
            with self.subTest(raw=raw), self.assertRaises(OllamaError):
                parse_stream(io.BytesIO(raw), lambda _: None, Cancellation())

    def test_incremental_segmentation_avoids_decimal_and_code(self):
        speech = SpeechSegmenter()
        self.assertEqual(speech.feed("I measured the value as 3."), [])
        self.assertEqual(speech.feed("14 units. "), ["I measured the value as 3.14 units."])
        self.assertEqual(speech.feed("\x60\x60\x60python\nprivate_code"), [])
        self.assertEqual(speech.feed("\n\x60\x60\x60 A short follow-up."), ["I have some technical details for that."])
        self.assertEqual(speech.flush(), ["A short follow-up."])

    def test_long_opening_sentence_starts_speech_before_sentence_end(self):
        speech = SpeechSegmenter()
        opening = "Small objects such as meteoroids hit the Moon and leave "
        chunks = speech.feed(opening + "craters")
        self.assertEqual(len(chunks), 1)
        self.assertLessEqual(len(chunks[0]), 56)
        rest = speech.feed(" of different sizes.") + speech.flush()
        self.assertEqual(" ".join(chunks + rest), opening + "craters of different sizes.")

    def test_voice_emits_the_next_complete_sentence_while_reply_is_streaming(self):
        speech = SpeechSegmenter()
        self.assertEqual(speech.feed("Consider the Moon, Maker. "), ["Consider the Moon, Maker."])
        self.assertEqual(
            speech.feed("Most craters formed when rocks hit its surface. There"),
            ["Most craters formed when rocks hit its surface."],
        )

    def test_clean_audio_preserves_quiet_tail_and_fades(self):
        import numpy as np

        audio = np.zeros(4_000, dtype=np.float32)
        audio[1000:2000] = 0.5
        audio[2000:2500] = 0.002
        cleaned = clean_audio(audio, 10_000, 0.02)
        self.assertEqual(cleaned[0], 0)
        self.assertEqual(cleaned[-1], 0)
        self.assertGreaterEqual(np.count_nonzero(cleaned == 0.002), 500)
        self.assertGreaterEqual(len(cleaned), 2_600)

    def test_cancel_drops_later_segments(self):
        stop = Cancellation()
        chunks = []

        def receive(text):
            chunks.append(text)
            stop.set()

        raw = frame("The first sentence is long enough. ") + frame("The second should never play.", True)
        self.assertEqual(parse_stream(io.BytesIO(raw), receive, stop), "")
        self.assertEqual(chunks, ["The first sentence is long enough."])

    def test_cancellation_and_completed_archive_are_exclusive(self):
        cancelled = Cancellation()
        self.assertTrue(cancelled.set())
        self.assertFalse(cancelled.complete())
        completed = Cancellation()
        self.assertTrue(completed.complete())
        self.assertFalse(completed.set())
        self.assertFalse(completed.is_set())


class OllamaTransportTests(unittest.TestCase):
    def setUp(self):
        self.arrived = threading.Event()
        self.release = threading.Event()
        self.chat_requests = 0
        self.tags = [{"name": "qwen2.5:3b"}]
        self.ports = []
        case = self

        class Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def handle(self):
                try:
                    super().handle()
                except ConnectionError:
                    pass

            def log_message(self, *_args):
                pass

            def do_GET(self):
                case.ports.append(self.client_address[1])
                data = json.dumps({"models": case.tags}).encode()
                self.send_response(200)
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def do_POST(self):
                self.rfile.read(int(self.headers["Content-Length"]))
                case.ports.append(self.client_address[1])
                case.chat_requests += 1
                data = frame("Here is a complete reply.", True)
                if case.chat_requests == 1 and self.path == "/api/chat":
                    case.arrived.set()
                    case.release.wait(4)
                try:
                    self.send_response(200)
                    self.send_header("Content-Length", str(len(data)))
                    self.end_headers()
                    self.wfile.write(data)
                except OSError:
                    pass

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.client = OllamaClient(Settings(
            model="qwen2.5:3b", ollama_url=f"http://127.0.0.1:{self.server.server_port}",
        ))
        self.addCleanup(self.stop_server)

    def stop_server(self):
        self.release.set()
        self.client.close()
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(2)

    def test_cancel_interrupts_blocked_read_and_new_request_uses_new_connection(self):
        stop = Cancellation()
        result = []

        def generate():
            try:
                result.append(self.client.stream([], result.append, stop))
            except OllamaError:
                if not stop.is_set():
                    result.append("unexpected error")

        generation = threading.Thread(target=generate, daemon=True)
        generation.start()
        self.assertTrue(self.arrived.wait(3))
        stop.set()
        generation.join(1)
        self.assertFalse(generation.is_alive(), "socket read should be interrupted")
        self.assertEqual(result, [])
        self.assertEqual(self.client.stream([], lambda _: None, Cancellation()), "Here is a complete reply.")
        self.assertEqual(self.ports[0], self.ports[1])
        self.assertEqual(self.ports[2], self.ports[3])
        self.assertNotEqual(self.ports[0], self.ports[2])

    def test_missing_and_remote_models_are_rejected_before_chat(self):
        for tags in ([], [{"name": "qwen2.5:3b", "remote_host": "https://example.com"}]):
            self.tags = tags
            with self.assertRaises(OllamaError):
                self.client.stream([], lambda _: None, Cancellation())
        self.assertEqual(self.chat_requests, 0)
