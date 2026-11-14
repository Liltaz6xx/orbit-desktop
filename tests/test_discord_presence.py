"""Discord IPC tests without using a Discord account or publishing activity."""

import json
import unittest
from unittest.mock import patch

from PySide6.QtCore import QCoreApplication

from orbit.discord_presence import DiscordPresence, CLOSE, FRAME, HANDSHAKE, HEADER, MAX_PAYLOAD, PING, PONG
from orbit.discord_presence import encode_frame, valid_application_id


class DiscordTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QCoreApplication.instance()
        if cls.app is None:
            from PySide6.QtWidgets import QApplication

            cls.app = QApplication([])

    def setUp(self):
        self.client = DiscordPresence()
        self.addCleanup(self.client.stop)

    def test_frames_and_application_ids(self):
        payload = {"client_id": "1571196055159046527", "v": 1}
        encoded = encode_frame(HANDSHAKE, payload)
        self.assertEqual(HEADER.unpack_from(encoded), (HANDSHAKE, len(encoded) - HEADER.size))
        self.assertEqual(json.loads(encoded[HEADER.size:]), payload)
        self.assertTrue(valid_application_id(payload["client_id"]))
        for invalid in ("", "abc", "0" * 18, "99999999999999999999"):
            self.assertFalse(valid_application_id(invalid))

    def test_activity_and_clear_contain_no_conversation_data(self):
        with patch.object(self.client, "send") as send:
            self.client.handle_frame({"evt": "READY"})
            opcode, payload = send.call_args.args
            self.assertEqual(opcode, FRAME)
            self.assertEqual(payload["cmd"], "SET_ACTIVITY")
            self.assertEqual(payload["args"]["activity"], {"type": 0})
            self.client.handle_frame({"cmd": "SET_ACTIVITY", "nonce": "wrong"})
            self.assertFalse(self.client.published)
            self.client.handle_frame({"cmd": "SET_ACTIVITY", "nonce": payload["nonce"]})
            self.assertTrue(self.client.published)
            self.client.send_activity(None)
            self.assertIsNone(send.call_args.args[1]["args"]["activity"])

    def test_ping_partial_reads_and_malformed_input(self):
        self.client.application_id = "1571196055159046527"
        data = encode_frame(PING, {"test": True})
        with patch.object(self.client.socket, "readAll", side_effect=[data[:4], data[4:]]), \
                patch.object(self.client, "send") as send:
            self.client.receive()
            send.assert_not_called()
            self.client.receive()
            send.assert_called_once_with(PONG, {"test": True})
        with patch.object(self.client.socket, "readAll", return_value=HEADER.pack(CLOSE, MAX_PAYLOAD + 1)):
            self.client.receive()
        self.assertIn("declined", self.client.status)
        self.assertTrue(self.client.retry.isActive())
