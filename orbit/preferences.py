"""User-controlled assistant preferences and named Windows routines."""

import json
import re
from dataclasses import asdict, dataclass, field
from tempfile import NamedTemporaryFile
from pathlib import Path

from .actions import fast_action_route
from .config import PROFILE_DIR, VOICE_LANGUAGE, VOICE_NAME

PREFERENCES_PATH = PROFILE_DIR / "preferences.json"
VOICES = {
    "bm_george": "George · British",
    "bm_daniel": "Daniel · British",
    "bf_emma": "Emma · British",
    "bf_isabella": "Isabella · British",
    "am_michael": "Michael · American",
    "af_heart": "Heart · American",
    "af_nova": "Nova · American",
}
STYLES = {
    "Classic": "Calm, polished and conversational.",
    "Friendly": "Warm, relaxed and encouraging.",
    "Direct": "Plainspoken and brief. Lead with the answer.",
    "Playful": "Light and witty when appropriate. Be clear and respectful.",
}


@dataclass(frozen=True)
class Preferences:
    name: str = "ORBIT"
    voice: str = VOICE_NAME
    style: str = "Classic"
    listening: bool = False
    macros: dict[str, tuple[str, ...]] = field(default_factory=dict)
    motion: bool = True

    def __post_init__(self):
        if not isinstance(self.name, str) or not re.fullmatch(r"[A-Za-z][A-Za-z0-9 ]{0,23}", self.name):
            raise ValueError("Use a name of up to 24 letters, spaces and numbers, beginning with a letter.")
        if self.name != " ".join(self.name.split()):
            raise ValueError("Use a single space between words in the assistant name.")
        if (not isinstance(self.voice, str) or self.voice not in VOICES
                or not isinstance(self.style, str) or self.style not in STYLES
                or type(self.listening) is not bool or type(self.motion) is not bool):
            raise ValueError("Choose a supported voice, personality and microphone setting.")
        if not isinstance(self.macros, dict) or len(self.macros) > 20:
            raise ValueError("You can save up to 20 macros.")
        macros = {}
        for name, commands in self.macros.items():
            if not isinstance(name, str) or not re.fullmatch(r"[a-z0-9]+(?: [a-z0-9]+)*", name) or len(name) > 40:
                raise ValueError("Macro names can use up to 40 letters, numbers and spaces.")
            if (not isinstance(commands, (list, tuple)) or not 1 <= len(commands) <= 6
                    or any(not isinstance(cmd, str) or not fast_action_route(cmd) for cmd in commands)):
                raise ValueError(f"Give '{name}' one to six supported Windows commands.")
            macros[name] = tuple(commands)
        object.__setattr__(self, "macros", macros)

    @property
    def language(self):
        return "en-us" if self.voice.startswith("a") else VOICE_LANGUAGE


def read_preferences(path: Path = PREFERENCES_PATH):
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return Preferences(**data)
    except FileNotFoundError:
        return Preferences()
    except (OSError, ValueError, TypeError, RecursionError) as exc:
        raise ValueError("Could not read ORBIT preferences. Defaults are active until you save new settings.") from exc


def save_preferences(preferences, path: Path = PREFERENCES_PATH):
    path.parent.mkdir(parents=True, exist_ok=True)
    with NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, delete=False) as file:
        temporary = Path(file.name)
        try:
            json.dump(asdict(preferences), file, ensure_ascii=False, indent=2)
            file.close()
            temporary.replace(path)
        finally:
            temporary.unlink(missing_ok=True)
