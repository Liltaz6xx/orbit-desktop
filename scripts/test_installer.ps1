param(
    [Parameter(Mandatory)][string]$Installer,
    [string]$PreviousInstaller
)

$ErrorActionPreference = 'Stop'
$installerPath = (Resolve-Path -LiteralPath $Installer).Path
$previousPath = if ($PreviousInstaller) { (Resolve-Path -LiteralPath $PreviousInstaller).Path } else { $installerPath }
$work = Join-Path ([IO.Path]::GetTempPath()) "ORBIT Installer QA $([guid]::NewGuid().ToString('N'))"
$appDir = Join-Path $work 'Installed copy'
$profile = Join-Path $work 'User profile'
$uninstallKey = 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\{70E68F53-B09E-46C9-ACF6-ECE84F5861C8}_is1'
$versionKey = 'HKCU:\Software\ORBIT Desktop'
$desktop = Join-Path ([Environment]::GetFolderPath('DesktopDirectory')) 'ORBIT Desktop.lnk'
$menu = Join-Path ([Environment]::GetFolderPath('Programs')) 'ORBIT Desktop'
$installedVersion = (Get-ItemProperty -LiteralPath $versionKey -ErrorAction SilentlyContinue).InstallerVersion
if ((Test-Path -LiteralPath $uninstallKey) -or $installedVersion -or
    (Test-Path -LiteralPath $desktop) -or (Test-Path -LiteralPath $menu)) {
    throw 'Use a Windows account without an existing ORBIT Desktop installation or shortcuts.'
}
$windowsLocalAppData = $env:LOCALAPPDATA
$qtPlatform = $env:QT_QPA_PLATFORM
New-Item -ItemType Directory -Path $work | Out-Null

function Invoke-Setup($Path, $Name, [string[]]$Extra = @()) {
    $log = Join-Path $work "$Name.log"
    $arguments = @('/VERYSILENT', '/SUPPRESSMSGBOXES', '/NORESTART', ('/LOG="' + $log + '"')) + $Extra
    $process = Start-Process -FilePath $Path -ArgumentList $arguments -WindowStyle Hidden -Wait -PassThru
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
    $env:LOCALAPPDATA = $profile
    $env:QT_QPA_PLATFORM = 'offscreen'
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

    $dataDir = Join-Path $profile 'ORBIT Desktop'
    $memoryFile = Join-Path $dataDir 'orbit_memory.sqlite3'
    $settingsFile = Join-Path $dataDir 'orbit.toml'
    $memoryHash = (Get-FileHash -LiteralPath $memoryFile).Hash
    $settingsHash = (Get-FileHash -LiteralPath $settingsFile).Hash
    $voice = Join-Path $dataDir 'voice'
    New-Item -ItemType Directory -Path $voice | Out-Null
    $voiceMarker = Join-Path $voice 'voice-test.marker'
    Set-Content -LiteralPath $voiceMarker -Value 'QA voice cache marker'
    # Restore the actual installer environment. The synthetic application profile
    # was used only by the Python process.
    $env:LOCALAPPDATA = $windowsLocalAppData
    $env:QT_QPA_PLATFORM = $qtPlatform

    $upgradeLog = Invoke-Setup $installerPath 'upgrade'
    if ((Get-FileHash -LiteralPath $appFile).Hash -eq $beforeHash) { throw 'Upgrade did not replace the existing files.' }
    if (-not (Select-String -LiteralPath $upgradeLog -Pattern 'Reusing the verified ORBIT runtime' -Quiet)) {
        throw 'Upgrade did not reuse the verified runtime.'
    }
    if (-not (Select-String -LiteralPath $upgradeLog -Pattern 'Reusing installed Ollama model' -Quiet) -or
        -not (Select-String -LiteralPath $upgradeLog -SimpleMatch 'Already present: voices-v1.0.bin' -Quiet)) {
        throw 'Setup did not reuse the provisioned model and voice files.'
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
    $env:LOCALAPPDATA = $profile
    $env:QT_QPA_PLATFORM = 'offscreen'
    Push-Location -LiteralPath $appDir
    try {
        & $python -s -E -B -c "from PySide6.QtCore import QTimer; from PySide6.QtWidgets import QApplication; from orbit.window import OrbitWindow; from orbit.config import load_settings; app=QApplication([]); win=OrbitWindow(load_settings()); win.show(); QTimer.singleShot(400, win.close); app.exec()"
        if ($LASTEXITCODE -ne 0) { throw 'The installed application failed its startup smoke test.' }
    } finally { Pop-Location }
    $env:LOCALAPPDATA = $windowsLocalAppData
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
    Write-Host "Verified fresh install, default shortcuts, in-place upgrade, runtime reuse, startup and uninstall. Logs: $work"
} finally {
    $env:LOCALAPPDATA = $windowsLocalAppData
    $env:QT_QPA_PLATFORM = $qtPlatform
    $uninstall = Join-Path $appDir 'unins000.exe'
    if (Test-Path -LiteralPath $uninstall) {
        $null = Invoke-Setup $uninstall 'cleanup'
    }
}
