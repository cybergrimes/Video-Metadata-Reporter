"""Pure scanning logic: find video files and turn MediaInfo tracks into a FileRecord.

Nothing in here knows about Excel, threads or the GUI.
"""
from __future__ import annotations

import os
import re
import sys
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Iterable

VIDEO_EXTS = {".mkv", ".mp4", ".m4v", ".avi", ".mov", ".ts", ".m2ts", ".wmv", ".mpg", ".mpeg", ".webm"}

# Folder names (case-insensitive) that mark bonus content.
DEFAULT_EXTRAS_FOLDERS = ("extras", "featurettes", "scenes")

# Fixed columns, in output order. Audio N columns follow these, then '# Subs', then Sub N.
BASE_COLUMNS = [
    "Folder", "File", "Category", "Container", "Encoded date", "Writing application",
    "Size (GB)", "Duration (min)",
    "Video codec", "Resolution", "Aspect ratio", "Frame rate", "Bit depth", "Dynamic range",
    "Video bitrate", "# Audio",
]

SUBS_COUNT_COLUMN = "# Subs"   # sits between the Audio N and Sub N columns
CATEGORY_COLUMN = "Category"   # Main / Extras / ... ; omitted from reports when no extras folders are defined

# Columns the user can switch off. Folder and File are always written.
CRITICAL_COLUMNS = ("Folder", "File")
AUDIO_GROUP = "Audio"          # '# Audio' + every 'Audio N ...' column
SUBS_GROUP = "Subtitles"       # '# Subs' + every 'Sub N ...' column
OPTIONAL_COLUMNS = ([c for c in BASE_COLUMNS if c not in CRITICAL_COLUMNS and c != "# Audio"]
                    + [AUDIO_GROUP, SUBS_GROUP])


def normalize_hidden_columns(names: Iterable[str]) -> list[str]:
    """Match names (any case) to OPTIONAL_COLUMNS, drop unknown ones and duplicates, keep canonical order."""
    wanted = {n.strip().lower() for n in names}
    return [c for c in OPTIONAL_COLUMNS if c.lower() in wanted]

# Per-track columns used when tracks are split into separate fields
# ("Audio 1 language", "Audio 1 codec", ...). Order matters.
AUDIO_FIELDS = ["language", "codec", "channels", "bitrate", "name", "default"]
SUB_FIELDS = ["language", "format", "name", "forced", "default"]


@dataclass
class FileRecord:
    folder: str
    file: str
    category: str = "Main"
    container: str | None = None
    encoded_date: str = ""
    writing_app: str = ""
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
            self.folder, self.file, self.category, self.container, self.encoded_date,
            self.writing_app, self.size_gb,
            self.duration_min, self.video_codec, self.resolution, self.aspect,
            self.frame_rate, self.bit_depth, self.hdr, self.video_bitrate,
            len(self.audio),
        ]


@dataclass
class ScanError:
    path: str
    message: str


# --------------------------------------------------------------------------- files

def find_files(folders: Iterable[str | os.PathLike],
               should_stop: Callable[[], bool] | None = None,
               on_error: Callable[[OSError], None] | None = None) -> list[Path]:
    """All video files under the given folders (recursive), sorted, de-duplicated.

    should_stop is checked once per directory; when it returns True the walk
    stops early and returns what was found so far. on_error is called with the
    OSError for each folder that couldn't be read (otherwise they are skipped silently).
    """
    files: set[Path] = set()
    for folder in folders:
        for root, _, names in os.walk(folder, onerror=on_error):
            if should_stop and should_stop():
                return sorted(files)
            files.update(Path(root) / n for n in names if Path(n).suffix.lower() in VIDEO_EXTS)
    return sorted(files)


def parse_extras(text: str) -> list[str]:
    """'Extras, Featurettes' -> ['Extras', 'Featurettes'] (blank entries dropped)."""
    return [e.strip() for e in text.split(",") if e.strip()]


def date_only(value) -> str:
    """'2021-03-14 09:12:33 UTC' -> '2021-03-14'. Unrecognised text is kept as is."""
    text = str(value or "").strip()
    m = re.search(r"\d{4}-\d{2}-\d{2}", text)
    return m.group(0) if m else text


