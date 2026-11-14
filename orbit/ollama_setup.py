"""Find and start local Ollama, and provision the default model during setup."""

import os
import subprocess
import sys
import time
from pathlib import Path
from urllib.parse import urlsplit

from .ai import OllamaClient, OllamaError, OllamaModelMissing
from .config import DEFAULT_MODEL, PROFILE_DIR, ConfigError, load_settings

NOT_INSTALLED = 10
UNINSTALL_KEY = r"Software\Microsoft\Windows\CurrentVersion\Uninstall\{44E83376-CE68-45EB-8FC1-393500EB558C}_is1"


def find_ollama() -> Path | None:
    if sys.platform != "win32":
        return None
    import winreg

    locations = []
    for hive in (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE):
        for view in (winreg.KEY_WOW64_64KEY, winreg.KEY_WOW64_32KEY):
            try:
                with winreg.OpenKey(hive, UNINSTALL_KEY, 0, winreg.KEY_READ | view) as key:
                    locations.append(winreg.QueryValueEx(key, "InstallLocation")[0])
            except OSError:
                continue
    if local := os.environ.get("LOCALAPPDATA"):
        locations.append(str(Path(local) / "Programs" / "Ollama"))
    locations.extend(os.get_exec_path())
    for value in locations:
        if not isinstance(value, str):
            continue
        directory = Path(os.path.expandvars(value.strip('"')))
        executable = directory / "ollama.exe"
        if directory.is_absolute() and executable.is_file():
            return executable
    return None


def default_server(url: str) -> bool:
    endpoint = urlsplit(url)
    return endpoint.hostname in {"localhost", "127.0.0.1"} and endpoint.port == 11434


def server_ready(client: OllamaClient) -> bool:
    try:
        version = client.read_json("/api/version").get("version")
    except OllamaError:
        return False
    return isinstance(version, str) and bool(version)


def start_server(executable: Path) -> None:
    env = os.environ.copy()
    env["OLLAMA_HOST"] = "127.0.0.1:11434"
    env["OLLAMA_NO_CLOUD"] = "1"
    desktop = executable.with_name("ollama app.exe")
    if desktop.is_file():
        command = [str(desktop), "hidden"]
    else:
        command = [str(executable), "serve"]
    # The server can be shared by other apps and outlives the Setup process.
    with (PROFILE_DIR / "ollama-start.log").open("ab") as log:
        subprocess.Popen(command, cwd=executable.parent, env=env, stdin=subprocess.DEVNULL,
                         stdout=log, stderr=log,
                         creationflags=subprocess.CREATE_NO_WINDOW)


def provision(client: OllamaClient) -> int:
    if not server_ready(client):
        if not default_server(client.settings.ollama_url):
            print("The custom Ollama address is unavailable. Start that server and rerun Setup.", flush=True)
            return 1
        executable = find_ollama()
        if executable is None:
            return NOT_INSTALLED

        print("Starting the local Ollama server.", flush=True)
        PROFILE_DIR.mkdir(parents=True, exist_ok=True)
        start_server(executable)
        for _ in range(30):
            if server_ready(client):
                break
            time.sleep(1)
        else:
            raise OllamaError("Ollama did not start. Check ollama-start.log in the ORBIT profile.")

    try:
        client.check_model()
    except OllamaModelMissing:
        if client.settings.model.casefold() != DEFAULT_MODEL:
            print("Keeping your custom model selection. Install that model in Ollama to use it.", flush=True)
            return 0
        print(f"Downloading {DEFAULT_MODEL} through Ollama.", flush=True)
        reported = set()

        def report(frame):
            total = frame.get("total")
            completed = frame.get("completed")
            if type(total) is int and type(completed) is int and total >= 10_000_000 and 0 <= completed <= total:
                bucket = completed * 10 // total
                if bucket not in reported:
                    reported.add(bucket)
                    print(f"Downloading {DEFAULT_MODEL}: {bucket * 10}%", flush=True)

        client.pull_model(report)
        client.check_model()
        print(f"Model {DEFAULT_MODEL} verified and ready.", flush=True)
    else:
        print(f"Reusing installed Ollama model {client.settings.model}.", flush=True)
    return 0


def main() -> int:
    try:
        client = OllamaClient(load_settings())
        try:
            return provision(client)
        finally:
            client.close()
    except (ConfigError, OllamaError, OSError) as exc:
        print(str(exc), flush=True)
        return 1


if __name__ == "__main__":
    sys.exit(main())
