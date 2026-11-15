"""Record and replay keyboard and mouse input on the Windows desktop."""

import ctypes
import json
import logging
import re
import sqlite3
import sys
import threading
from concurrent.futures import Future
from contextlib import closing
from ctypes import wintypes
from dataclasses import dataclass
from pathlib import Path
from time import perf_counter, sleep

from .config import PROFILE_DIR

STOP_KEY_LABEL = "F8"
STOP_VK = 0x77
MAX_RECORD_SECONDS = 60
MAX_EVENTS = 6000
MAX_MACROS = 50
STORE_PATH = PROFILE_DIR / "input_macros.sqlite3"

log = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class InputEvent:
    time_ms: int
    kind: str
    values: tuple[int, ...]


def normalize_macro_name(name):
    if not isinstance(name, str):
        raise ValueError("Name the recorded macro before saving.")
    name = " ".join(name.casefold().split())
    if not re.fullmatch(r"[a-z0-9]+(?: [a-z0-9]+)*", name) or len(name) > 40:
        raise ValueError("Use up to 40 letters, numbers and spaces for the recorded macro name.")
    return name


def validate_events(events):
    events = tuple(events)
    if not 1 <= len(events) <= MAX_EVENTS:
        raise ValueError("Record at least one input before saving a macro.")
    previous = -1
    for event in events:
        if not isinstance(event, InputEvent) or type(event.time_ms) is not int:
            raise ValueError("The macro contains an invalid input event.")
        if not previous <= event.time_ms <= MAX_RECORD_SECONDS * 1000 or event.time_ms < 0:
            raise ValueError("The macro contains invalid event timing.")
        previous = event.time_ms
        values = event.values
        if not isinstance(values, tuple) or any(type(value) is not int for value in values):
            raise ValueError("The macro contains invalid input values.")
        if event.kind == "key" and len(values) == 4:
            vk, scan, extended, down = values
            if (1 <= vk < 255 and vk not in {STOP_VK, 0xE5, 0xE7} and 0 <= scan <= 255
                    and extended in (0, 1) and down in (0, 1)):
                continue
        if event.kind in ("move", "button", "wheel"):
            tail_size = 0 if event.kind == "move" else 2
            if len(values) == 2 + tail_size and all(-65536 <= pos <= 65535 for pos in values[:2]):
                if event.kind == "move":
                    continue
                first, second = values[2:]
                if event.kind == "button" and 1 <= first <= 5 and second in (0, 1):
                    continue
                if event.kind == "wheel" and first in (0, 1) and -32768 <= second <= 32767 and second:
                    continue
        raise ValueError("The macro contains an unsupported input event.")
    return events