def content_type(path: Path, extras_folders: Iterable[str] = DEFAULT_EXTRAS_FOLDERS,
                 root: Path | None = None) -> str:
    """'Extras' / 'Featurettes' / 'Scenes' if a parent folder matches (nearest wins), else 'Main'.

    With `root` (the scan folder the file was found under) only folders below it are
    considered, so a library that merely lives inside a folder called 'Extras' isn't mislabelled.
    """
    wanted = {e.strip().lower() for e in extras_folders if e.strip()}
    parent = path.parent
    if root is not None:
        try:
            parent = parent.relative_to(root)
        except ValueError:
            pass
    for part in reversed(parent.parts):
        if part.lower() in wanted:
            # Capitalise each word without str.title()'s "Director'S Cut" apostrophe bug.
            return " ".join(w[:1].upper() + w[1:].lower() for w in part.split(" "))
    return "Main"


# --------------------------------------------------------------------------- track helpers

_APP_VERSION = re.compile(r"^(.+?)\s+v?(\d+(?:\.\d+)*(?:-[\w.]+)?)(?=\s|$)")   # version may carry -beta1, -rc2


def clean_writing_app(text) -> str:
    """'mkvmerge v97.0 ('Name') 64-bit' -> 'mkvmerge 97.0'; 'MakeMKV v1.18.3 win(x64-release)' -> 'MakeMKV 1.18.3'.

    Keeps just the application name and version number; anything it can't parse is left as is.
    """
    text = (text or "").strip()
    m = _APP_VERSION.match(text)
    return f"{m.group(1)} {m.group(2)}" if m else text


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
        bps = int(float(str(value).split()[0]))
    except (TypeError, ValueError):
        return ""
    if bps <= 0:
        return ""
    return f"{max(1, round(bps / 1000)):,} kb/s"


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


EXTERNAL = " (external)"


def describe_sub(t) -> str:
    return describe_sub_fields(sub_fields(t))


def describe_sub_fields(fields: list[str]) -> str:
    """The combined 'English | PGS | "Title" | Forced | Default' cell from SUB_FIELDS values."""
    lang_, fmt, title, forced, default = fields
    external = fmt.endswith(EXTERNAL)
    fmt = fmt[:-len(EXTERNAL)] if external else fmt
    parts = [lang_, fmt]
    if title:
        parts.append(f'"{title}"')
    if forced:
        parts.append(forced)
    if default:
        parts.append(default)
    if external:
        parts.append("External")
    return " | ".join(p for p in parts if p)


# --------------------------------------------------------------------------- sidecar subtitles

# Subtitle files that sit next to a video: extension -> format name.
SIDECAR_FORMATS = {".srt": "SRT", ".ass": "ASS", ".ssa": "SSA", ".vtt": "WebVTT",
                   ".sub": "SUB", ".sup": "PGS"}

# Language tokens seen in subtitle file names (ISO 639-1/-2 codes and English names).
_LANGUAGES = {
    "English": "en eng english", "French": "fr fre fra french", "German": "de ger deu german",
    "Spanish": "es spa spanish", "Italian": "it ita italian", "Portuguese": "pt por portuguese",
    "Russian": "ru rus russian", "Japanese": "ja jpn japanese", "Chinese": "zh chi zho chinese",
    "Korean": "ko kor korean", "Dutch": "nl dut nld dutch", "Swedish": "sv swe swedish",
    "Danish": "da dan danish", "Norwegian": "no nor norwegian", "Finnish": "fi fin finnish",
    "Polish": "pl pol polish", "Turkish": "tr tur turkish", "Arabic": "ar ara arabic",
    "Hebrew": "he heb hebrew", "Hindi": "hi hin hindi", "Czech": "cs cze ces czech",
    "Greek": "el gre ell greek", "Hungarian": "hu hun hungarian", "Thai": "th tha thai",
    "Vietnamese": "vi vie vietnamese", "Indonesian": "id ind indonesian",
    "Romanian": "ro rum ron romanian", "Ukrainian": "uk ukr ukrainian",
}
LANGUAGE_TOKENS = {tok: name for name, toks in _LANGUAGES.items() for tok in toks.split()}
# Codes that are also common words: only treated as a language when written in lower case
# ('Movie.it.srt' is Italian, 'Movie.It.srt' is a name).
AMBIGUOUS_CODES = {"no", "it", "id", "he", "hi"}


class FolderListing:
    """What sidecar matching needs to know about one folder, built once and shared by its videos."""

    def __init__(self, names: Iterable[str]):
        names = list(names)
        suffix = {n: Path(n).suffix.lower() for n in names}
        self.video_stems = frozenset(Path(n).stem.lower() for n in names if suffix[n] in VIDEO_EXTS)
        self.idx_stems = frozenset(Path(n).stem.lower() for n in names if suffix[n] == ".idx")
        self.subtitles = sorted((n for n in names if suffix[n] in SIDECAR_FORMATS), key=str.lower)


