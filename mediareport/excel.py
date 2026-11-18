"""Write scan results to an .xlsx workbook (one "Library" row per file + "Errors" sheet)."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

from .core import BASE_COLUMNS, FileRecord, ScanError

HEADER_FILL = "DDEBF7"
MAX_COL_WIDTH = 60


@dataclass
class ExcelOptions:
    max_audio: int = 0   # 0 = as many Audio columns as needed
    max_subs: int = 0    # 0 = as many Sub columns as needed


def track_column_counts(records: Sequence[FileRecord], opts: ExcelOptions) -> tuple[int, int]:
    n_aud = max((len(r.audio) for r in records), default=0)
    n_sub = max((len(r.subs) for r in records), default=0)
    if opts.max_audio:
        n_aud = min(n_aud, opts.max_audio)
    if opts.max_subs:
        n_sub = min(n_sub, opts.max_subs)
    return n_aud, n_sub


def build_workbook(records: Sequence[FileRecord], errors: Sequence[ScanError],
                   opts: ExcelOptions | None = None) -> Workbook:
    opts = opts or ExcelOptions()
    n_aud, n_sub = track_column_counts(records, opts)
    headers = BASE_COLUMNS + [f"Audio {i}" for i in range(1, n_aud + 1)] + [f"Sub {i}" for i in range(1, n_sub + 1)]

    wb = Workbook()
    ws = wb.active
    ws.title = "Library"
    ws.append(headers)
    for r in records:
        ws.append(r.base_values()
                  + (r.audio + [""] * n_aud)[:n_aud]
                  + (r.subs + [""] * n_sub)[:n_sub])

    # Formatting: bold header, freeze panes, filters, sensible widths
    fill = PatternFill("solid", fgColor=HEADER_FILL)
    for cell in ws[1]:
        cell.font = Font(bold=True)
        cell.fill = fill
        cell.alignment = Alignment(vertical="center")
    ws.freeze_panes = "C2"
    ws.auto_filter.ref = ws.dimensions
    for idx, col in enumerate(headers, 1):
        letter = get_column_letter(idx)
        longest = max(len(str(c.value or "")) for c in ws[letter][:500])
        ws.column_dimensions[letter].width = min(max(longest + 2, len(col) + 2), MAX_COL_WIDTH)

    if errors:
        es = wb.create_sheet("Errors")
        es.append(["File", "Error"])
        for e in errors:
            es.append([e.path, e.message])
    return wb


def write_workbook(records: Sequence[FileRecord], errors: Sequence[ScanError],
                   path: str | Path, opts: ExcelOptions | None = None) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    build_workbook(records, errors, opts).save(path)
    return path


def unique_path(path: str | Path) -> Path:
    """path, or 'name (2).xlsx', 'name (3).xlsx', ... if it already exists."""
    path = Path(path)
    n = 2
    candidate = path
    while candidate.exists():
        candidate = path.with_name(f"{path.stem} ({n}){path.suffix}")
        n += 1
    return candidate
