"""Run scan_file over many files in parallel, with progress and cancel support."""
from __future__ import annotations

import threading
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Iterable, Sequence

from .core import DEFAULT_EXTRAS_FOLDERS, FileRecord, ScanError, scan_file

# on_progress(done, total, path, error_message_or_None)
ProgressFn = Callable[[int, int, Path, "str | None"], None]


@dataclass
class ScanResult:
    records: list[FileRecord] = field(default_factory=list)   # in input order
    errors: list[ScanError] = field(default_factory=list)     # in input order


def scan(
    files: Sequence[Path],
    workers: int = 4,
    on_progress: ProgressFn | None = None,
    cancel_event: threading.Event | None = None,
    extras_folders: Iterable[str] = DEFAULT_EXTRAS_FOLDERS,
    scan_fn: Callable[[Path, Iterable[str]], FileRecord] = scan_file,
) -> ScanResult:
    """Scan files; results keep input order. on_progress is called on the calling thread.

    If cancel_event is set, pending files are dropped, in-flight ones finish,
    and the caller checks cancel_event.
    """
    extras = tuple(extras_folders)
    total = len(files)
    slots: list[FileRecord | ScanError | None] = [None] * total
    cancel_event = cancel_event or threading.Event()
    done_count = 0

    with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        # Submit lazily (a few ahead of the workers) so Cancel takes effect quickly
        it = iter(enumerate(files))
        pending = {}

        def fill():
            while len(pending) < max(1, workers) * 2 and not cancel_event.is_set():
                try:
                    i, f = next(it)
                except StopIteration:
                    return
                pending[pool.submit(scan_fn, f, extras)] = i

        fill()
        while pending:
            finished, _ = wait(pending, timeout=0.2, return_when=FIRST_COMPLETED)
            for fut in finished:
                i = pending.pop(fut)
                err = None
                try:
                    slots[i] = fut.result()
                except Exception as e:  # keep going on bad files
                    err = str(e) or type(e).__name__
                    slots[i] = ScanError(str(files[i]), err)
                done_count += 1
                if on_progress:
                    on_progress(done_count, total, files[i], err)
            fill()

    result = ScanResult()
    for s in slots:
        if isinstance(s, FileRecord):
            result.records.append(s)
        elif isinstance(s, ScanError):
            result.errors.append(s)
    return result