def sidecar_fields(video: Path, filename: str, has_idx: bool = False,
                   other_videos: "frozenset[str] | set[str]" = frozenset()) -> list[str] | None:
    """SUB_FIELDS values for `filename` if it is a subtitle file belonging to `video`, else None.

    A sidecar is '<video stem>[.tags].<ext>', e.g. Movie.en.forced.srt. Tags that name a
    language set the language, 'forced'/'default' set the flags, anything else becomes the Name.
    `other_videos` (lower-case stems of the folder's videos) lets the longest matching video win:
    'Movie.Trailer.en.srt' belongs to 'Movie.Trailer.mkv', not to 'Movie.mkv'.
    """
    p = Path(filename)
    fmt = SIDECAR_FORMATS.get(p.suffix.lower())
    stem = video.stem
    if not fmt or not p.stem.lower().startswith(stem.lower()):
        return None
    rest = p.stem[len(stem):]
    if rest and not rest.startswith("."):
        return None
    full = p.stem.lower()
    cuts = [i for i, c in enumerate(full) if c == "."] + [len(full)]
    if any(full[:i] in other_videos for i in cuts if i > len(stem)):
        return None
    if p.suffix.lower() == ".sub" and has_idx:
        fmt = "VobSub"
    language, forced, default, name = "", False, False, []
    for tok in (t for t in rest.split(".") if t):
        low = tok.lower()
        if low == "forced":
            forced = True
        elif low == "default":
            default = True
        elif not language and low in LANGUAGE_TOKENS and not (low in AMBIGUOUS_CODES and tok != low):
            language = LANGUAGE_TOKENS[low]
        else:
            name.append(tok)
    return [language or "und", fmt + EXTERNAL, " ".join(name),
            "Forced" if forced else "", "Default" if default else ""]


def sidecar_subs(video: Path, names: "Iterable[str] | FolderListing") -> list[list[str]]:
    """SUB_FIELDS rows for every subtitle file in a folder listing that belongs to `video`."""
    listing = names if isinstance(names, FolderListing) else FolderListing(names)
    out = []
    for n in listing.subtitles:
        fields = sidecar_fields(video, n, has_idx=Path(n).stem.lower() in listing.idx_stems,
                                other_videos=listing.video_stems)
        if fields:
            out.append(fields)
    return out


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

def record_from_tracks(path: Path, tracks, extras_folders: Iterable[str] = DEFAULT_EXTRAS_FOLDERS,
                       sibling_names: "Iterable[str] | FolderListing" = (),
                       root: Path | None = None) -> FileRecord:
    """Build a FileRecord from a list of MediaInfo-like track objects (testable without MediaInfo).

    sibling_names: file names in the video's folder (or a FolderListing of them); subtitle files
    among them are added after the embedded subtitle tracks.
    root: the scan folder the file was found under (limits which folders count as 'extras').
    """
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

    external = sidecar_subs(path, sibling_names)
    w, h = g(v, "width"), g(v, "height")
    other_dar = g(v, "other_display_aspect_ratio")
    return FileRecord(
        folder=str(path.parent),
        file=path.name,
        category=content_type(path, extras_folders, root),
        container=g(gen, "format"),
        encoded_date=date_only(g(gen, "encoded_date")),
        writing_app=clean_writing_app(g(gen, "writing_application")),
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
        subs=[describe_sub(s) for s in subs] + [describe_sub_fields(f) for f in external],
        audio_split=[audio_fields(a) for a in auds],
        subs_split=[sub_fields(s) for s in subs] + external,
    )


class MediaInfoUnavailable(RuntimeError):
    """The MediaInfo library we ship can't be used. The message is shown to the user as is."""


@dataclass(frozen=True)
class MediaInfoChoice:
    """The MediaInfo library scans use. `library` is passed to pymediainfo as library_file."""
    library: str | None = None   # vendored DLL path; None only off Windows (pymediainfo's own library)
    version: str = ""            # e.g. "26.10"; empty if it couldn't be read


_choice: MediaInfoChoice | None = None
_choice_lock = threading.Lock()


def _probe_mediainfo(library_file: str | None) -> tuple[str, str]:
    """Try to load a MediaInfo library. Returns (version, error); error is empty on success."""
    from pymediainfo import MediaInfo
    version = error = ""
    try:
        lib, handle, version = MediaInfo._get_library(library_file)[:3]   # private API; version only
        lib.MediaInfo_Close(handle)
        lib.MediaInfo_Delete(handle)
    except Exception as e:  # noqa: BLE001 - any failure means "couldn't load"
        error = str(e) or type(e).__name__
        # pymediainfo repeats the path in its message; we show the path ourselves, so keep just the reason.
        prefix = f"Failed to load library from {library_file} - "
        if error.startswith(prefix):
            error = error[len(prefix):]
    if error and MediaInfo.can_parse(library_file=library_file):
        error = ""   # the private call changed but the library itself works
    return version, error


