"""Command-line front-end (same flags as the original media_report.py)."""
from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path

from .core import DEFAULT_EXTRAS_FOLDERS, find_files
from .settings import DEFAULT_EXPORT_DIR

USAGE = """\
Scan folders of movie/TV rips and write an Excel report with one row per file
and columns Audio 1, Audio 2, ... / Sub 1, Sub 2, ...

Examples:
    py media_report.py "D:\\Movies" "D:\\TV" -o library.xlsx
    py media_report.py "D:\\Movies" --max-audio 3 --max-subs 6
"""


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=USAGE, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("folders", nargs="+", help="Folders to scan (recursive)")
    ap.add_argument("-o", "--output", default=None,
                    help="Output .xlsx (default: export\\media_report_<date>.xlsx next to this script)")
    ap.add_argument("--max-audio", type=int, default=0, help="Cap Audio columns (0 = as many as needed)")
    ap.add_argument("--max-subs", type=int, default=0, help="Cap Sub columns (0 = as many as needed)")
    ap.add_argument("--workers", type=int, default=4, help="Files to read in parallel (default 4)")
    ap.add_argument("--extras", default=",".join(DEFAULT_EXTRAS_FOLDERS),
                    help="Comma-separated folder names that mark bonus content (default: %(default)s)")
    args = ap.parse_args(argv)

    try:
        from .excel import ExcelOptions, write_workbook
        from .scanner import scan
        import pymediainfo  # noqa: F401  (fail early with a clear message)
    except ImportError as e:
        print(f"Missing package: {e.name}. Run: py -m pip install pymediainfo openpyxl", file=sys.stderr)
        return 1

    files = find_files(args.folders)
    if not files:
        print("No video files found.", file=sys.stderr)
        return 1

    def progress(done, total, path, err):
        print(f"[{done}/{total}] {path.name}" + (f"  !! {err}" if err else ""), flush=True)

    extras = [e for e in args.extras.split(",") if e.strip()]
    result = scan(files, workers=args.workers, on_progress=progress, extras_folders=extras)

    output = args.output
    if not output:
        stamp = datetime.now().strftime("%Y-%m-%d_%H%M")
        output = DEFAULT_EXPORT_DIR / f"media_report_{stamp}.xlsx"
    out = write_workbook(result.records, result.errors, output,
                         ExcelOptions(max_audio=args.max_audio, max_subs=args.max_subs))
    n_err = len(result.errors)
    print(f"\nDone: {len(result.records)} files -> {out}"
          + (f" ({n_err} errors, see 'Errors' sheet)" if n_err else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
