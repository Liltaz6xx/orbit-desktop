"""Defaults and validated settings for the Windows desktop application."""

import os
import re
import tomllib
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit

from . import __version__

APP_NAME = "ORBIT"
APP_VERSION = __version__
CREATOR = "Liltaz6xx"
ROOT = Path(__file__).resolve().parent.parent
ASSETS = ROOT / "assets"
PROFILE_DIR = Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local") / "ORBIT Desktop"
DATA_DIR = PROFILE_DIR
DATABASE_PATH = PROFILE_DIR / "orbit_memory.sqlite3"
CONFIG_PATH = PROFILE_DIR / "orbit.toml"
DEFAULT_OLLAMA_URL = "http://127.0.0.1:11434"
DEFAULT_MODEL = "qwen2.5:1.5b"
MAX_CONVERSATION_PAIRS = 10
MAX_RELEVANT_MEMORIES = 8
MAX_MEMORY_LENGTH = 500
VOICE_MODEL = "kokoro-v1.0.onnx"
LEGACY_VOICE_MODEL = "kokoro-v1.0.int8.onnx"
VOICE_LIBRARY = "voices-v1.0.bin"
VOICE_NAME = "bm_george"
VOICE_LANGUAGE = "en-gb"
VOICE_SPEED = 0.90
AUDIO_LEVEL_GAIN = 9.0


def voice_files() -> tuple[Path, Path]:
    profile_voice = PROFILE_DIR / "voice"
    # Prefer the faster export even when the profile contains the older model.
    for name in (VOICE_MODEL, LEGACY_VOICE_MODEL):
        for directory in (profile_voice, ASSETS):
            model, library = directory / name, directory / VOICE_LIBRARY
            if model.is_file() and library.is_file():
                return model, library
    return profile_voice / VOICE_MODEL, profile_voice / VOICE_LIBRARY


class ConfigError(ValueError):
    """A setting needs to be corrected before starting ORBIT."""


@dataclass(frozen=True, slots=True)
class Settings:
    ollama_url: str = DEFAULT_OLLAMA_URL
    model: str = DEFAULT_MODEL
    timeout: float = 180
    max_tokens: int = 220
    database_path: Path = DATABASE_PATH

    def __post_init__(self):
        try:
            url = urlsplit(self.ollama_url)
            url.port
        except (ValueError, AttributeError) as exc:
            raise ConfigError("Set ollama.url to a loopback HTTP address.") from exc
        if (
            url.scheme != "http" or url.hostname not in {"localhost", "127.0.0.1", "::1"}
            or url.path not in {"", "/"} or url.username is not None or url.query or url.fragment
        ):
            raise ConfigError("Set ollama.url to a loopback HTTP address, such as http://127.0.0.1:11434.")
        if not isinstance(self.model, str) or not re.fullmatch(
            r"[A-Za-z0-9][A-Za-z0-9_.-]*(?:/[A-Za-z0-9][A-Za-z0-9_.-]*){0,2}"
            r"(?::[A-Za-z0-9][A-Za-z0-9_.-]*)?", self.model
        ):
            raise ConfigError("Set ollama.model to a valid local model name.")
        tag = self.model.rpartition(":")[2].lower()
        if tag == "cloud" or tag.endswith("-cloud"):
            raise ConfigError("Choose an installed local model for ORBIT.")
        if type(self.timeout) not in (float, int) or not 1 <= self.timeout <= 600:
            raise ConfigError("Set ollama.timeout to a number between 1 and 600 seconds.")
        if type(self.max_tokens) is not int or not 32 <= self.max_tokens <= 1024:
            raise ConfigError("Set ollama.max_tokens to an integer between 32 and 1024.")


def load_settings(path: Path = CONFIG_PATH) -> Settings:
    try:
        with path.open("rb") as file:
            config = tomllib.load(file)
    except FileNotFoundError:
        config = {}
    except (OSError, ValueError) as exc:
        raise ConfigError("Could not read orbit.toml. Check its syntax and file permissions.") from exc
    ollama = config.get("ollama", {})
    if not isinstance(ollama, dict) or config.keys() - {"ollama"}:
        raise ConfigError("Use an [ollama] table in orbit.toml.")
    fields = {"url": "ollama_url", "model": "model", "timeout": "timeout", "max_tokens": "max_tokens"}
    if ollama.keys() - fields.keys():
        raise ConfigError("Supported [ollama] settings are url, model, timeout and max_tokens.")
    if "url" in ollama and not isinstance(ollama["url"], str):
        raise ConfigError("Set ollama.url to a loopback HTTP address.")
    values = {fields[key]: value for key, value in ollama.items()}
    for env_name, setting in (("ORBIT_OLLAMA_URL", "ollama_url"), ("ORBIT_OLLAMA_MODEL", "model")):
        if env_name in os.environ:
            values[setting] = os.environ[env_name]
    return Settings(**values)
