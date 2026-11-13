# ORBIT Desktop

**A voice-first AI assistant for Windows 11.** Type a request and hear ORBIT’s reply in a British voice. The orb animates as ORBIT thinks, speaks and runs approved Windows actions.

![ORBIT's illuminated orbital core against a near-black background](assets/preview.jpg)

Created by [Liltaz6xx](https://github.com/Liltaz6xx). ORBIT calls the operator of each installation **Maker**.

## Install the Windows beta

1. Download the Windows ZIP from [GitHub Releases](https://github.com/Liltaz6xx/orbit-desktop/releases) and extract it. A clone of the repository works too.
2. Install 64-bit Python 3.12 and start Ollama for Windows. [Python downloads](https://www.python.org/downloads/windows/) · [Ollama downloads](https://ollama.com/download/windows)
3. Double-click **Setup_ORBIT.bat** to install dependencies into a virtual environment. Choose whether to download the Kokoro voice assets. ORBIT can use Windows speech if the voice assets are missing.
4. In PowerShell, install the default local language model. [Model page](https://ollama.com/library/qwen2.5:1.5b)

   ~~~powershell
   ollama pull qwen2.5:1.5b
   ~~~

5. Double-click **Run_ORBIT.bat**. Press **Enter** to send, **Esc** to stop, or **Read reply** to open the latest answer.

The ZIP contains editable source and Windows launchers. The models and Python dependencies are installed separately.

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

Run **Check_ORBIT.bat** to verify packages, artwork, audio output, SQLite and the selected local model. Kokoro speech can pause between chunks on slower CPUs. If both voice engines fail, open **Read reply** to see the answer.

## Development

See the [developer guide](DEVELOPMENT_GUIDE.md), [contribution guide](CONTRIBUTING.md), [changelog](CHANGELOG.md) and [upstream model sources and licences](MODEL_SOURCES.md).

ORBIT Desktop is released under the [MIT License](LICENSE).
