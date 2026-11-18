"""One full report run (find -> scan -> write), independent of any GUI toolkit.

A front-end calls run_job() on a worker thread and receives plain callbacks.
Cancel writes nothing.
"""
from __future__ import annotations

import os
import threading
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable, Sequence

from .core import FileRecord, find_files, scan_file
from .settings import Options

LogFn = Callable[[str], None]
# progress(done, total, path, error_message_or_None)
ProgressFn = Callable[[int, int, Path, "str | None"], None]

DONE = "done"
CANCELLED = "cancelled"
NO_FILES = "no_files"
FAILED = "failed"


@dataclass
class JobResult:
    status: str                 # DONE / CANCELLED / NO_FILES / FAILED
    report: Path | None = None  # set only when status == DONE
    files: int = 0              # video files found
    records: int = 0            # rows written
    errors: int = 0             # unreadable files (Errors sheet)
    seconds: float = 0.0
    message: str = ""           # one-line summary for the user


def format_duration(seconds: float) -> str:
    seconds = int(round(seconds))
    m, s = divmod(seconds, 60)
    h, m = divmod(m, 60)
    if h:
        return f"{h}h {m:02d}m {s:02d}s"
    if m:
        return f"{m}m {s:02d}s"
    return f"{s}s"


def run_job(
    opts: Options,
    log: LogFn,
    progress: ProgressFn,
    cancel_event: threading.Event,
    *,
    now: datetime | None = None,
    find_fn: Callable[..., Sequence[Path]] = find_files,
    scan_fn: Callable[[Path, object], FileRecord] = scan_file,
) -> JobResult:
    """Run one report. Never raises for expected failures; returns a JobResult."""
    # Imported here so a missing openpyxl is reported in the log, not at import time.
    from .excel import ExcelOptions, unique_path, write_workbook
    from .scanner import scan

    start = time.monotonic()

    def finish(status: str, message: str, **kw) -> JobResult:
        res = JobResult(status=status, message=message, seconds=time.monotonic() - start, **kw)
        log(message)
        return res

    folders = [f for f in opts.folders if f.strip()]
    if not folders:
        return finish(NO_FILES, "No folders to scan. Add at least one folder.")
    for f in folders:
        if not os.path.isdir(f):
            log(f"Skipping missing folder: {f}")

    log("Looking for video files...")
    files = list(find_fn([f for f in folders if os.path.isdir(f)], should_stop=cancel_event.is_set))
    if cancel_event.is_set():
        return finish(CANCELLED, "Cancelled. No report was written.", files=len(files))
    if not files:
        return finish(NO_FILES, "No video files found in the selected folders.")
    log(f"Found {len(files)} video file(s). Scanning with {opts.workers} worker(s)...")

    result = scan(files, workers=opts.workers, on_progress=progress,
                  cancel_event=cancel_event, extras_folders=opts.extras_folders,
                  scan_fn=scan_fn)
    if result.cancelled or cancel_event.is_set():
        return finish(CANCELLED, "Cancelled. No report was written.", files=len(files))

    export_dir, note = opts.export_dir()
    if note:
        log(note)
    path = unique_path(export_dir / opts.report_name(now))
    try:
        out = write_workbook(result.records, result.errors, path,
                             ExcelOptions(max_audio=opts.max_audio, max_subs=opts.max_subs))
    except OSError as e:
        return finish(FAILED, f"Couldn't save the report to {path}: {e}", files=len(files),
                      records=len(result.records), errors=len(result.errors))

    n_err = len(result.errors)
    elapsed = format_duration(time.monotonic() - start)
    msg = (f"Done: {len(result.records)} file(s) in {elapsed}"
           + (f", {n_err} unreadable (see 'Errors' sheet)" if n_err else "")
           + f". Saved {out}")
    return finish(DONE, msg, report=out, files=len(files),
                  records=len(result.records), errors=n_err)
