"""User options, stored in a hand-editable MediaReport.ini.

Location: next to the app (portable) if that folder is writable or already has
the file; otherwise the per-OS user config folder (see paths.user_config_dir).
"""
from __future__ import annotations

import configparser
import os
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from .core import DEFAULT_EXTRAS_FOLDERS, parse_extras
from .paths import app_dir, is_writable_dir, resolve_export_dir, user_config_dir

INI_NAME = "MediaReport.ini"
SECTION = "Media Report"
MAX_WORKERS = 32


@dataclass
class Options:
    folders: list[str] = field(default_factory=list)
    export_folder: str = ""          # "" = 'export' next to the app; relative = relative to the app
    max_audio: int = 0
    max_subs: int = 0
    split_tracks: bool = False
    extras_folders: list[str] = field(default_factory=lambda: list(DEFAULT_EXTRAS_FOLDERS))
    workers: int = 4

    def export_dir(self) -> tuple[Path, str | None]:
        """(folder to write reports to, note if we had to fall back)."""
        return resolve_export_dir(self.export_folder)

    def report_name(self, now: datetime | None = None) -> str:
        return f"Media Report {(now or datetime.now()).strftime('%Y-%m-%d_%H%M')}.xlsx"


def settings_path() -> Path:
    portable = app_dir() / INI_NAME
    if portable.exists() or is_writable_dir(portable.parent):
        return portable
    return user_config_dir() / INI_NAME


# --------------------------------------------------------------------------- load

def _int(cp: configparser.ConfigParser, key: str, default: int, minimum: int = 0) -> int:
    try:
        return max(minimum, cp.getint(SECTION, key, fallback=default))
    except ValueError:
        return default


def _lines(value: str) -> list[str]:
    return [line.strip() for line in value.splitlines() if line.strip()]


def load(path: Path | None = None) -> Options:
    """Load settings; a missing/unreadable file or bad values fall back to defaults."""
    path = path or settings_path()
    opts = Options()
    cp = configparser.ConfigParser(interpolation=None)
    try:
        cp.read(path, encoding="utf-8")
    except (OSError, configparser.Error, UnicodeDecodeError):
        return opts
    if not cp.has_section(SECTION):
        return opts

    s = cp[SECTION]
    if "folders" in s:
        opts.folders = _lines(s["folders"])
    opts.export_folder = s.get("export_folder", opts.export_folder).strip()
    opts.max_audio = _int(cp, "max_audio", opts.max_audio)
    opts.max_subs = _int(cp, "max_subs", opts.max_subs)
    try:
        opts.split_tracks = cp.getboolean(SECTION, "split_tracks", fallback=opts.split_tracks)
    except ValueError:
        pass
    opts.workers = min(MAX_WORKERS, _int(cp, "workers", opts.workers, minimum=1))
    if "extras_folders" in s:
        opts.extras_folders = parse_extras(s["extras_folders"])
    return opts


# --------------------------------------------------------------------------- save

TEMPLATE = """\
; Media Report settings. Safe to edit by hand while the app is closed.
; Lines starting with ; are comments.

[{section}]
; Folders to scan, one per line (indent each line under 'folders =').
folders ={folders}

; Where reports are saved. Leave empty for the 'export' folder next to the app.
; A relative path is relative to the app folder.
export_folder = {export_folder}

; Maximum Audio N / Sub N columns in the report (0 = as many as needed).
max_audio = {max_audio}
max_subs = {max_subs}

; Put each audio/subtitle detail in its own column (Audio 1 Language, Audio 1 Type, ...)
; instead of one combined cell per track. yes or no.
split_tracks = {split_tracks}

; Folder names (comma-separated, any case) that mark bonus content in the Type column.
extras_folders = {extras_folders}

; Files to read at the same time. Lower this for slow network drives.
workers = {workers}
"""


def render(opts: Options) -> str:
    folders = "".join(f"\n    {f}" for f in opts.folders)
    return TEMPLATE.format(
        section=SECTION,
        folders=folders,
        export_folder=opts.export_folder,
        max_audio=max(0, opts.max_audio),
        max_subs=max(0, opts.max_subs),
        split_tracks="yes" if opts.split_tracks else "no",
        extras_folders=", ".join(opts.extras_folders),
        workers=max(1, opts.workers),
    )


def save(opts: Options, path: Path | None = None) -> Path:
    """Write settings atomically. Returns the path written."""
    path = path or settings_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    try:
        tmp.write_text(render(opts), encoding="utf-8")
        os.replace(tmp, path)
    finally:
        if tmp.exists():
            tmp.unlink()
    return path
