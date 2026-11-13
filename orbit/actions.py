"""Allowlisted Windows actions, intent parsing and session permissions."""

import os
import platform
import re
import time
from pathlib import Path

from .config import CREATOR, ROOT

ALLOWED_APPS = {
    "vscode": "Visual Studio Code",
    "spotify": "Spotify",
    "calculator": "Calculator",
    "notepad": "Notepad",
    "paint": "Paint",
    "explorer": "File Explorer",
    "settings": "Windows Settings",
}
ALLOWED_FOLDERS = {
    "desktop": "Desktop", "downloads": "Downloads", "documents": "Documents",
    "pictures": "Pictures", "music": "Music", "videos": "Videos",
    "orbit": "ORBIT project",
}
SYSTEM_QUERIES = {
    "cpu": "CPU usage", "ram": "Memory usage", "disk": "Disk storage",
    "processes": "Running processes", "specs": "Computer specifications",
    "overview": "System overview",
}
APP_ALIASES = {
    "visual studio code": "vscode", "vs code": "vscode", "vscode": "vscode",
    "code editor": "vscode", "spotify": "spotify", "calculator": "calculator",
    "calc": "calculator", "notepad": "notepad", "paint": "paint",
    "file explorer": "explorer", "windows explorer": "explorer",
    "windows settings": "settings", "settings app": "settings", "settings": "settings",
}


FOLDER_IDS = {
    "desktop": "B4BFCC3A-DB2C-424C-B029-7FE99A87C641",
    "downloads": "374DE290-123F-4565-9164-39C4925E467B",
    "documents": "FDD39AD0-238F-46AF-ADB4-6C85480369C7",
    "pictures": "33E28130-4E1E-4676-835A-98395C3BC3BB",
    "music": "4BD8D571-6D19-48D3-BE97-422220080E43",
    "videos": "18989B1D-99B5-455B-841C-AB7C74E4DDFC",
}
ACTION_TARGETS = {
    "open_app": ALLOWED_APPS, "open_folder": ALLOWED_FOLDERS,
    "system_info": SYSTEM_QUERIES, "lock_pc": {"none": "Lock Windows"},
}
STATE_CHANGING = {"open_app", "open_folder", "lock_pc"}
SYSTEM_ALIASES = {
    "cpu": r"(?:cpu|processor)(?: usage| load)?",
    "ram": r"(?:ram|memory)(?: usage)?|available (?:ram|memory)",
    "disk": r"disk(?: usage| space| storage)?|storage(?: usage| space)?|drive space|free space",
    "processes": r"(?:(?:active|running|top) )?(?:processes|programs)",
    "specs": r"(?:(?:computer|pc|system|hardware) )?(?:specs|specifications)",
    "overview": r"(?:system|computer|pc) (?:status|overview)",
}


def validate_action(action, target):
    if not isinstance(action, str) or not isinstance(target, str) or target not in ACTION_TARGETS.get(action, {}):
        raise PermissionError("ORBIT blocked an unsupported Windows action.")


class ActionPermissions:
    def __init__(self):
        self.session = set()

    def needs_confirmation(self, action, target):
        validate_action(action, target)
        return action == "lock_pc" or (action in STATE_CHANGING and (action, target) not in self.session)

    def approve(self, action, target):
        validate_action(action, target)
        if action in {"open_app", "open_folder"}:
            self.session.add((action, target))


def fast_action_route(message):
    text = " ".join(message.casefold().split()).strip(" .?!")
    text = re.sub(r"^orbit\b[ ,.:]*", "", text)
    text = re.sub(r"^(?:(?:can|could|would|will) you )?(?:please )?", "", text)
    text = re.sub(r",? please$", "", text)
    if re.fullmatch(r"lock (?:my |this |the )?(?:pc|computer|windows|screen|workstation)(?: now)?", text):
        return "lock_pc", "none"

    launch = re.fullmatch(r"(?:open|launch|start|run|bring up|pull up|show me) (.+)", text)
    if launch:
        name = re.sub(r"^(?:my|the) ", "", launch[1])
        if name in APP_ALIASES:
            return "open_app", APP_ALIASES[name]
        folder = re.sub(r" (?:folder|directory)$", "", name)
        if folder in {"orbit", "orbit project"} and (folder != name or name == "orbit project"):
            return "open_folder", "orbit"
        if folder in FOLDER_IDS:
            return "open_folder", folder

    info = re.fullmatch(
        r"(?:check|report|list|show(?: me)?|tell me(?: about)?|what(?: is| are|'s)) "
        r"(?:(my|this|the|current) )?(.+)", text,
    )
    if info:
        for target, pattern in SYSTEM_ALIASES.items():
            if re.fullmatch(pattern, info[2]) and not (text.startswith("what") and not info[1]):
                return "system_info", target
    if re.fullmatch(r"how much (?:disk space|storage|drive space) (?:is free|is left|do i have)(?: on (?:my|this|the) (?:pc|computer|drive))?", text):
        return "system_info", "disk"
    if re.fullmatch(r"how much (?:ram|memory) (?:is available|is free|do i have)", text):
        return "system_info", "ram"
    if re.fullmatch(r"(?:what|which) (?:programs|processes) are (?:running|using (?:my |the )?cpu)", text):
        return "system_info", "processes"
    return None


