"""Exercise local draft generation, validation and exclusive Office export."""

import io
import json
import tempfile
import unittest
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import Mock

from docx import Document
from pptx import Presentation

from orbit.artifacts import (
    Artifact, ArtifactError, ArtifactRequest, Slide, detect_artifact_kind,
    generate_artifact, load_source, save_artifact,
)
from orbit.config import Settings
from orbit.models import Cancellation


class ArtifactTests(unittest.TestCase):
    def test_routes_explicit_file_requests(self):
        cases = {
            "Could you make me a 4-slide PowerPoint about space?": "presentation",
            "Create a file named Orbit.docx": "word",
            "Write me a plain text file about orbiting": "document",
            "Generate a Markdown document": "markdown",
            "Create a set of flashcards": "flashcards",
            "Make some revision notes": "study_guide",
            "Prepare a practice quiz": "quiz",
            "How do I create a PowerPoint?": None,
            "Write a poem about a presentation": None,
        }
        for request, kind in cases.items():
            with self.subTest(request=request):
                self.assertEqual(detect_artifact_kind(request), kind)

    def test_selected_source_and_structured_response(self):
        raw_data = {"title": "Launching", "body": "Move ahead"}
        client = self.client(raw_data)
        request = ArtifactRequest("study_guide", "Use my notes", 'Use "quotes" in examples')
        artifact = generate_artifact(client, request, Cancellation())
        self.assertEqual(artifact.preview, "# Launching\n\nMove ahead\n")
        endpoint, payload = client.sent
        self.assertEqual(endpoint, "/api/chat")
        self.assertIsInstance(payload["format"], dict)
        self.assertIn(json.dumps(request.source), payload["messages"][-1]["content"])

    def test_rejects_invalid_deck_and_truncated_model_response(self):
        data = {"title": "Deck", "subtitle": "Introduction", "slides": [{"title": "Long", "points": [1]}]}
        with self.assertRaisesRegex(ArtifactError, "invalid draft"):
            generate_artifact(self.client(data), ArtifactRequest("presentation", "Build it"), Cancellation())
        client = self.client({"title": "Deck", "body": "Only part"}, "length")
        with self.assertRaisesRegex(ArtifactError, "ran out of space"):
            generate_artifact(client, ArtifactRequest("document", "Write it"), Cancellation())

    def test_quiz_preview_always_has_a_separate_answer_key(self):
        client = self.client({
            "title": "Moon quiz", "items": [{"question": "What orbits Earth?", "answer": "The Moon."}],
        })
        quiz = generate_artifact(client, ArtifactRequest("quiz", "Create a quiz with one question"), Cancellation())
        self.assertIn("## Questions\n\n1. What orbits Earth?", quiz.preview)
        self.assertIn("## Answer key\n\n1. The Moon.", quiz.preview)

    def test_word_and_powerpoint_export_reopen_and_never_overwrite(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            deck = Artifact("presentation", "Robotics < & >",
                            subtitle="An introduction", slides=(Slide("Sensors", ("Depth & movement",)),))
            deck_file = save_artifact(deck, directory / deck.filename)
            result = Presentation(deck_file)
            self.assertEqual(len(result.slides), 2)
            self.assertEqual(result.core_properties.title, deck.title)
            self.assertIn("Depth & movement", [shape.text for shape in result.slides[1].shapes if shape.has_text_frame])
            original = deck_file.read_bytes()
            with self.assertRaises(FileExistsError):
                save_artifact(deck, deck_file)
            self.assertEqual(deck_file.read_bytes(), original)
            with self.assertRaises(ArtifactError):
                save_artifact(deck, directory / "Wrong.exe")
            document = Artifact("word", "A report", "## Progress\n\nWe finished.\n\n- Next step")
            word_file = save_artifact(document, directory / document.filename)
            result = Document(word_file)
            self.assertEqual([p.text for p in result.paragraphs], ["A report", "Progress", "We finished.", "Next step"])
            self.assertEqual(list(directory.glob(".orbit-*")), [])

    def test_loads_only_supported_bounded_text_sources(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "source.md"
            path.write_text("Révision ✓", encoding="utf-8-sig")
            self.assertEqual(load_source(path), "Révision ✓")
            path.write_bytes(b"binary\x00data")
            with self.assertRaises(ArtifactError):
                load_source(path)
            path.write_text("X" * 6001, encoding="utf-8")
            with self.assertRaises(ArtifactError):
                load_source(path)

    @staticmethod
    def client(content, reason="stop"):
        client = Mock(settings=Settings())

        @contextmanager
        def request(endpoint, *, payload, cancel):
            client.sent = (endpoint, payload)
            yield io.BytesIO(json.dumps({
                "done": True, "done_reason": reason, "message": {"content": json.dumps(content)},
            }).encode())

        client.request.side_effect = request
        return client
