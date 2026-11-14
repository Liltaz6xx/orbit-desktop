"""Read-only health checks, independent of the GUI startup path."""

import argparse
import importlib
import sqlite3
import sys
from contextlib import closing

from .ai import OllamaClient, OllamaError
from .config import APP_VERSION, ASSETS, ConfigError, PROFILE_DIR, load_settings, voice_files
from .memory import SCHEMA_VERSION, MemoryStore

PACKAGES = {
    "PySide6-Essentials": ("PySide6.QtWidgets",),
    "numpy": ("numpy",),
    "psutil": ("psutil",),
    "sounddevice": ("sounddevice",),
    "kokoro-onnx": ("kokoro_onnx", "onnxruntime", "phonemizer"),
}


def check_database(path):
    if not path.exists():
        return "Database will be created on first run."
    with closing(sqlite3.connect(path.as_uri() + "?mode=ro", uri=True, timeout=2)) as db:
        db.execute("PRAGMA query_only=ON")
        if db.execute("PRAGMA quick_check").fetchone()[0] != "ok":
            raise sqlite3.DatabaseError("SQLite quick check failed.")
        version = db.execute("PRAGMA user_version").fetchone()[0]
        if version not in {0, 1, SCHEMA_VERSION}:
            raise sqlite3.DatabaseError("Unsupported schema version.")
        MemoryStore.validate_schema(db, require_revision=version == SCHEMA_VERSION)
        return f"Database healthy (schema {version})."


def main(argv=None):
    parser = argparse.ArgumentParser(description="Check the ORBIT installation without starting the GUI.")
    parser.add_argument("--model-name", action="store_true", help="Print the configured model for the setup script.")
    args = parser.parse_args(argv)
    try:
        settings = load_settings()
    except ConfigError as exc:
        print(f"[FAIL] Configuration - {exc}", file=sys.stderr)
        return 1
    if args.model_name:
        print(settings.model)
        return 0

    failures = []

    def report(ok, message):
        print(f"[{'OK' if ok else 'FAIL'}] {message}")
        if not ok:
            failures.append(message)

    print(f"ORBIT {APP_VERSION} system check")
    print(f"Local profile: {PROFILE_DIR}")
    report(sys.version_info[:2] == (3, 12), f"Python {sys.version.split()[0]} ({sys.executable})")
    for package, modules in PACKAGES.items():
        try:
            for module in modules:
                importlib.import_module(module)
        except Exception as exc:
            report(False, f"{package} could not load ({type(exc).__name__}). Run Setup_ORBIT.bat.")
        else:
            report(True, package)
    try:
        from PySide6.QtGui import QImage
        for name in ("orbit_core.png", "orbit_halo.png", "orbit.ico"):
            report(not QImage(str(ASSETS / name)).isNull(), f"Visual asset {name}")
    except ImportError:
        report(False, "Visual assets could not be decoded without PySide6.")
    for path, minimum_size in zip(voice_files(), (50_000_000, 20_000_000)):
        try:
            report(path.is_file() and path.stat().st_size >= minimum_size, f"Voice asset {path.name}")
        except OSError:
            report(False, f"Voice asset {path.name} could not be read.")

    client = OllamaClient(settings)
    try:
        version = client.read_json("/api/version").get("version")
        report(isinstance(version, str) and bool(version), f"Ollama local API at {settings.ollama_url}"
               + (f" (version {version})" if isinstance(version, str) else ""))
        client.check_model()
        report(True, f"Installed local model {settings.model}")
    except OllamaError as exc:
        report(False, str(exc))
    finally:
        client.close()

    try:
        report(True, check_database(settings.database_path))
    except (OSError, sqlite3.Error) as exc:
        report(False, f"SQLite health check failed ({type(exc).__name__}). Review data folder permissions and schema.")

    try:
        import sounddevice as sd

        device = sd.query_devices(kind="output")
        rate = int(device["default_samplerate"])
        sd.check_output_settings(samplerate=rate, channels=1, dtype="float32")
        report(True, f"Audio output {device['name']} ({rate} Hz)")
        try:
            sd.check_output_settings(samplerate=24_000, channels=1, dtype="float32")
        except sd.PortAudioError:
            print("[INFO] The default device does not accept Kokoro's 24 kHz output directly.")
    except Exception as exc:
        report(False, f"Audio output unavailable ({type(exc).__name__}). Check the Windows default playback device.")
    return int(bool(failures))


if __name__ == "__main__":
    sys.exit(main())
