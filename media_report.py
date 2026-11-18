#!/usr/bin/env python3
"""
media_report.py - Scan a folder of movie/TV rips and write an Excel report
with one row per file and columns Audio 1, Audio 2, ... / Sub 1, Sub 2, ...

Setup (once):
    pip install pymediainfo openpyxl
    (Windows/macOS: pymediainfo bundles MediaInfo. Linux: also install the
     'libmediainfo' / 'mediainfo' package from your distro.)

Usage:
    python media_report.py "D:\\Movies" "D:\\TV" -o library.xlsx
    python media_report.py /mnt/media --max-audio 3 --max-subs 6
"""
import argparse
import os
from datetime import datetime
import sys
from pathlib import Path

try:
    from pymediainfo import MediaInfo
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill, Alignment
    from openpyxl.utils import get_column_letter
except ImportError as e:
    sys.exit(f"Missing package: {e.name}. Run: pip install pymediainfo openpyxl")

VIDEO_EXTS = {".mkv", ".mp4", ".m4v", ".avi", ".mov", ".ts", ".m2ts", ".wmv", ".mpg", ".mpeg", ".webm"}

# Folder names (case-insensitive) that mark bonus content. Add more if you like,
# e.g. "behind the scenes", "deleted scenes", "trailers", "interviews".
EXTRAS_FOLDERS = {"extras", "featurettes", "scenes"}


def content_type(path):
    """'Extras' / 'Featurettes' / 'Scenes' if any parent folder matches, else 'Main'."""
    for part in reversed(path.parent.parts):
        if part.lower() in EXTRAS_FOLDERS:
            return part.title()
    return "Main"


def g(track, attr):
    """Safe attribute getter."""
    return getattr(track, attr, None) if track is not None else None


def lang(track):
    other = g(track, "other_language")
    if other:
        return other[0]          # e.g. "English"
    return g(track, "language") or "und"


def channels(track):
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


def kbps(value):
    try:
        return f"{round(int(float(str(value).split()[0])) / 1000)} kb/s"
    except (TypeError, ValueError):
        return ""


def yes(v):
    return str(v).lower() in ("yes", "true", "1")


def describe_audio(t):
    codec = g(t, "commercial_name") or g(t, "format") or "?"
    parts = [lang(t), codec, channels(t), kbps(g(t, "bit_rate"))]
    title = g(t, "title")
    if title:
        parts.append(f'"{title}"')
    if yes(g(t, "default")):
        parts.append("Default")
    return " | ".join(p for p in parts if p)


def describe_sub(t):
    fmt = g(t, "format") or "?"
    fmt = {"PGS": "PGS", "UTF-8": "SRT", "VobSub": "VobSub", "ASS": "ASS"}.get(fmt, fmt)
    parts = [lang(t), fmt]
    title = g(t, "title")
    if title:
        parts.append(f'"{title}"')
    if yes(g(t, "forced")):
        parts.append("Forced")
    if yes(g(t, "default")):
        parts.append("Default")
    return " | ".join(p for p in parts if p)


def hdr(v):
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


