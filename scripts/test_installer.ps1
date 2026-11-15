param(
    [Parameter(Mandatory)][string]$Installer,
    [string]$PreviousInstaller
)

$ErrorActionPreference = 'Stop'
$installerPath = (Resolve-Path -LiteralPath $Installer).Path
$previousPath = if ($PreviousInstaller) { (Resolve-Path -LiteralPath $PreviousInstaller).Path } else { $installerPath }
$work = Join-Path ([IO.Path]::GetTempPath()) "ORBIT Installer QA $([guid]::NewGuid().ToString('N'))"
$appDir = Join-Path $work 'Installed copy'
$dataDir = Join-Path $env:LOCALAPPDATA 'ORBIT Desktop'
$uninstallKey = 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\{70E68F53-B09E-46C9-ACF6-ECE84F5861C8}_is1'
$versionKey = 'HKCU:\Software\ORBIT Desktop'
$desktop = Join-Path ([Environment]::GetFolderPath('DesktopDirectory')) 'ORBIT Desktop.lnk'
$menu = Join-Path ([Environment]::GetFolderPath('Programs')) 'ORBIT Desktop'
$installedVersion = (Get-ItemProperty -LiteralPath $versionKey -ErrorAction SilentlyContinue).InstallerVersion
if ((Test-Path -LiteralPath $uninstallKey) -or $installedVersion -or (Test-Path -LiteralPath $dataDir) -or
    (Test-Path -LiteralPath $desktop) -or (Test-Path -LiteralPath $menu)) {
    throw 'Use a Windows account without an existing ORBIT Desktop installation, profile or shortcuts.'
}
$qtPlatform = $env:QT_QPA_PLATFORM
New-Item -ItemType Directory -Path $work | Out-Null

function Invoke-Setup($Path, $Name, [string[]]$Extra = @()) {
    $log = Join-Path $work "$Name.log"
    $arguments = @('/VERYSILENT', '/SUPPRESSMSGBOXES', '/NORESTART', ('/LOG="' + $log + '"')) + $Extra
    $process = Start-Process -FilePath $Path -ArgumentList $arguments -WindowStyle Hidden -PassThru
    # Ollama's tray process remains open after its installer exits. Wait for
    # ORBIT Setup itself so that the running server does not hold this test open.
    if (-not $process.WaitForExit(900000)) {
        if (Test-Path -LiteralPath $log) { Get-Content -LiteralPath $log -Tail 70 }
        throw "$Name did not exit within 15 minutes."
    }
    if ($process.ExitCode -ne 0) {
        if (Test-Path -LiteralPath $log) { Get-Content -LiteralPath $log -Tail 70 }
        throw "$Name failed with exit code $($process.ExitCode)."
    }
    return $log
}

