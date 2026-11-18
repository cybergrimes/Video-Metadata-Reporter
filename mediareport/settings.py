"""User options, persisted as JSON in %APPDATA%\\MediaReport\\settings.json."""
from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field, fields
from datetime import datetime
from pathlib import Path

from .core import DEFAULT_EXTRAS_FOLDERS

PROJECT_DIR = Path(__file__).resolve().parent.parent
DEFAULT_EXPORT_DIR = PROJECT_DIR / "export"


def settings_path() -> Path:
    base = os.environ.get("APPDATA") or str(Path.home() / ".config")
    return Path(base) / "MediaReport" / "settings.json"


@dataclass
class Options:
    folders: list[str] = field(default_factory=list)
    output_dir: str = str(DEFAULT_EXPORT_DIR)
    max_audio: int = 0
    max_subs: int = 0
    extras_folders: list[str] = field(default_factory=lambda: list(DEFAULT_EXTRAS_FOLDERS))
    workers: int = 4

    def report_path(self, now: datetime | None = None) -> Path:
        stamp = (now or datetime.now()).strftime("%Y-%m-%d_%H%M")
        return Path(self.output_dir or DEFAULT_EXPORT_DIR) / f"Media Report {stamp}.xlsx"


def load(path: Path | None = None) -> Options:
    """Load settings; missing/corrupt file or unknown keys fall back to defaults."""
    path = path or settings_path()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return Options()
    if not isinstance(data, dict):
        return Options()
    opts = Options()
    for f in fields(Options):
        if f.name not in data:
            continue
        default = getattr(opts, f.name)
        value = data[f.name]
        if isinstance(default, list) and isinstance(value, list):
            setattr(opts, f.name, [str(v) for v in value])
        elif isinstance(default, int) and isinstance(value, int) and not isinstance(value, bool):
            setattr(opts, f.name, max(0, value))
        elif isinstance(default, str) and isinstance(value, str):
            setattr(opts, f.name, value)
    opts.workers = max(1, opts.workers)
    return opts


def save(opts: Options, path: Path | None = None) -> None:
    path = path or settings_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(asdict(opts), indent=2), encoding="utf-8")
    os.replace(tmp, path)
