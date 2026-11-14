# ORBIT Desktop

**A voice-first AI assistant for Windows 11.** Type a request and hear ORBIT’s reply in a British voice. The orb animates as ORBIT thinks, speaks and runs approved Windows actions.

![ORBIT's illuminated orbital core against a near-black background](assets/preview.jpg)

Created by [Liltaz6xx](https://github.com/Liltaz6xx). ORBIT calls the operator of each installation **Maker**.

## Install or update on Windows 11

1. Download the **Windows x64 Setup EXE** and its SHA-256 checksum. The installer is unsigned, so Windows SmartScreen may display a warning. [GitHub Releases](https://github.com/Liltaz6xx/orbit-desktop/releases)
2. Run Setup. It installs for your Windows account in %LOCALAPPDATA%\Programs\ORBIT Desktop and downloads a private Python runtime and verified dependencies. The Start menu shortcut is always created and the desktop shortcut box is checked on a fresh install.
3. Install and start Ollama for Windows. In PowerShell, install the default model. [Ollama for Windows](https://ollama.com/download/windows) · [Model page](https://ollama.com/library/qwen2.5:1.5b)

   ~~~powershell
   ollama pull qwen2.5:1.5b
   ~~~

4. Open **ORBIT Desktop**. Press **Enter** to send, **Esc** to stop, or **Read reply** to open the latest answer. To enable Kokoro, choose **Download Kokoro voice** in the ORBIT Desktop Start menu folder and reopen ORBIT after the download.

For updates, download and run the newer Setup EXE. Setup finds the existing installation and replaces its program files. It remembers the desktop shortcut choice. Settings, memories and downloaded voice files live in the separate ORBIT Desktop profile and survive updates and uninstall.

## Share your activity on Discord

Open the Discord desktop app and sign in. In ORBIT, select **Discord**, check **Share activity with Discord**, and select **Save**. Discord can show **Playing ORBIT** while the app is open if activity sharing is allowed in Discord. Turn the option off in ORBIT to clear its activity. Sharing starts off on every new profile. Prompts, replies and saved memories stay local. [Discord activity sharing](https://support.discord.com/hc/en-us/articles/7931156448919-Activity-Sharing-on-Discord-FAQ)

## Run from source

Extract the Windows ZIP or clone the repository. Install 64-bit Python 3.12, run **Setup_ORBIT.bat**, then **Run_ORBIT.bat**. The source copy and installer edition share the public ORBIT Desktop profile for your Windows account. [Python downloads](https://www.python.org/downloads/windows/)

## Try these commands

| Type | What happens |
| --- | --- |
| `Who made you?` | ORBIT credits its creator. |
| `Remember that my rover is silver` | Saves a fact in your local profile and returns a memory number. |
| `Search memories for rover` | Finds matching saved facts. |
| `Forget memory 1` | Asks before deleting the selected fact, any matching saved notes shown in the dialog and conversation history. |
| `Clear conversation` | Asks before removing conversation history. Saved facts are kept. |
| `Check my CPU usage` | Reads a local system metric. Also try `Check RAM`, `List active processes` or `Show computer specifications`. |
| `Open Notepad` | Asks for permission the first time for that app in the session. |
| `Lock my PC` | Requires confirmation every time. |

Approved app targets include Visual Studio Code, Spotify, Calculator, Notepad, Paint, File Explorer and Windows Settings. ORBIT also opens approved Windows folders and its project directory.

## Settings, privacy and diagnostics

ORBIT sends prompts to the configured loopback Ollama server. Speech runs on Windows and saved facts and conversation history live in a plaintext SQLite file in `%LOCALAPPDATA%\ORBIT Desktop`. That folder also holds the rotating diagnostic log. The diagnostic log records timings and errors. Treat the SQLite file as private.

Create an `orbit.toml` file in that profile folder to change the model or response limits. Restart ORBIT after saving.

~~~toml
[ollama]
url = "http://127.0.0.1:11434"
model = "qwen2.5:1.5b"
timeout = 180
max_tokens = 220
~~~

The source ZIP includes **Check_ORBIT.bat** to verify packages, artwork, audio output, SQLite and the selected local model. Kokoro speech can pause between chunks on slower CPUs. If both voice engines fail, open **Read reply** to see the answer.

## Development

See the [developer guide](DEVELOPMENT_GUIDE.md), [contribution guide](CONTRIBUTING.md), [changelog](CHANGELOG.md) and [upstream model sources and licences](MODEL_SOURCES.md).

ORBIT Desktop is released under the [MIT License](LICENSE).