try {
    $freshLog = Invoke-Setup $previousPath 'fresh' @(('/DIR="' + $appDir + '"'))
    if (-not (Test-Path -LiteralPath $desktop)) { throw 'Fresh install did not create the default desktop shortcut.' }
    $startMenu = Join-Path $menu 'ORBIT Desktop.lnk'
    if (-not (Test-Path -LiteralPath $startMenu)) { throw 'No Start menu entry.' }
    $shell = New-Object -ComObject WScript.Shell
    $desktopLink = $shell.CreateShortcut($desktop)
    $startMenuLink = $shell.CreateShortcut($startMenu)
    if ($desktopLink.TargetPath -ne $startMenuLink.TargetPath -or
        -not (Test-Path -LiteralPath $desktopLink.TargetPath) -or
        -not $desktopLink.TargetPath.StartsWith($appDir + '\', [StringComparison]::OrdinalIgnoreCase) -or
        -not $desktopLink.Arguments.Contains("$appDir\main.py")) {
        throw 'Installed shortcuts do not launch the private runtime and application.'
    }

    $appFile = Join-Path $appDir 'main.py'
    Add-Content -LiteralPath $appFile -Value '# QA changed installed program file'
    $beforeHash = (Get-FileHash -LiteralPath $appFile).Hash
    $python = Join-Path (Split-Path -Parent $desktopLink.TargetPath) 'python.exe'
    Push-Location -LiteralPath $appDir
    try {
        $seedProfile = @'
from orbit.config import CONFIG_PATH, DATABASE_PATH, PROFILE_DIR
from orbit.memory import MemoryStore
PROFILE_DIR.mkdir(parents=True, exist_ok=True)
CONFIG_PATH.write_text('[ollama]\nmodel = "qwen2.5:1.5b"\n', encoding="utf-8")
MemoryStore(DATABASE_PATH).save_memory("The upgrade preserves this memory")
'@
        $seedProfile | & $python -s -E -B -
        if ($LASTEXITCODE -ne 0) { throw 'Could not create the QA profile.' }
    } finally { Pop-Location }

    $memoryFile = Join-Path $dataDir 'orbit_memory.sqlite3'
    $settingsFile = Join-Path $dataDir 'orbit.toml'
    $memoryHash = (Get-FileHash -LiteralPath $memoryFile).Hash
    $settingsHash = (Get-FileHash -LiteralPath $settingsFile).Hash
    $voice = Join-Path $dataDir 'voice'
    New-Item -ItemType Directory -Path $voice -Force | Out-Null
    $voiceMarker = Join-Path $voice 'voice-test.marker'
    Set-Content -LiteralPath $voiceMarker -Value 'QA voice cache marker'
    $upgradeLog = Invoke-Setup $installerPath 'upgrade'
    if ((Get-FileHash -LiteralPath $appFile).Hash -eq $beforeHash) { throw 'Upgrade did not replace the existing files.' }
    if (-not (Select-String -LiteralPath $upgradeLog -Pattern 'Reusing the verified ORBIT runtime' -Quiet)) {
        throw 'Upgrade did not reuse the verified runtime.'
    }
    if (-not (Select-String -LiteralPath $upgradeLog -Pattern 'Reusing installed Ollama model' -Quiet) -or
        -not (Select-String -LiteralPath $upgradeLog -SimpleMatch 'Already present: voices-v1.0.bin' -Quiet)) {
        throw 'Setup did not reuse the provisioned language model and voice library.'
    }
    if (-not $PreviousInstaller -and
        -not (Select-String -LiteralPath $upgradeLog -SimpleMatch 'Already present: kokoro-v1.0.onnx' -Quiet)) {
        throw 'Setup did not reuse the provisioned Kokoro model.'
    }
    if (-not $PreviousInstaller -and
        -not (Select-String -LiteralPath $freshLog -Pattern 'Kokoro voice assets are ready' -Quiet)) {
        throw 'Fresh install did not provision the Kokoro voice.'
    }
    $desktopLink = $shell.CreateShortcut($desktop)
    $python = Join-Path (Split-Path -Parent $desktopLink.TargetPath) 'python.exe'
    if (-not (Test-Path -LiteralPath $voiceMarker) -or (Get-FileHash -LiteralPath $memoryFile).Hash -ne $memoryHash -or
        (Get-FileHash -LiteralPath $settingsFile).Hash -ne $settingsHash) {
        throw 'Upgrade changed the user profile.'
    }
    $env:QT_QPA_PLATFORM = 'offscreen'
    Push-Location -LiteralPath $appDir
    try {
        $smoke = @'
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication
from orbit.artifacts import Artifact, Slide, write_document, write_presentation
from orbit.config import VOICE_MODEL, load_settings, voice_files
from orbit.voice import OrbitVoice
from orbit.window import OrbitWindow
from io import BytesIO

if voice_files()[0].name != VOICE_MODEL:
    raise SystemExit("Setup did not install the new Kokoro model.")
samples, rate = OrbitVoice().synthesize("ORBIT is ready.")
if not len(samples) or rate != 24000:
    raise SystemExit("The installed Kokoro voice did not produce 24 kHz audio.")
app = QApplication([])
win = OrbitWindow(load_settings())
win.show()
if not win.visual.aurora.isValid():
    raise SystemExit("Setup did not install the animated orb background.")
for draft, writer in (
    (Artifact("word", "Installer smoke test", body="Example text."), write_document),
    (Artifact("presentation", "Installer smoke test", slides=(Slide("Example", ("Example point.",)),)), write_presentation),
):
    output = BytesIO()
    writer(draft, output)
    if not output.getvalue().startswith(b"PK"):
        raise SystemExit("The installed Office exporter did not produce a file.")
win.show_history()
win.history_dialog.reject()
win.show_macros()
win.macro_dialog.close()
if win.history_dialog is not None or win.macro_dialog is not None or not win.entry.isEnabled():
    raise SystemExit("The installed workspace did not close its local tools cleanly.")
QTimer.singleShot(400, win.close)
raise SystemExit(app.exec())
'@
        $smoke | & $python -s -E -B -
        if ($LASTEXITCODE -ne 0) { throw 'The installed application failed its startup smoke test.' }
    } finally { Pop-Location }
    $env:QT_QPA_PLATFORM = $qtPlatform

    $uninstall = Join-Path $appDir 'unins000.exe'
    $null = Invoke-Setup $uninstall 'uninstall'
    if ((Test-Path -LiteralPath $appFile) -or (Test-Path -LiteralPath $desktop) -or
        (Test-Path -LiteralPath $startMenu) -or (Test-Path -LiteralPath (Join-Path $appDir 'runtime'))) {
        throw 'Uninstall left application files, runtime or shortcuts.'
    }
    if (-not (Test-Path -LiteralPath $memoryFile) -or -not (Test-Path -LiteralPath $voiceMarker) -or
        (Get-FileHash -LiteralPath $settingsFile).Hash -ne $settingsHash) {
        throw 'Uninstall removed or changed the user profile.'
    }
    Write-Host "Verified fresh install, default shortcuts, in-place upgrade, dependency reuse, Kokoro synthesis, startup and uninstall. Logs: $work"
} finally {
    $env:QT_QPA_PLATFORM = $qtPlatform
    $uninstall = Join-Path $appDir 'unins000.exe'
    if ((Test-Path -LiteralPath $uninstallKey) -and (Test-Path -LiteralPath $uninstall)) {
        $null = Invoke-Setup $uninstall 'cleanup'
    }
}
