"""Where things live on disk, for source runs and PyInstaller builds on Windows/macOS/Linux."""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path

APP_DIR_NAME = "VideoMetadataReporter"          # per-user config folder name
DOCUMENTS_EXPORT_NAME = "Video Metadata Reporter"  # fallback export folder under ~/Documents


def app_dir() -> Path:
    """The folder the user launched the app from.

    - From source: the project folder (parent of the mediareport package).
    - Frozen (PyInstaller): the folder holding the executable; on macOS the
      folder *containing* the .app bundle, never inside it.
    """
    if getattr(sys, "frozen", False):
        exe = Path(sys.executable).resolve()
        for parent in exe.parents:
            if parent.suffix == ".app":
                return parent.parent
        return exe.parent
    return Path(__file__).resolve().parent.parent


def vendored_mediainfo() -> Path | None:
    """The MediaInfo.dll shipped in vendor/mediainfo, or None (pymediainfo's bundled copy is used then).

    From source it sits in the project folder; in a PyInstaller build it is under the bundle root.
    """
    if sys.platform != "win32":
        return None
    root = Path(getattr(sys, "_MEIPASS", "")) if getattr(sys, "frozen", False) else app_dir()
    dll = root / "vendor" / "mediainfo" / "MediaInfo.dll"
    return dll if dll.is_file() else None


def is_writable_dir(path: Path) -> bool:
    """True if path exists (or can be created) and a file can be written in it."""
    try:
        path.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryFile(dir=path):
            pass
        return True
    except OSError:
        return False


def user_config_dir() -> Path:
    if sys.platform == "win32":
        base = os.environ.get("APPDATA") or str(Path.home() / "AppData" / "Roaming")
        return Path(base) / APP_DIR_NAME
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / APP_DIR_NAME
    base = os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
    return Path(base) / APP_DIR_NAME


def documents_export_dir() -> Path:
    return Path.home() / "Documents" / DOCUMENTS_EXPORT_NAME


def resolve_export_dir(configured: str) -> tuple[Path, str | None]:
    """Turn the configured export folder into a usable path.

    Empty -> <app folder>/export. Relative -> relative to the app folder.
    If that folder can't be written, fall back to ~/Documents/Video Metadata Reporter.
    Returns (path, note) where note explains a fallback, else None.
    """
    configured = (configured or "").strip()
    wanted = Path(os.path.expandvars(os.path.expanduser(configured))) if configured else Path("export")
    if not wanted.is_absolute():
        wanted = app_dir() / wanted
    if is_writable_dir(wanted):
        return wanted, None
    fallback = documents_export_dir()
    return fallback, f"Can't write to {wanted}; saving to {fallback} instead."


def open_path(path: str | os.PathLike) -> None:
    """Open a file or folder with the OS default handler."""
    path = str(path)
    if sys.platform == "win32":
        os.startfile(path)  # noqa: S606
    elif sys.platform == "darwin":
        subprocess.Popen(["open", path])
    else:
        subprocess.Popen(["xdg-open", path])