def scan_file(path):
    mi = MediaInfo.parse(str(path))
    gen = next((t for t in mi.tracks if t.track_type == "General"), None)
    vids = [t for t in mi.tracks if t.track_type == "Video"]
    auds = [t for t in mi.tracks if t.track_type == "Audio"]
    subs = [t for t in mi.tracks if t.track_type == "Text"]
    v = vids[0] if vids else None

    dur_ms = g(gen, "duration")
    try:
        mins = round(float(dur_ms) / 60000)
    except (TypeError, ValueError):
        mins = None
    size = g(gen, "file_size")
    try:
        size_gb = round(int(size) / 1024**3, 2)
    except (TypeError, ValueError):
        size_gb = None

    w, h = g(v, "width"), g(v, "height")
    row = {
        "Folder": str(path.parent),
        "File": path.name,
        "Type": content_type(path),
        "Container": g(gen, "format"),
        "Size (GB)": size_gb,
        "Duration (min)": mins,
        "Video Codec": (g(v, "format") or "") + (f" ({g(v, 'format_profile')})" if g(v, "format_profile") else ""),
        "Resolution": f"{w}x{h}" if w and h else "",
        "Aspect": g(v, "other_display_aspect_ratio")[0] if g(v, "other_display_aspect_ratio") else g(v, "display_aspect_ratio"),
        "Frame Rate": g(v, "frame_rate"),
        "Bit Depth": g(v, "bit_depth"),
        "HDR": hdr(v) if v else "",
        "Video Bitrate": kbps(g(v, "bit_rate")) or kbps(g(gen, "overall_bit_rate")),
        "# Audio": len(auds),
        "# Subs": len(subs),
    }
    return row, [describe_audio(a) for a in auds], [describe_sub(s) for s in subs]


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("folders", nargs="+", help="Folders to scan (recursive)")
    ap.add_argument("-o", "--output", default=None,
                    help="Output .xlsx (default: export\\media_report_<date>.xlsx next to this script)")
    ap.add_argument("--max-audio", type=int, default=0, help="Cap Audio columns (0 = as many as needed)")
    ap.add_argument("--max-subs", type=int, default=0, help="Cap Sub columns (0 = as many as needed)")
    args = ap.parse_args()

    files = []
    for folder in args.folders:
        for root, _, names in os.walk(folder):
            files += [Path(root) / n for n in names if Path(n).suffix.lower() in VIDEO_EXTS]
    files.sort()
    if not files:
        sys.exit("No video files found.")

    results, errors = [], []
    for i, f in enumerate(files, 1):
        print(f"[{i}/{len(files)}] {f.name}", flush=True)
        try:
            results.append(scan_file(f))
        except Exception as e:  # keep going on bad files
            errors.append((str(f), str(e)))

    n_aud = max((len(a) for _, a, _ in results), default=0)
    n_sub = max((len(s) for _, _, s in results), default=0)
    if args.max_audio:
        n_aud = min(n_aud, args.max_audio)
    if args.max_subs:
        n_sub = min(n_sub, args.max_subs)

    base_cols = list(results[0][0].keys())
    headers = base_cols + [f"Audio {i}" for i in range(1, n_aud + 1)] + [f"Sub {i}" for i in range(1, n_sub + 1)]

    wb = Workbook()
    ws = wb.active
    ws.title = "Library"
    ws.append(headers)
    for row, auds, subs in results:
        ws.append([row[c] for c in base_cols]
                  + (auds + [""] * n_aud)[:n_aud]
                  + (subs + [""] * n_sub)[:n_sub])

    # Formatting: bold header, freeze panes, filters, sensible widths
    fill = PatternFill("solid", fgColor="DDEBF7")
    for cell in ws[1]:
        cell.font = Font(bold=True)
        cell.fill = fill
        cell.alignment = Alignment(vertical="center")
    ws.freeze_panes = "C2"
    ws.auto_filter.ref = ws.dimensions
    for idx, col in enumerate(headers, 1):
        longest = max(len(str(c.value or "")) for c in ws[get_column_letter(idx)][:500])
        ws.column_dimensions[get_column_letter(idx)].width = min(max(longest + 2, len(col) + 2), 60)

    if errors:
        es = wb.create_sheet("Errors")
        es.append(["File", "Error"])
        for e in errors:
            es.append(list(e))

    if not args.output:
        stamp = datetime.now().strftime("%Y-%m-%d_%H%M")
        args.output = str(Path(__file__).resolve().parent / "export" / f"media_report_{stamp}.xlsx")
    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    wb.save(args.output)
    print(f"\nDone: {len(results)} files -> {args.output}" + (f" ({len(errors)} errors, see 'Errors' sheet)" if errors else ""))


if __name__ == "__main__":
    main()