class InputMacroStore:
    """A separate local store so input recordings never enter chat history."""

    def __init__(self, path=STORE_PATH):
        self.path = Path(path)

    def connect(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        db = sqlite3.connect(self.path, timeout=3)
        try:
            db.execute("CREATE TABLE IF NOT EXISTS input_macros (name TEXT PRIMARY KEY, events TEXT NOT NULL)")
        except sqlite3.Error:
            db.close()
            raise
        return db

    def load(self):
        if not self.path.exists():
            return {}
        with closing(self.connect()) as db:
            rows = db.execute("SELECT name, events FROM input_macros ORDER BY name LIMIT ?", (MAX_MACROS + 1,)).fetchall()
        if len(rows) > MAX_MACROS:
            raise ValueError("The input macro store exceeds its size limit.")
        macros = {}
        try:
            for name, payload in rows:
                if len(payload) > MAX_EVENTS * 64 or normalize_macro_name(name) != name:
                    raise ValueError
                raw = json.loads(payload)
                if not isinstance(raw, list) or len(raw) > MAX_EVENTS:
                    raise ValueError
                macros[name] = validate_events(
                    InputEvent(time_ms, kind, tuple(values)) for time_ms, kind, values in raw
                )
        except (TypeError, ValueError, RecursionError) as exc:
            raise ValueError("A saved input macro is invalid.") from exc
        return macros

    def save(self, name, events):
        name = normalize_macro_name(name)
        events = validate_events(events)
        payload = json.dumps([(e.time_ms, e.kind, e.values) for e in events], separators=(",", ":"))
        with closing(self.connect()) as db, db:
            db.execute("BEGIN IMMEDIATE")
            if not db.execute("SELECT 1 FROM input_macros WHERE name = ?", (name,)).fetchone():
                if db.execute("SELECT COUNT(*) FROM input_macros").fetchone()[0] >= MAX_MACROS:
                    raise ValueError(f"You can save up to {MAX_MACROS} recorded macros.")
            db.execute("INSERT OR REPLACE INTO input_macros VALUES (?, ?)", (name, payload))

    def delete(self, name):
        name = normalize_macro_name(name)
        with closing(self.connect()) as db, db:
            db.execute("DELETE FROM input_macros WHERE name = ?", (name,))


class InputMacroSession:
    """Run one native recording or playback operation at a time."""

    def __init__(self):
        self._guard = threading.Lock()
        self._cancelled = threading.Event()
        self._thread = None
        self.event_count = 0

    def start_recording(self):
        return self._start(None)

    def start_playback(self, events):
        return self._start(validate_events(events))

    def _start(self, events):
        if sys.platform != "win32":
            raise OSError("Input macros require Windows.")
        with self._guard:
            if self._thread is not None and self._thread.is_alive():
                raise RuntimeError("An input macro is already running.")
            self._cancelled = threading.Event()
            self.event_count = 0
            result = Future()
            result.set_running_or_notify_cancel()
            self._thread = threading.Thread(
                target=self._run, args=(self._cancelled, events, result), name="ORBIT input macro", daemon=True
            )
            self._thread.start()
            return result

    def _run(self, cancel, events, result):
        failure = value = None
        try:
            native = WindowsInput(cancel)
            if events is None:
                value = native.record(self._count)
            else:
                native.play(events, self._count)
        except Exception as exc:
            failure = exc
        with self._guard:
            self._thread = None
        if failure is not None:
            result.set_exception(failure)
        else:
            result.set_result(value)

    def _count(self, size):
        self.event_count = size

    def stop(self):
        self._cancelled.set()

    def close(self):
        self.stop()
        thread = self._thread
        if thread is not None:
            thread.join(1)


ULONG_PTR = ctypes.c_size_t
LRESULT = ctypes.c_ssize_t
WM_MOUSEMOVE = 0x0200
WM_MOUSEWHEEL, WM_MOUSEHWHEEL = 0x020A, 0x020E
BUTTON_MESSAGES = {
    0x0201: (1, 1), 0x0202: (1, 0),
    0x0204: (2, 1), 0x0205: (2, 0),
    0x0207: (3, 1), 0x0208: (3, 0),
}
X_BUTTON_MESSAGES = (0x020B, 0x020C)
BUTTON_FLAGS = {
    1: (0x0002, 0x0004), 2: (0x0008, 0x0010), 3: (0x0020, 0x0040),
    4: (0x0080, 0x0100), 5: (0x0080, 0x0100),
}


class KeyboardHook(ctypes.Structure):
    _fields_ = [("vk", wintypes.DWORD), ("scan", wintypes.DWORD), ("flags", wintypes.DWORD),
                ("time", wintypes.DWORD), ("extra", ULONG_PTR)]


class MouseHook(ctypes.Structure):
    _fields_ = [("point", wintypes.POINT), ("data", wintypes.DWORD), ("flags", wintypes.DWORD),
                ("time", wintypes.DWORD), ("extra", ULONG_PTR)]


class MouseInput(ctypes.Structure):
    _fields_ = [("x", wintypes.LONG), ("y", wintypes.LONG), ("data", wintypes.DWORD),
                ("flags", wintypes.DWORD), ("time", wintypes.DWORD), ("extra", ULONG_PTR)]


class KeyboardInput(ctypes.Structure):
    _fields_ = [("vk", wintypes.WORD), ("scan", wintypes.WORD), ("flags", wintypes.DWORD),
                ("time", wintypes.DWORD), ("extra", ULONG_PTR)]


class InputFields(ctypes.Union):
    _fields_ = [("mouse", MouseInput), ("key", KeyboardInput)]


class NativeInput(ctypes.Structure):
    _fields_ = [("kind", wintypes.DWORD), ("fields", InputFields)]


class WindowsInput:
    def __init__(self, cancel):
        self.cancel = cancel
        self._keys = set()
        self._buttons = set()
        self._hooks = []
        self._procs = []
        self._stop_key_down = False
        self.callback_type = ctypes.WINFUNCTYPE(LRESULT, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM)
        self.user = ctypes.WinDLL("user32", use_last_error=True)
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.GetModuleHandleW.argtypes = (wintypes.LPCWSTR,)
        kernel.GetModuleHandleW.restype = wintypes.HMODULE
        self.module = kernel.GetModuleHandleW(None)
        self.user.SetWindowsHookExW.argtypes = (ctypes.c_int, self.callback_type, wintypes.HMODULE, wintypes.DWORD)
        self.user.SetWindowsHookExW.restype = wintypes.HANDLE
        self.user.CallNextHookEx.argtypes = (wintypes.HANDLE, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM)
        self.user.CallNextHookEx.restype = LRESULT
        self.user.UnhookWindowsHookEx.argtypes = (wintypes.HANDLE,)
        self.user.UnhookWindowsHookEx.restype = wintypes.BOOL
        self.user.PeekMessageW.argtypes = (ctypes.POINTER(wintypes.MSG), wintypes.HWND, wintypes.UINT,
                                           wintypes.UINT, wintypes.UINT)
        self.user.PeekMessageW.restype = wintypes.BOOL
        self.user.SendInput.argtypes = (wintypes.UINT, ctypes.POINTER(NativeInput), ctypes.c_int)
        self.user.SendInput.restype = wintypes.UINT
        self.user.SetThreadDpiAwarenessContext.argtypes = (ctypes.c_void_p,)
        self.user.SetThreadDpiAwarenessContext.restype = ctypes.c_void_p
        self.user.GetSystemMetrics.argtypes = (ctypes.c_int,)
        self.user.GetSystemMetrics.restype = ctypes.c_int
        self.message = wintypes.MSG()

    def pump(self):
        # PeekMessage dispatches the synchronous, cross-thread low-level hooks.
        self.user.PeekMessageW(ctypes.byref(self.message), None, 0, 0, 1)

    def install_hook(self, kind, handler):
        @self.callback_type
        def callback(code, message, data):
            if code == 0 and handler(message, data):
                return 1
            return self.user.CallNextHookEx(None, code, message, data)

        self.pump()
        handle = self.user.SetWindowsHookExW(kind, callback, self.module, 0)
        if not handle:
            raise OSError("Windows could not monitor keyboard or mouse input.")
        self._hooks.append(handle)
        self._procs.append(callback)

    def uninstall_hooks(self):
        # Swallow the matching key-up on ordinary F8 taps before removing the hook.
        deadline = perf_counter() + 0.5
        while self._stop_key_down and perf_counter() < deadline:
            self.pump()
            if self._stop_key_down:
                sleep(0.008)
        for handle in self._hooks:
            self.user.UnhookWindowsHookEx(handle)
        self._hooks.clear()
        self._procs.clear()

    def keyboard(self, data, capture=None):
        key = KeyboardHook.from_address(data)
        if key.flags & 0x10:  # Ignore injected input, including our own replay.
            return False
        down = not bool(key.flags & 0x80)
        if key.vk == STOP_VK:
            self._stop_key_down = down
            if down:
                self.cancel.set()
            return True
        if self.cancel.is_set() or capture is None or key.vk in {0, 0xE5, 0xE7, 255}:
            return False
        token = (key.vk, key.scan & 255, key.flags & 1)
        if down or token in self._keys:
            if down:
                self._keys.add(token)
            else:
                self._keys.discard(token)
            capture("key", (*token, int(down)))
        return False

    def mouse(self, message, data, capture):
        mouse = MouseHook.from_address(data)
        if mouse.flags & 1 or self.cancel.is_set():
            return False
        point = (mouse.point.x, mouse.point.y)
        if message == WM_MOUSEMOVE:
            capture("move", point)
        elif message in (WM_MOUSEWHEEL, WM_MOUSEHWHEEL):
            delta = ctypes.c_short(mouse.data >> 16).value
            if delta:
                capture("wheel", (*point, int(message == WM_MOUSEHWHEEL), delta))
        else:
            button = BUTTON_MESSAGES.get(message)
            if message in X_BUTTON_MESSAGES:
                button = (3 + (mouse.data >> 16), int(message == X_BUTTON_MESSAGES[0]))
            if button and 1 <= button[0] <= 5:
                which, down = button
                if down or which in self._buttons:
                    if down:
                        self._buttons.add(which)
                    else:
                        self._buttons.discard(which)
                    capture("button", (*point, which, down))
        return False

    def record(self, count):
        events = []
        started = perf_counter()
        first = None
        last_move = -100

        def capture(kind, values):
            nonlocal first, last_move
            now = perf_counter()
            if now - started >= MAX_RECORD_SECONDS:
                self.cancel.set()
                return
            if first is None:
                first = now
            timestamp = int((now - first) * 1000)
            if kind == "move":
                if timestamp - last_move < 12:
                    return
                last_move = timestamp
            events.append(InputEvent(timestamp, kind, values))
            count(len(events))
            if len(events) >= MAX_EVENTS:
                self.cancel.set()

        dpi = self.user.SetThreadDpiAwarenessContext(-4)  # DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2
        try:
            self.install_hook(13, lambda _message, data: self.keyboard(data, capture))
            self.install_hook(14, lambda message, data: self.mouse(message, data, capture))
            while not self.cancel.is_set() and perf_counter() - started < MAX_RECORD_SECONDS:
                self.pump()
                self.cancel.wait(0.008)
        finally:
            self.uninstall_hooks()
            if dpi:
                self.user.SetThreadDpiAwarenessContext(dpi)
        return tuple(events)

    def send(self, kind, **fields):
        data = NativeInput(kind, InputFields(**fields))
        if self.user.SendInput(1, ctypes.byref(data), ctypes.sizeof(data)) != 1:
            raise OSError("Windows blocked replay. Check that the target app is on the active desktop and uses the same privilege level.")

    def send_key(self, vk, scan, extended, down):
        flags = extended | (0 if down else 2)
        # Pause and Print Screen use multi-byte scan codes, so send their VK.
        if scan and vk not in (0x13, 0x2C):
            self.send(1, key=KeyboardInput(0, scan, flags | 8))
        else:
            self.send(1, key=KeyboardInput(vk, 0, flags))

    def send_button(self, which, down):
        flags = BUTTON_FLAGS[which][0 if down else 1]
        self.send(0, mouse=MouseInput(0, 0, which - 3 if which > 3 else 0, flags))

    def position(self, x, y):
        left, top, width, height = (self.user.GetSystemMetrics(index) for index in (76, 77, 78, 79))
        if not (left <= x < left + width and top <= y < top + height):
            raise OSError("A recorded mouse position is outside the current desktop. Restore the display layout or re-record the macro.")
        horizontal = ((x - left) * 65536 + 32768) // width
        vertical = ((y - top) * 65536 + 32768) // height
        self.send(0, mouse=MouseInput(horizontal, vertical, 0, 0xC001))

    def dispatch(self, event):
        if event.kind == "key":
            vk, scan, extended, down = event.values
            self.send_key(vk, scan, extended, down)
            token = (vk, scan, extended)
            if down:
                self._keys.add(token)
            else:
                self._keys.discard(token)
            return
        x, y, *data = event.values
        self.position(x, y)
        if event.kind == "button":
            which, down = data
            self.send_button(which, down)
            if down:
                self._buttons.add(which)
            else:
                self._buttons.discard(which)
        elif event.kind == "wheel":
            horizontal, delta = data
            self.send(0, mouse=MouseInput(0, 0, delta & 0xFFFFFFFF, 0x1000 if horizontal else 0x0800))

    def play(self, events, count):
        dpi = self.user.SetThreadDpiAwarenessContext(-4)
        try:
            self.install_hook(13, lambda _message, data: self.keyboard(data))
            started = perf_counter()
            for index, event in enumerate(events, 1):
                deadline = started + event.time_ms / 1000
                while not self.cancel.is_set():
                    self.pump()
                    wait = deadline - perf_counter()
                    if wait <= 0:
                        break
                    self.cancel.wait(min(0.008, wait))
                if self.cancel.is_set():
                    break
                self.dispatch(event)
                count(index)
        finally:
            try:
                for token in self._keys:
                    try:
                        self.send_key(*token, 0)
                    except OSError:
                        log.warning("event=input_macro_key_release_failed")
                for button in self._buttons:
                    try:
                        self.send_button(button, 0)
                    except OSError:
                        log.warning("event=input_macro_button_release_failed")
            finally:
                self.uninstall_hooks()
                if dpi:
                    self.user.SetThreadDpiAwarenessContext(dpi)