def authorise_model_action(message, action, target):
    """Validate an action proposal against the Maker's complete typed request."""
    return fast_action_route(message) == (action, target)


def unsupported_action_request(message):
    return bool(re.match(
        r"^(?:orbit[ ,.:]+)?(?:(?:can|could|would|will) you )?(?:please )?"
        r"(?:(?:open|launch|run|execute|lock|delete|uninstall|format|wipe)\s+\S|"
        r"(?:shutdown|shut down|restart|reboot)(?:[ .!?]|$))",
        message.strip(), re.I,
    ))


def identity_response(message):
    text = message.lower().strip()
    if re.fullmatch(r"(hello|hi|hey|hello orbit|hi orbit|hey orbit)[!., ]*", text):
        return "Hello, Maker. What can I do for you?"
    if re.search(r"\bwho\b.*\b(created|built|made|developed|designed)\b", text):
        if re.search(r"\b(?:qwen(?:2\.5)?|(?:language |underlying |ai )?model)\b", text):
            if "qwen" in text:
                return f"The Qwen team developed Qwen. {CREATOR} created the ORBIT application."
            return f"My underlying model was built by its own developers. {CREATOR} created ORBIT."
        if re.search(r"\b(?:voice|kokoro|library|libraries)\b", text):
            return f"The voice engine and libraries have their own developers. {CREATOR} assembled ORBIT."
        if re.search(r"\b(you|orbit)\b", text):
            return f"{CREATOR} created ORBIT and gave me my identity."
    if re.search(r"\b(who am i to you|what am i to you|am i your maker|who is your maker)\b", text):
        return "You're my Maker. You're in charge of this ORBIT installation."
    return None


