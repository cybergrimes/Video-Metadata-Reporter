"""Pure scanning logic: find video files and turn MediaInfo tracks into a FileRecord.

Nothing in here knows about Excel, threads or the GUI.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Iterable

VIDEO_EXTS = {".mkv", ".mp4", ".m4v", ".avi", ".mov", ".ts", ".m2ts", ".wmv", ".mpg", ".mpeg", ".webm"}

# Folder names (case-insensitive) that mark bonus content.
DEFAULT_EXTRAS_FOLDERS = ("extras", "featurettes", "scenes")

# Fixed columns, in output order. Audio N / Sub N columns follow these.
BASE_COLUMNS = [
    "Folder", "File", "Type", "Container", "Size (GB)", "Duration (min)",
    "Video Codec", "Resolution", "Aspect", "Frame Rate", "Bit Depth", "HDR",
    "Video Bitrate", "# Audio", "# Subs",
]

# Per-track columns used when tracks are split into separate fields
# ("Audio 1 Language", "Audio 1 Type", ...). Order matters.
AUDIO_FIELDS = ["Language", "Type", "Channels", "Bitrate", "Name", "Default"]
SUB_FIELDS = ["Language", "Type", "Name", "Forced", "Default"]


@dataclass
class FileRecord:
    folder: str
    file: str
    type: str = "Main"
    container: str | None = None
    size_gb: float | None = None
    duration_min: int | None = None
    video_codec: str = ""
    resolution: str = ""
    aspect: str | None = None
    frame_rate: str | None = None
    bit_depth: object = None
    hdr: str = ""
    video_bitrate: str = ""
    audio: list[str] = field(default_factory=list)
    subs: list[str] = field(default_factory=list)
    # Same tracks as audio/subs, one value per AUDIO_FIELDS / SUB_FIELDS entry.
    audio_split: list[list[str]] = field(default_factory=list)
    subs_split: list[list[str]] = field(default_factory=list)

    def base_values(self) -> list:
        """Values for BASE_COLUMNS, in order."""
        return [
            self.folder, self.file, self.type, self.container, self.size_gb,
            self.duration_min, self.video_codec, self.resolution, self.aspect,
            self.frame_rate, self.bit_depth, self.hdr, self.video_bitrate,
            len(self.audio), len(self.subs),
        ]


@dataclass
class ScanError:
    path: str
    message: str


# --------------------------------------------------------------------------- files

def find_files(folders: Iterable[str | os.PathLike],
               should_stop: Callable[[], bool] | None = None) -> list[Path]:
    """All video files under the given folders (recursive), sorted, de-duplicated.

    should_stop is checked once per directory; when it returns True the walk
    stops early and returns what was found so far.
    """
    files: set[Path] = set()
    for folder in folders:
        for root, _, names in os.walk(folder):
            if should_stop and should_stop():
                return sorted(files)
            files.update(Path(root) / n for n in names if Path(n).suffix.lower() in VIDEO_EXTS)
    return sorted(files)


def content_type(path: Path, extras_folders: Iterable[str] = DEFAULT_EXTRAS_FOLDERS) -> str:
    """'Extras' / 'Featurettes' / 'Scenes' if any parent folder matches (nearest wins), else 'Main'."""
    wanted = {e.strip().lower() for e in extras_folders if e.strip()}
    for part in reversed(path.parent.parts):
        if part.lower() in wanted:
            return part.title()
    return "Main"


# --------------------------------------------------------------------------- track helpers

def g(track, attr):
    """Safe attribute getter."""
    return getattr(track, attr, None) if track is not None else None


def lang(track) -> str:
    other = g(track, "other_language")
    if other:
        return other[0]          # e.g. "English"
    return g(track, "language") or "und"


def channels(track) -> str:
    ch = g(track, "channel_s")
    try:
        ch = int(str(ch).split()[0])
    except (TypeError, ValueError):
        return ""
    layout = (g(track, "channel_layout") or "").upper()
    lfe = 1 if "LFE" in layout else 0
    if ch >= 3 and not lfe and ch in (6, 8):  # layout missing; assume .1
        lfe = 1
    return f"{ch - lfe}.{lfe}"


def kbps(value) -> str:
    try:
        return f"{round(int(float(str(value).split()[0])) / 1000):,} kb/s"
    except (TypeError, ValueError):
        return ""


def yes(v) -> bool:
    return str(v).lower() in ("yes", "true", "1")


def audio_fields(t) -> list[str]:
    """One value per AUDIO_FIELDS entry."""
    return [
        lang(t),
        g(t, "commercial_name") or g(t, "format") or "?",
        channels(t),
        kbps(g(t, "bit_rate")),
        g(t, "title") or "",
        "Default" if yes(g(t, "default")) else "",
    ]


def describe_audio(t) -> str:
    lang_, codec, ch, rate, title, default = audio_fields(t)
    parts = [lang_, codec, ch, rate]
    if title:
        parts.append(f'"{title}"')
    if default:
        parts.append(default)
    return " | ".join(p for p in parts if p)


SUB_FORMATS = {"PGS": "PGS", "UTF-8": "SRT", "VobSub": "VobSub", "ASS": "ASS"}


def sub_fields(t) -> list[str]:
    """One value per SUB_FIELDS entry."""
    fmt = g(t, "format") or "?"
    return [
        lang(t),
        SUB_FORMATS.get(fmt, fmt),
        g(t, "title") or "",
        "Forced" if yes(g(t, "forced")) else "",
        "Default" if yes(g(t, "default")) else "",
    ]


def describe_sub(t) -> str:
    lang_, fmt, title, forced, default = sub_fields(t)
    parts = [lang_, fmt]
    if title:
        parts.append(f'"{title}"')
    if forced:
        parts.append(forced)
    if default:
        parts.append(default)
    return " | ".join(p for p in parts if p)


def hdr(v) -> str:
    fmt = g(v, "hdr_format") or ""
    compat = g(v, "hdr_format_compatibility") or ""
    if "Dolby Vision" in fmt:
        return "Dolby Vision" + (" + HDR10" if "HDR10" in compat else "")
    if "2094" in fmt or "HDR10+" in compat:
        return "HDR10+"
    if fmt or "HDR10" in compat:
        return "HDR10"
    if (g(v, "transfer_characteristics") or "") == "HLG":
        return "HLG"
    return "SDR"


# --------------------------------------------------------------------------- record building

def record_from_tracks(path: Path, tracks, extras_folders: Iterable[str] = DEFAULT_EXTRAS_FOLDERS) -> FileRecord:
    """Build a FileRecord from a list of MediaInfo-like track objects (testable without MediaInfo)."""
    gen = next((t for t in tracks if t.track_type == "General"), None)
    vids = [t for t in tracks if t.track_type == "Video"]
    auds = [t for t in tracks if t.track_type == "Audio"]
    subs = [t for t in tracks if t.track_type == "Text"]
    v = vids[0] if vids else None

    try:
        mins = round(float(g(gen, "duration")) / 60000)
    except (TypeError, ValueError):
        mins = None
    try:
        size_gb = round(int(g(gen, "file_size")) / 1024**3, 2)
    except (TypeError, ValueError):
        size_gb = None

    w, h = g(v, "width"), g(v, "height")
    other_dar = g(v, "other_display_aspect_ratio")
    return FileRecord(
        folder=str(path.parent),
        file=path.name,
        type=content_type(path, extras_folders),
        container=g(gen, "format"),
        size_gb=size_gb,
        duration_min=mins,
        video_codec=(g(v, "format") or "") + (f" ({g(v, 'format_profile')})" if g(v, "format_profile") else ""),
        resolution=f"{w}x{h}" if w and h else "",
        aspect=other_dar[0] if other_dar else g(v, "display_aspect_ratio"),
        frame_rate=g(v, "frame_rate"),
        bit_depth=g(v, "bit_depth"),
        hdr=hdr(v) if v else "",
        video_bitrate=kbps(g(v, "bit_rate")) or kbps(g(gen, "overall_bit_rate")),
        audio=[describe_audio(a) for a in auds],
        subs=[describe_sub(s) for s in subs],
        audio_split=[audio_fields(a) for a in auds],
        subs_split=[sub_fields(s) for s in subs],
    )


def scan_file(path: Path, extras_folders: Iterable[str] = DEFAULT_EXTRAS_FOLDERS) -> FileRecord:
    """Read one file with MediaInfo. Raises on unreadable files."""
    from pymediainfo import MediaInfo  # imported lazily so the rest of core works without it
    mi = MediaInfo.parse(str(path))
    return record_from_tracks(path, mi.tracks, extras_folders)
