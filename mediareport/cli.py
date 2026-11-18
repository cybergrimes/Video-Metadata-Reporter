"""Command-line front-end (same flags as the original media_report.py)."""
from __future__ import annotations

import argparse
import sys
import threading
from pathlib import Path

from .core import DEFAULT_EXTRAS_FOLDERS, parse_extras
from .job import DONE, run_job
from .settings import Options

USAGE = """\
Scan folders of movie/TV rips and write an Excel report with one row per file
and columns Audio 1, Audio 2, ... / Sub 1, Sub 2, ...

Examples:
    py media_report.py "D:\\Movies" "D:\\TV" -o library.xlsx
    py media_report.py "D:\\Movies" --max-audio 3 --max-subs 6
"""


def non_negative(text: str) -> int:
    n = int(text)
    if n < 0:
        raise argparse.ArgumentTypeError("must be 0 or more")
    return n


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=USAGE, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("folders", nargs="+", help="Folders to scan (recursive)")
    ap.add_argument("-o", "--output", default=None,
                    help="Output .xlsx (default: 'Media Report <date>_<time>.xlsx' in the export folder next to this script)")
    ap.add_argument("--max-audio", type=non_negative, default=0, help="Cap Audio columns (0 = as many as needed)")
    ap.add_argument("--max-subs", type=non_negative, default=0, help="Cap Sub columns (0 = as many as needed)")
    ap.add_argument("--split-tracks", action="store_true",
                    help="Put each audio/sub detail in its own column (Audio 1 Language, Audio 1 Codec, ...)")
    ap.add_argument("--workers", type=int, default=4, choices=range(1, 33), metavar="1-32", help="Files to read in parallel (default 4)")
    ap.add_argument("--extras", default=",".join(DEFAULT_EXTRAS_FOLDERS),
                    help="Comma-separated folder names that mark bonus content (default: %(default)s)")
    args = ap.parse_args(argv)

    try:
        import openpyxl  # noqa: F401  (fail early with a clear message)
        import pymediainfo  # noqa: F401
    except ImportError as e:
        print(f"Missing package: {e.name}. Run: py -m pip install pymediainfo openpyxl", file=sys.stderr)
        return 1

    def progress(done, total, path, err):
        print(f"[{done}/{total}] {path.name}" + (f"  !! {err}" if err else ""), flush=True)

    opts = Options(folders=list(args.folders), max_audio=args.max_audio, max_subs=args.max_subs,
                   split_tracks=args.split_tracks, extras_folders=parse_extras(args.extras),
                   workers=args.workers)
    res = run_job(opts, log=print, progress=progress, cancel_event=threading.Event(),
                  output=Path(args.output) if args.output else None)
    return 0 if res.status == DONE else 1


if __name__ == "__main__":
    sys.exit(main())