def _vendored_version() -> str:
    """The MediaInfo version we ship, read from vendor/mediainfo/VERSION ('' if unavailable)."""
    from . import paths
    try:
        first = (paths.vendored_mediainfo_dir() / "VERSION").read_text(encoding="utf-8").splitlines()[0]
    except (OSError, IndexError):
        return ""
    m = re.search(r"\b\d+\.\d+\b", first)
    return m.group(0) if m else ""


def resolve_mediainfo(refresh: bool = False) -> MediaInfoChoice:
    """Load the MediaInfo library we ship once per run, or raise MediaInfoUnavailable.

    On Windows that is vendor/mediainfo/MediaInfo.dll, and its version must match vendor/mediainfo/VERSION.
    There is no fallback to pymediainfo's own copy. Off Windows pymediainfo's library is used as is.
    """
    global _choice
    with _choice_lock:
        if _choice is not None and not refresh:
            return _choice
        from . import paths
        if sys.platform == "win32":
            expected = _vendored_version()
            name = f"MediaInfo {expected}" if expected else "MediaInfo"
            dll = paths.vendored_mediainfo()
            if dll is None:
                raise MediaInfoUnavailable(
                    f"{name} isn't available: {paths.vendored_mediainfo_dir() / 'MediaInfo.dll'} is missing.")
            version, error = _probe_mediainfo(str(dll))
            if error:
                raise MediaInfoUnavailable(f"{name} couldn't be loaded from {dll}: {error}")
            if expected and version and version != expected:
                raise MediaInfoUnavailable(f"Expected {name} but {dll} is MediaInfo {version}.")
            _choice = MediaInfoChoice(str(dll), version)
        else:
            version, error = _probe_mediainfo(None)
            if error:
                raise MediaInfoUnavailable(f"MediaInfo couldn't be loaded: {error}")
            _choice = MediaInfoChoice(None, version)
        return _choice


def mediainfo_library() -> str | None:
    """Path of the MediaInfo library to use (None = pymediainfo's own, off Windows). May raise MediaInfoUnavailable."""
    return resolve_mediainfo().library


def mediainfo_version() -> str:
    """Version of the MediaInfo library in use, e.g. '26.10' (empty if unknown)."""
    return resolve_mediainfo().version


def scan_file(path: Path, extras_folders: Iterable[str] = DEFAULT_EXTRAS_FOLDERS,
              root: Path | None = None, listing: "FolderListing | None" = None) -> FileRecord:
    """Read one file with MediaInfo. Raises on unreadable files."""
    from pymediainfo import MediaInfo  # imported lazily so the rest of core works without it
    mi = MediaInfo.parse(str(path), library_file=mediainfo_library())
    if listing is None:
        listing = read_listing(path.parent)
    return record_from_tracks(path, mi.tracks, extras_folders, listing, root)


def read_listing(folder: Path) -> FolderListing:
    try:
        return FolderListing(os.listdir(folder))
    except OSError:
        return FolderListing(())


class ScanContext:
    """State shared by the worker threads of one scan: the scan roots and a per-folder listing cache.

    Each folder is listed once however many videos it holds (matters on network shares).
    """

    def __init__(self, roots: Iterable[str | os.PathLike] = ()):
        self.roots = [Path(r) for r in roots]
        self._listings: dict[Path, FolderListing] = {}
        self._lock = threading.Lock()

    def root_for(self, path: Path) -> Path | None:
        """The deepest scan root containing `path`, or None."""
        best = None
        for r in self.roots:
            try:
                path.relative_to(r)
            except ValueError:
                continue
            if best is None or len(r.parts) > len(best.parts):
                best = r
        return best

    def listing(self, folder: Path) -> FolderListing:
        with self._lock:
            cached = self._listings.get(folder)
        if cached is None:
            cached = read_listing(folder)          # outside the lock: may be slow
            with self._lock:
                cached = self._listings.setdefault(folder, cached)
        return cached

    def scan_file(self, path: Path, extras_folders: Iterable[str] = DEFAULT_EXTRAS_FOLDERS) -> FileRecord:
        return scan_file(path, extras_folders, self.root_for(path), self.listing(path.parent))
