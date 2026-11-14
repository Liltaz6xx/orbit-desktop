# ORBIT developer guide

| Area | Source |
| --- | --- |
| Startup, version and settings | `main.py`, `orbit/config.py`, `orbit/__init__.py` |
| Qt controls, dark window frame and orb | `orbit/window.py`, `orbit/theme.py`, `orbit/visuals.py` |
| Request lifecycle and background work | `orbit/models.py`, `orbit/workers.py`, `orbit/conversation.py` |
| Local AI and Maker Protocol | `orbit/ai.py`, `orbit/prompts.py` |
| SQLite and memory commands | `orbit/memory.py` |
| Windows allowlist, permission policy and discovery | `orbit/actions.py` |
| Segmentation, Kokoro, playback and Windows fallback | `orbit/voice.py`, `orbit/audio.py` |
| Health check and rotating logs | `orbit/diagnostics.py`, `orbit/logging_setup.py` |

## Request lifecycle

Each turn has a unique ID. Three long-lived workers handle conversation, synthesis and playback. Qt widgets are updated by signals on the GUI thread. Text and audio queues are bounded. Stop invalidates the turn immediately, wakes workers, interrupts Ollama reads and aborts audio. An in-flight native Kokoro inference may finish before the synthesis worker picks up the replacement turn. Its samples are discarded on cancellation. The playback worker owns device and fallback subprocess cleanup.

Ollama requests use a direct loopback HTTP connection, validate the selected model against the local inventory and reuse connections when the server keeps them open. Only completed replies can be archived. [Ollama chat API](https://docs.ollama.com/api/chat) · [Ollama model inventory](https://docs.ollama.com/api/tags)

## Memory

The public edition keeps its SQLite database, logs and optional settings under
%LOCALAPPDATA%\ORBIT Desktop. Tests use their own temporary databases.

SQLite keeps explicit facts in `memories`, previous model replies in `conversations` and the archive revision in `context_revision`. Schema migrations run in a transaction and preserve existing rows and IDs. Retrieval ranks saved facts by term overlap and reads recent conversation turns from SQLite when building a prompt.

Forget shows the matching saved records for approval and clears old conversation context in the same transaction. Matching saved notes are identified by normalised terms and text containment. A revision change invalidates pending archive writes so a stale reply cannot put cleared context back into history. Distinct paraphrases may need a separate forget command.

## Windows tools

Register fixed action and target values in `ACTION_TARGETS` and a complete typed command in `fast_action_route`. Add a controller method that uses a fixed application identifier or a Windows known folder. Read-only system information runs without confirmation. App and folder approvals are cached per target for the current session. The lock action always requires fresh confirmation. Keep permissions outside model inference.

## Checks

Run from the project directory:

~~~powershell
.\.venv\Scripts\python.exe -m compileall -q main.py orbit scripts tests
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe -m pip check
.\Check_ORBIT.bat --no-pause
~~~

Tests use temporary SQLite databases, a loopback mock server, offscreen Qt and mocked Windows actions. The environment checker queries the real local services. Audio logs include synthesis duration, first audio latency and silence caused by late chunks.

## Publishing a release

The release workflow tests the tagged commit, builds the ZIP and installer,
exercises the installer, and publishes the build as the latest GitHub release.
Review the release notes before pushing the tag. If the workflow did not start,
run **Publish Windows release** manually for that tag.

Build locally from a committed tree with Python 3.12 and Inno Setup 6.7.4:

~~~powershell
.\.venv\Scripts\python.exe scripts\build_release.py
.\scripts\build_installer.ps1 -Compiler 'C:\Program Files (x86)\Inno Setup 6\ISCC.exe'
~~~

The ZIP contains the tracked application source, artwork, docs and launchers.
The package script uses an explicit file list and reads each file from the
commit. The ZIP works with the same setup instructions as the repository.

The installer provisions a private Python runtime and installs wheels from
installer/requirements-win-x64.txt with SHA-256 verification. A setup run
reuses the runtime when the Python version and lock file match. It uses
Ollama's loopback API to provision the default model and installs Ollama
with the official, hash-pinned EXE if it cannot find an existing installation.
Kokoro assets are verified and stored in the Windows profile.
Keep
the Inno Setup AppId stable so Windows detects upgrades. Run the installer
test only on a disposable Windows runner or Windows Sandbox account.
