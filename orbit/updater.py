"""Find and verify ORBIT Desktop installers from its GitHub releases."""

import base64
import hashlib
import json
import os
import re
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from urllib.request import Request, urlopen

REPOSITORY = "Liltaz6xx/orbit-desktop"
LATEST = f"https://api.github.com/repos/{REPOSITORY}/releases/latest"
RELEASE_PAGE = f"https://github.com/{REPOSITORY}/releases/latest"
MAX_INSTALLER_BYTES = 256 * 1024 * 1024


@dataclass(frozen=True)
class Update:
    version: str
    filename: str
    url: str
    digest: str
    size: int


def version_key(version):
    match = re.fullmatch(r"(\d{1,5})\.(\d{1,5})\.(\d{1,5})(?:-beta\.(\d{1,5}))?", version)
    if not match:
        raise ValueError("GitHub returned an unsupported ORBIT version.")
    return tuple(map(int, match.groups()[:3])) + (int(match[4]) if match[4] else 65535,)


def installed_copy(root):
    import sys

    if sys.platform != "win32":
        return False
    import winreg

    key = r"Software\Microsoft\Windows\CurrentVersion\Uninstall\{70E68F53-B09E-46C9-ACF6-ECE84F5861C8}_is1"
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key) as entry:
            location, _ = winreg.QueryValueEx(entry, "InstallLocation")
        return bool(location) and Path(location).resolve() == root.resolve()
    except OSError:
        return False


def latest_update(current):
    request = Request(LATEST, headers={"Accept": "application/vnd.github+json", "User-Agent": "ORBIT-Desktop"})
    with urlopen(request, timeout=12) as response:
        release = json.loads(response.read(1024 * 1024))
    if release.get("draft") or release.get("prerelease"):
        raise ValueError("GitHub did not return a published release.")
    tag = release["tag_name"]
    if not tag.startswith("v"):
        raise ValueError("GitHub returned an unsupported ORBIT tag.")
    version = tag[1:]
    if version_key(version) <= version_key(current):
        return None
    filename = f"ORBIT-Desktop-{version}-Windows-x64-Setup.exe"
    url = f"https://github.com/{REPOSITORY}/releases/download/{tag}/{filename}"
    for asset in release["assets"]:
        if asset.get("name") != filename or asset.get("browser_download_url") != url:
            continue
        digest = asset.get("digest") or ""
        size = asset.get("size")
        if re.fullmatch(r"sha256:[a-f0-9]{64}", digest) and type(size) is int and 0 < size <= MAX_INSTALLER_BYTES:
            return Update(version, filename, url, digest[7:], size)
    raise ValueError("The latest release has no Windows installer with a valid checksum.")


def download_update(update, cancelled):
    folder = Path(tempfile.mkdtemp(prefix="orbit-update-"))
    installer = folder / update.filename
    try:
        digest = hashlib.sha256()
        size = 0
        request = Request(update.url, headers={"User-Agent": "ORBIT-Desktop"})
        with urlopen(request, timeout=20) as response, installer.open("xb") as file:
            if not response.geturl().startswith("https://"):
                raise ValueError("The update download did not use HTTPS.")
            while not cancelled.is_set():
                chunk = response.read(256 * 1024)
                if not chunk:
                    break
                size += len(chunk)
                if size > update.size:
                    raise ValueError("The installer is larger than expected.")
                digest.update(chunk)
                file.write(chunk)
        if cancelled.is_set():
            raise InterruptedError("Update download cancelled.")
        if size != update.size or digest.hexdigest() != update.digest:
            raise ValueError("The installer checksum did not match. Try again.")
        return installer
    except BaseException:
        installer.unlink(missing_ok=True)
        folder.rmdir()
        raise


def launch_after_exit(installer):
    root = Path(os.environ.get("SystemRoot", r"C:\Windows"))
    powershell = root / "System32/WindowsPowerShell/v1.0/powershell.exe"
    environment = dict(os.environ, ORBIT_UPDATE_EXE=str(installer), ORBIT_UPDATE_PID=str(os.getpid()))
    script = """
$ErrorActionPreference = 'Stop'
$exe = $env:ORBIT_UPDATE_EXE
try {
    $parent = Get-Process -Id ([int]$env:ORBIT_UPDATE_PID) -ErrorAction SilentlyContinue
    if ($parent -and -not $parent.WaitForExit(30000)) { throw 'ORBIT is still open.' }
    $setup = Start-Process -FilePath $exe -ArgumentList '/SILENT /NORESTART /ORBITUPDATE' -PassThru
    $setup.WaitForExit()
} catch {
    Add-Type -AssemblyName System.Windows.Forms
    [void][Windows.Forms.MessageBox]::Show('Could not start the update. Open ORBIT and try again.', 'ORBIT update')
} finally {
    Remove-Item -LiteralPath $exe -Force -ErrorAction SilentlyContinue
    Remove-Item -LiteralPath (Split-Path -Parent $exe) -ErrorAction SilentlyContinue
}
"""
    encoded = base64.b64encode(script.encode("utf-16le")).decode("ascii")
    subprocess.Popen([str(powershell), "-NoProfile", "-NonInteractive", "-EncodedCommand", encoded],
                     env=environment, creationflags=subprocess.CREATE_NO_WINDOW)
