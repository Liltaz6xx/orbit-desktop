"""Build a Windows source ZIP from the exact files in the current commit."""

import argparse
import hashlib
import re
import subprocess
import tomllib
from pathlib import Path, PurePosixPath
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

ROOT = Path(__file__).resolve().parent.parent
ROOT_FILES = {
    "main.py", "requirements.txt", "Setup_ORBIT.bat", "Run_ORBIT.bat", "Check_ORBIT.bat",
    "README.md", "CHANGELOG.md", "CONTRIBUTING.md", "DEVELOPMENT_GUIDE.md",
    "MODEL_SOURCES.md", "RELEASE_NOTES.md", "LICENSE", "orbit.example.toml",
}
ASSETS = {"assets/orbit.ico", "assets/orbit_core.png", "assets/orbit_halo.png", "assets/orbit_aurora.gif",
          "assets/preview.jpg", "assets/VOICE_ASSETS.txt"}
SCRIPTS = {"scripts/setup.ps1", "scripts/download_voice_models.ps1", "scripts/check_environment.py"}


def git(*args):
    return subprocess.check_output(("git", *args), cwd=ROOT)


def include_file(name):
    path = PurePosixPath(name)
    return (name in ROOT_FILES or name in ASSETS or name in SCRIPTS
            or (path.parent == PurePosixPath("orbit") and path.suffix == ".py"))


def build(tag, output):
    commit = git("rev-parse", "--verify", "HEAD").decode("ascii").strip()
    source = git("show", f"{commit}:orbit/__init__.py").decode("utf-8")
    match = re.search(r'^__version__ = "([^"]+)"$', source, flags=re.M)
    if not match or not re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+(?:-[A-Za-z0-9.]+)?", match[1]):
        raise ValueError("The committed ORBIT version is missing or invalid.")
    version = match[1]
    if tag and tag != f"v{version}":
        raise ValueError(f"Tag {tag} does not match committed version v{version}.")

    listed = git("ls-tree", "-rz", commit).decode("utf-8").split("\0")
    paths = {}
    for entry in filter(None, listed):
        metadata, name = entry.split("\t", 1)
        mode, object_type, object_id = metadata.split()
        if include_file(name):
            if object_type != "blob" or mode not in {"100644", "100755"}:
                raise ValueError(f"Unsupported release entry {name}")
            paths[name] = object_id
    required = ROOT_FILES | ASSETS | SCRIPTS | {"orbit/__init__.py"}
    if missing := required - paths.keys():
        raise ValueError(f"Release is missing {', '.join(sorted(missing))}")

    settings = tomllib.loads(git("cat-file", "blob", paths["orbit.example.toml"]).decode("utf-8"))
    if "ollama" not in settings:
        raise ValueError("The committed example settings are invalid.")

    folder = f"ORBIT-Desktop-{version}"
    output.mkdir(parents=True, exist_ok=True)
    path = output / f"{folder}-Windows.zip"
    with ZipFile(path, "w", ZIP_DEFLATED) as archive:
        for name, object_id in sorted(paths.items()):
            content = git("cat-file", "blob", object_id)
            if PurePosixPath(name).suffix in {".bat", ".ps1"}:
                content = content.replace(b"\r\n", b"\n").replace(b"\n", b"\r\n")
            info = ZipInfo(f"{folder}/{name}")
            info.compress_type = ZIP_DEFLATED
            archive.writestr(info, content)

    checksum = hashlib.sha256(path.read_bytes()).hexdigest()
    path.with_suffix(".zip.sha256").write_text(f"{checksum}  {path.name}\n", encoding="ascii")
    return path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tag", help="Verify the release tag against the committed app version.")
    parser.add_argument("--output", type=Path, default=ROOT / "dist")
    args = parser.parse_args()
    try:
        archive = build(args.tag, args.output)
    except (ValueError, OSError, subprocess.CalledProcessError) as exc:
        parser.exit(1, f"Release build failed: {exc}\n")
    print(archive)


if __name__ == "__main__":
    main()