class WindowsController:
    def __init__(self):
        self.home = Path.home()

    def resolve_folder(self, name):
        validate_action("open_folder", name)
        if name == "orbit":
            return ROOT
        import ctypes
        from uuid import UUID

        folder_id = ctypes.create_string_buffer(UUID(FOLDER_IDS[name]).bytes_le)
        path = ctypes.c_wchar_p()
        try:
            result = ctypes.windll.shell32.SHGetKnownFolderPath(folder_id, 0, None, ctypes.byref(path))
            if result == 0 and path.value:
                folder = Path(path.value)
                if folder.is_dir():
                    return folder
        finally:
            if path:
                ctypes.windll.ole32.CoTaskMemFree(path)
        raise FileNotFoundError(f"Windows could not locate the {ALLOWED_FOLDERS[name]} folder.")

    @staticmethod
    def registered_executable(filename):
        import winreg

        key_name = rf"Software\Microsoft\Windows\CurrentVersion\App Paths\{filename}"
        for hive in (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE):
            for view in (0, winreg.KEY_WOW64_32KEY, winreg.KEY_WOW64_64KEY):
                try:
                    with winreg.OpenKey(hive, key_name, 0, winreg.KEY_READ | view) as key:
                        raw, _ = winreg.QueryValueEx(key, "")
                        path = Path(os.path.expandvars(raw.strip('"')))
                        if path.is_absolute() and path.name.casefold() == filename.casefold() and path.is_file():
                            return path
                except OSError:
                    continue
        return None

    def locate_vscode(self):
        registered = self.registered_executable("Code.exe")
        if registered:
            return registered
        candidates = [
            Path(os.environ[var]) / relative
            for var, relative in (
                ("LOCALAPPDATA", "Programs/Microsoft VS Code/Code.exe"),
                ("ProgramFiles", "Microsoft VS Code/Code.exe"),
                ("ProgramFiles(x86)", "Microsoft VS Code/Code.exe"),
            )
            if os.environ.get(var)
        ]
        # The Windows installer often adds only the bin subfolder to PATH.
        for entry in os.get_exec_path():
            folder = Path(entry.strip('"'))
            if folder.is_absolute():
                candidates.extend((folder / "Code.exe", folder.parent / "Code.exe"))
        for candidate in candidates:
            if candidate.is_file():
                return candidate
        raise FileNotFoundError("Visual Studio Code was not found.")

    def open_app(self, name):
        validate_action("open_app", name)
        if name == "vscode":
            os.startfile(str(self.locate_vscode()))
        elif name == "spotify":
            import winreg

            try:
                with winreg.OpenKey(winreg.HKEY_CLASSES_ROOT, "spotify") as key:
                    winreg.QueryValueEx(key, "URL Protocol")
            except OSError as exc:
                registered = self.registered_executable("Spotify.exe")
                if registered is None:
                    raise FileNotFoundError("Spotify does not appear to be installed.") from exc
                os.startfile(str(registered))
            else:
                os.startfile("spotify:")
        elif name == "settings":
            os.startfile("ms-settings:")
        else:
            import ctypes

            system = ctypes.create_unicode_buffer(32768)
            count = ctypes.windll.kernel32.GetWindowsDirectoryW(system, len(system))
            if not 0 < count < len(system):
                raise OSError("Windows could not locate its system directory.")
            executables = {
                "calculator": "System32/calc.exe", "notepad": "System32/notepad.exe",
                "paint": "System32/mspaint.exe", "explorer": "explorer.exe",
            }
            path = Path(system.value) / executables[name]
            if path.is_file():
                os.startfile(str(path))
            else:
                # These inbox apps can also be installed as Store packages.
                fallback = {"calculator": "calculator:", "paint": "ms-paint:", "notepad": "ms-notepad:"}
                if name not in fallback:
                    raise FileNotFoundError(f"{ALLOWED_APPS[name]} was not found.")
                os.startfile(fallback[name])
        return f"Windows accepted the request to open {ALLOWED_APPS[name]}, Maker."

    def open_folder(self, name):
        path = self.resolve_folder(name)
        os.startfile(str(path))
        return f"Windows accepted the request to open your {ALLOWED_FOLDERS[name]} folder, Maker."

    def system_information(self, kind):
        if kind not in SYSTEM_QUERIES:
            raise PermissionError("Unsupported system information request.")
        import psutil
        gb = 1024 ** 3
        if kind == "cpu":
            return f"Your CPU is at {psutil.cpu_percent(interval=0.25):.0f} percent usage, Maker."
        if kind == "ram":
            m = psutil.virtual_memory()
            return f"You have {m.total / gb:.1f} gigabytes of RAM, with {m.available / gb:.1f} gigabytes available, Maker."
        if kind == "disk":
            d = psutil.disk_usage(os.environ.get("SystemDrive", self.home.drive) + "\\")
            return f"Your Windows drive has {d.free / gb:.1f} gigabytes free out of {d.total / gb:.1f}, Maker."
        if kind == "specs":
            m = psutil.virtual_memory()
            return (f"You're running {platform.system()} {platform.release()} on {platform.machine()}, "
                    f"with {m.total / gb:.1f} gigabytes of RAM and {psutil.cpu_count()} logical processors, Maker.")
        if kind == "overview":
            return f"Systems operational, Maker. CPU usage is {psutil.cpu_percent(interval=0.2):.0f} percent and RAM usage is {psutil.virtual_memory().percent:.0f} percent."

        processes = []
        for p in psutil.process_iter(attrs=["name"]):
            try:
                p.cpu_percent(interval=None)
                processes.append(p)
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
        time.sleep(0.35)
        active = []
        for p in processes:
            try:
                value = p.cpu_percent(interval=None)
                if value > 0:
                    active.append((p.name(), value))
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
        active.sort(key=lambda item: item[1], reverse=True)
        names = []
        for name, value in active:
            if name not in names:
                names.append(name)
            if len(names) == 3:
                break
        if not names:
            return "No processes showed notable CPU activity during this short sample, Maker."
        return "During this sample, the most CPU-active processes included " + ", ".join(names) + "."

    def execute(self, action, target, *, approved=False):
        validate_action(action, target)
        if action in STATE_CHANGING and approved is not True:
            raise PermissionError("This Windows action requires the Maker's approval.")
        if action == "open_app":
            return self.open_app(target)
        if action == "open_folder":
            return self.open_folder(target)
        if action == "system_info":
            return self.system_information(target)
        if action == "lock_pc" and target == "none":
            import ctypes
            if ctypes.windll.user32.LockWorkStation() == 0:
                raise OSError("Windows declined the lock request.")
            return "The Windows lock request was accepted, Maker."
        raise PermissionError("ORBIT blocked an unsupported action.")
