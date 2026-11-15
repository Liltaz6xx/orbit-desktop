"""Input macro storage, capture filtering and replay cleanup."""

import ctypes
import threading
import unittest
from ctypes import wintypes
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import Mock

from orbit.input_macros import (
    STOP_VK, InputEvent, InputMacroStore, KeyboardHook, MouseHook, WindowsInput, validate_events,
)


class InputMacroTests(unittest.TestCase):
    def test_saved_macro_round_trip_and_overwrite(self):
        first = (InputEvent(0, "key", (65, 30, 0, 1)), InputEvent(25, "key", (65, 30, 0, 0)))
        second = (InputEvent(0, "button", (-50, 30, 1, 1)), InputEvent(20, "button", (-50, 31, 1, 0)))
        with TemporaryDirectory() as temp:
            store = InputMacroStore(Path(temp) / "macros.sqlite3")
            self.assertEqual(store.load(), {})
            store.save("Open Workspace", first)
            self.assertEqual(store.load(), {"open workspace": first})
            store.save("OPEN WORKSPACE", second)
            self.assertEqual(store.load(), {"open workspace": second})
            store.delete("Open Workspace")
            self.assertEqual(store.load(), {})

    def test_input_validation_rejects_stop_key_and_invalid_timing(self):
        for events in (
            (InputEvent(0, "key", (STOP_VK, 0, 0, 1)),),
            (InputEvent(60_001, "move", (0, 0)),),
            (InputEvent(1, "move", (0, 0)), InputEvent(0, "move", (0, 0))),
            (InputEvent(0, "button", (0, 0, 6, 1)),),
        ):
            with self.subTest(events=events), self.assertRaises(ValueError):
                validate_events(events)

    def native(self):
        native = WindowsInput.__new__(WindowsInput)
        native.cancel = threading.Event()
        native._keys = set()
        native._buttons = set()
        return native

    def test_keyboard_capture_ignores_injected_and_unpaired_up_and_consumes_stop(self):
        native = self.native()
        capture = Mock()
        released = KeyboardHook(65, 30, 0x80)
        injected = KeyboardHook(65, 30, 0x10)
        pressed = KeyboardHook(65, 30, 0)
        stop = KeyboardHook(STOP_VK, 0, 0)
        for record in (released, injected, pressed, released):
            self.assertFalse(native.keyboard(ctypes.addressof(record), capture))
        self.assertTrue(native.keyboard(ctypes.addressof(stop), capture))
        self.assertTrue(native.cancel.is_set())
        self.assertEqual([call.args for call in capture.call_args_list],
                         [("key", (65, 30, 0, 1)), ("key", (65, 30, 0, 0))])

    def test_mouse_capture_keeps_drag_and_signed_wheel(self):
        native = self.native()
        capture = Mock()
        left = MouseHook(wintypes.POINT(-12, 9))
        moved = MouseHook(wintypes.POINT(-10, 10))
        wheel = MouseHook(wintypes.POINT(-10, 10), 0xFF880000)
        for message, sample in ((0x0201, left), (0x0200, moved), (0x0202, moved), (0x020A, wheel)):
            native.mouse(message, ctypes.addressof(sample), capture)
        self.assertEqual([call.args for call in capture.call_args_list], [
            ("button", (-12, 9, 1, 1)), ("move", (-10, 10)),
            ("button", (-10, 10, 1, 0)), ("wheel", (-10, 10, 0, -120)),
        ])

    def test_replay_stop_releases_held_key_and_mouse_button(self):
        native = self.native()
        native.install_hook = Mock()
        native.uninstall_hooks = Mock()
        native.position = Mock()
        native.send_key = Mock()
        native.send_button = Mock()
        native.user = Mock()
        checks = iter((False, False, True))

        def pump():
            if next(checks):
                native.cancel.set()

        native.pump = pump
        events = (
            InputEvent(0, "key", (17, 29, 0, 1)),
            InputEvent(0, "button", (5, 6, 1, 1)),
            InputEvent(200, "key", (65, 30, 0, 1)),
        )
        progress = Mock()
        native.play(events, progress)
        self.assertEqual([call.args for call in native.send_key.call_args_list],
                         [(17, 29, 0, 1), (17, 29, 0, 0)])
        self.assertEqual([call.args for call in native.send_button.call_args_list], [(1, 1), (1, 0)])
        self.assertEqual([call.args for call in progress.call_args_list], [(1,), (2,)])
        native.uninstall_hooks.assert_called_once()
