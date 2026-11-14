"""Installer provisioning decisions with an isolated Ollama API."""

import io
import unittest
from contextlib import contextmanager
from unittest.mock import Mock, patch

from orbit.ai import OllamaClient, OllamaError, OllamaModelMissing
from orbit.config import Settings
from orbit.ollama_setup import NOT_INSTALLED, provision


class ProvisionTests(unittest.TestCase):
    def setUp(self):
        self.client = Mock(settings=Settings())
        self.client.read_json.return_value = {"version": "0.40.16"}

    @patch("orbit.ollama_setup.find_ollama")
    def test_reuses_running_server_and_model(self, find):
        self.assertEqual(provision(self.client), 0)
        self.client.check_model.assert_called_once()
        self.client.pull_model.assert_not_called()
        find.assert_not_called()

    @patch("orbit.ollama_setup.find_ollama", return_value=None)
    def test_missing_local_ollama_requests_installer(self, find):
        self.client.read_json.side_effect = OllamaError()
        self.assertEqual(provision(self.client), NOT_INSTALLED)
        find.assert_called_once()
        self.client.pull_model.assert_not_called()

    @patch("orbit.ollama_setup.find_ollama")
    def test_custom_endpoint_does_not_start_or_install_ollama(self, find):
        self.client.settings = Settings(ollama_url="http://127.0.0.1:11435")
        self.client.read_json.side_effect = OllamaError()
        self.assertNotEqual(provision(self.client), 0)
        find.assert_not_called()

    def test_missing_default_model_is_pulled_and_rechecked(self):
        self.client.check_model.side_effect = [OllamaModelMissing(), None]
        self.assertEqual(provision(self.client), 0)
        self.client.pull_model.assert_called_once()
        self.assertEqual(self.client.check_model.call_count, 2)

    def test_custom_model_is_preserved(self):
        self.client.settings = Settings(model="qwen2.5:3b")
        self.client.check_model.side_effect = OllamaModelMissing()
        self.assertEqual(provision(self.client), 0)
        self.client.pull_model.assert_not_called()

    def test_pull_requires_success_frame(self):
        client = OllamaClient(Settings())
        for body in (b'{"status":"pulling","total":100,"completed":75}\n',
                     b'{"error":"disk full"}\n'):
            with self.subTest(body=body):
                @contextmanager
                def response(*args, **kwargs):
                    yield io.BytesIO(body)

                with patch.object(client, "request", response), self.assertRaises(OllamaError):
                    client.pull_model(Mock())
