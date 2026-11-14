"""Discord activity via the local desktop client's named pipe."""

import json
import logging
import os
import re
import struct
from uuid import uuid4

from PySide6.QtCore import QObject, QSignalBlocker, QTimer, Signal
from PySide6.QtNetwork import QLocalSocket

log = logging.getLogger(__name__)
APPLICATION_ID = "1571196055159046527"
HEADER = struct.Struct("<II")
HANDSHAKE, FRAME, CLOSE, PING, PONG = range(5)
MAX_PAYLOAD = 64 * 1024


def valid_application_id(value: str) -> bool:
    return bool(re.fullmatch(r"[1-9][0-9]{16,19}", value) and int(value) < 2**64)


def encode_frame(opcode, payload):
    body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    return HEADER.pack(opcode, len(body)) + body


class DiscordPresence(QObject):
    status_changed = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.application_id = ""
        self.buffer = bytearray()
        self.endpoint = 0
        self.nonce = None
        self.published = False
        self.status = "Sharing is off"
        self.socket = QLocalSocket(self)
        self.socket.setReadBufferSize(2 * MAX_PAYLOAD)
        self.socket.connected.connect(self.handshake)
        self.socket.readyRead.connect(self.receive)
        self.socket.errorOccurred.connect(self.connection_error)
        self.socket.disconnected.connect(self.disconnected)

        self.retry = QTimer(self, singleShot=True)
        self.retry.timeout.connect(self.connect_next)
        self.deadline = QTimer(self, interval=3000, singleShot=True)
        self.deadline.timeout.connect(self.disconnected)

    def start(self, application_id):
        if not valid_application_id(application_id):
            raise ValueError("Enter a valid numeric Discord Application ID.")
        self.stop()
        self.application_id = application_id
        self.endpoint = 0
        self.set_status("Waiting for the Discord desktop app")
        self.retry.start(0)

    def stop(self):
        self.retry.stop()
        self.deadline.stop()
        self.application_id = ""
        if self.nonce and self.socket.state() == QLocalSocket.LocalSocketState.ConnectedState:
            self.send_activity(None)
            self.socket.flush()
            self.socket.disconnectFromServer()
        else:
            self.reset_socket()
        self.published = False
        self.set_status("Sharing is off")

    def set_status(self, status):
        self.status = status
        self.status_changed.emit(status)

    def reset_socket(self):
        with QSignalBlocker(self.socket):
            self.socket.abort()
        self.buffer.clear()
        self.nonce = None
        self.published = False
        self.deadline.stop()

    def connect_next(self):
        if not self.application_id:
            return
        self.reset_socket()
        self.deadline.start()
        self.socket.connectToServer(rf"\\.\pipe\discord-ipc-{self.endpoint}")

    def connection_error(self, error):
        if not self.application_id or self.retry.isActive():
            return
        if error in (QLocalSocket.LocalSocketError.ServerNotFoundError,
                     QLocalSocket.LocalSocketError.ConnectionRefusedError):
            self.deadline.stop()
            self.endpoint += 1
            if self.endpoint < 10:
                self.retry.start(0)
                return
        self.disconnected()

    def disconnected(self):
        self.deadline.stop()
        if self.application_id and not self.retry.isActive():
            self.reset_socket()
            self.endpoint = 0
            self.set_status("Waiting for the Discord desktop app")
            self.retry.start(15_000)

    def handshake(self):
        self.send(HANDSHAKE, {"v": 1, "client_id": self.application_id})

    def send(self, opcode, payload):
        self.socket.write(encode_frame(opcode, payload))

    def send_activity(self, activity):
        self.nonce = uuid4().hex
        self.send(FRAME, {"cmd": "SET_ACTIVITY", "nonce": self.nonce,
                          "args": {"pid": os.getpid(), "activity": activity}})

    def receive(self):
        self.buffer.extend(bytes(self.socket.readAll()))
        while len(self.buffer) >= HEADER.size and self.application_id:
            opcode, size = HEADER.unpack_from(self.buffer)
            if size > MAX_PAYLOAD:
                self.invalid_response()
                return
            end = HEADER.size + size
            if len(self.buffer) < end:
                return
            body = bytes(self.buffer[HEADER.size:end])
            del self.buffer[:end]
            try:
                payload = json.loads(body) if body else {}
            except (ValueError, RecursionError):
                self.invalid_response()
                return
            if not isinstance(payload, dict):
                self.invalid_response()
                return
            if opcode == PING:
                self.send(PONG, payload)
            elif opcode == CLOSE or (opcode == FRAME and payload.get("evt") == "ERROR"):
                self.invalid_response()
                return
            elif opcode == FRAME:
                self.handle_frame(payload)

    def handle_frame(self, payload):
        if payload.get("evt") == "READY" and self.nonce is None:
            self.deadline.start()
            self.send_activity({"type": 0})
        elif (self.nonce and payload.get("nonce") == self.nonce
              and payload.get("cmd") == "SET_ACTIVITY"):
            self.deadline.stop()
            self.published = True
            self.set_status("ORBIT activity sent to Discord")
            log.info("event=discord_presence_active")

    def invalid_response(self):
        self.reset_socket()
        self.endpoint = 0
        self.set_status("Discord declined the activity")
        self.retry.start(30_000)
