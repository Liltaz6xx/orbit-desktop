"""On-device wake phrase and dictation through Windows System.Speech."""

import base64
import json
import os

from PySide6.QtCore import QProcess, QObject, Signal

RECOGNIZE = r"""
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [Text.UTF8Encoding]::new($false)
try {
    Add-Type -AssemblyName System.Speech
    $culture = [System.Speech.Recognition.SpeechRecognitionEngine]::InstalledRecognizers() |
        Where-Object { $_.Culture.TwoLetterISOLanguageName -eq 'en' } |
        Sort-Object { $_.Culture.Name -ne [Globalization.CultureInfo]::CurrentUICulture.Name } |
        Select-Object -First 1
    if ($null -eq $culture) { [Console]::WriteLine('NO_ENGLISH'); exit 1 }
    $engine = [System.Speech.Recognition.SpeechRecognitionEngine]::new($culture)
    try {
        $builder = [System.Speech.Recognition.GrammarBuilder]::new()
        $builder.Culture = $culture.Culture
        $builder.Append('Hey ' + $env:ORBIT_WAKE_NAME)
        $wake = [System.Speech.Recognition.Grammar]::new($builder)
        $dictation = [System.Speech.Recognition.DictationGrammar]::new()
        $dictation.Enabled = $false
        $engine.LoadGrammar($wake)
        $engine.LoadGrammar($dictation)
        $engine.SetInputToDefaultAudioDevice()
        [Console]::WriteLine('READY')
        while ($true) {
            $engine.InitialSilenceTimeout = [TimeSpan]::FromSeconds(12)
            $heard = $engine.Recognize()
            if ($null -eq $heard -or $heard.Confidence -lt 0.7) { continue }
            [Console]::WriteLine('WAKE')
            $wake.Enabled = $false
            $dictation.Enabled = $true
            $engine.InitialSilenceTimeout = [TimeSpan]::FromSeconds(7)
            $command = $engine.Recognize()
            $dictation.Enabled = $false
            $wake.Enabled = $true
            if ($null -ne $command -and $command.Confidence -ge 0.4 -and $command.Text.Trim()) {
                [Console]::WriteLine('TEXT ' + (ConvertTo-Json -InputObject $command.Text -Compress))
                break
            }
            [Console]::WriteLine('READY')
        }
    } finally { $engine.Dispose() }
} catch { [Console]::WriteLine('FAILED'); exit 1 }
"""


class VoiceListener(QObject):
    status = Signal(str)
    heard = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.process = QProcess(self)
        self.process.readyReadStandardOutput.connect(self.receive)
        self.process.finished.connect(self.finished)
        self.process.errorOccurred.connect(self.process_error)
        self.buffer = bytearray()
        self.active = False
        self.delivered = False
        self.reported_error = False
        self.name = ""

    def start(self, name):
        if self.process.state() != QProcess.ProcessState.NotRunning:
            return
        self.active = True
        self.name = name
        self.delivered = self.reported_error = False
        self.buffer.clear()
        path = os.path.join(os.environ.get("SystemRoot", r"C:\Windows"), "System32",
                            "WindowsPowerShell", "v1.0", "powershell.exe")
        environment = self.process.processEnvironment()
        if environment.isEmpty():
            from PySide6.QtCore import QProcessEnvironment
            environment = QProcessEnvironment.systemEnvironment()
        environment.insert("ORBIT_WAKE_NAME", name)
        self.process.setProcessEnvironment(environment)
        encoded = base64.b64encode(RECOGNIZE.encode("utf-16le")).decode("ascii")
        self.status.emit("Starting the microphone…")
        self.process.start(path, ["-NoProfile", "-NonInteractive", "-WindowStyle", "Hidden",
                                  "-EncodedCommand", encoded], QProcess.OpenModeFlag.ReadOnly)

    def stop(self):
        self.active = False
        if self.process.state() != QProcess.ProcessState.NotRunning:
            self.process.kill()
            self.process.waitForFinished(1000)

    def receive(self):
        self.buffer.extend(bytes(self.process.readAllStandardOutput()))
        while self.buffer and b"\n" in self.buffer:
            line, _, self.buffer = self.buffer.partition(b"\n")
            line = line.decode("utf-8", errors="replace").strip().lstrip("\ufeff")
            if not self.active:
                continue
            if line == "READY":
                self.status.emit(f"Microphone on · say “Hey {self.name}”")
            elif line == "WAKE":
                self.status.emit("Listening for your request…")
            elif line.startswith("TEXT ") and not self.delivered:
                try:
                    message = json.loads(line[5:])
                except ValueError:
                    continue
                if isinstance(message, str) and message.strip():
                    self.delivered = True
                    self.heard.emit(message[:2000])
            elif line == "NO_ENGLISH":
                self.reported_error = True
                self.status.emit("Install an English Windows Speech recognition language to use the microphone.")
            elif line == "FAILED":
                self.reported_error = True
                self.status.emit("Microphone unavailable. Check Windows microphone access and the default input.")

    def finished(self, _code, _status):
        self.receive()
        if self.active and not (self.delivered or self.reported_error):
            self.status.emit("Windows speech recognition stopped. Check your microphone and try again.")

    def process_error(self, error):
        if self.active and error == QProcess.ProcessError.FailedToStart:
            self.status.emit("Windows speech recognition could not start.")
