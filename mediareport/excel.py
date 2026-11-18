"""Write scan results to an .xlsx workbook (one "Library" row per file + "Errors" sheet)."""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

from openpyxl import Workbook
from openpyxl.cell.cell import ILLEGAL_CHARACTERS_RE
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

from .core import (AUDIO_FIELDS, AUDIO_GROUP, BASE_COLUMNS, CATEGORY_COLUMN, SUB_FIELDS, SUBS_COUNT_COLUMN,
                   SUBS_GROUP, FileRecord, ScanError)

HEADER_FILL = "DDEBF7"
PADDING = 2          # extra width (chars) so text doesn't touch the gridline
FILTER_BUTTON = 3    # extra width on header cells for the autofilter arrow


@dataclass
class ExcelOptions:
    max_audio: int = 0   # 0 = as many Audio columns as needed
    max_subs: int = 0    # 0 = as many Sub columns as needed
    include_category: bool = True    # False = leave out the "Category" column (no extras folders defined)
    hidden_columns: frozenset = frozenset()   # OPTIONAL_COLUMNS names left out of the report (Folder/File can't be)
    split_tracks: bool = False   # True = "Audio 1 language", "Audio 1 codec", ... instead of one mixed cell


def track_column_counts(records: Sequence[FileRecord], opts: ExcelOptions) -> tuple[int, int]:
    n_aud = max((len(r.audio) for r in records), default=0)
    n_sub = max((len(r.subs) for r in records), default=0)
    if opts.max_audio > 0:
        n_aud = min(n_aud, opts.max_audio)
    if opts.max_subs > 0:
        n_sub = min(n_sub, opts.max_subs)
    return n_aud, n_sub


def build_workbook(records: Sequence[FileRecord], errors: Sequence[ScanError],
                   opts: ExcelOptions | None = None) -> Workbook:
    opts = opts or ExcelOptions()
    hidden = {h.lower() for h in opts.hidden_columns}
    show_audio, show_subs = AUDIO_GROUP.lower() not in hidden, SUBS_GROUP.lower() not in hidden
    n_aud, n_sub = track_column_counts(records, opts)
    n_aud, n_sub = n_aud if show_audio else 0, n_sub if show_subs else 0

    def wanted(col: str) -> bool:
        if col == CATEGORY_COLUMN and not opts.include_category:
            return False
        if col == "# Audio":
            return show_audio
        return col == "Folder" or col == "File" or col.lower() not in hidden

    keep = [wanted(c) for c in BASE_COLUMNS]
    base = [c for c, k in zip(BASE_COLUMNS, keep) if k]
    if opts.split_tracks:
        audio_headers = [f"Audio {i} {f}" for i in range(1, n_aud + 1) for f in AUDIO_FIELDS]
        sub_headers = [f"Sub {i} {f}" for i in range(1, n_sub + 1) for f in SUB_FIELDS]
    else:
        audio_headers = [f"Audio {i}" for i in range(1, n_aud + 1)]
        sub_headers = [f"Sub {i}" for i in range(1, n_sub + 1)]
    headers = base + audio_headers + ([SUBS_COUNT_COLUMN] if show_subs else []) + sub_headers

    wb = Workbook()
    ws = wb.active
    ws.title = "Library"
    ws.append([_clean(h) for h in headers])
    for r in records:
        if opts.split_tracks:
            audio = _split_cells(r.audio_split, n_aud, len(AUDIO_FIELDS))
            subs = _split_cells(r.subs_split, n_sub, len(SUB_FIELDS))
        else:
            audio = (r.audio + [""] * n_aud)[:n_aud]
            subs = (r.subs + [""] * n_sub)[:n_sub]
        values = [v for v, k in zip(r.base_values(), keep) if k]
        ws.append([_clean(v) for v in values + audio + ([len(r.subs)] if show_subs else []) + subs])
    _force_text(ws)

    # Formatting: bold header, freeze panes, filters, sensible widths
    fill = PatternFill("solid", fgColor=HEADER_FILL)
    for cell in ws[1]:
        cell.font = Font(bold=True)
        cell.fill = fill
        cell.alignment = Alignment(vertical="center")
    ws.freeze_panes = "A2"
    ws.auto_filter.ref = ws.dimensions
    autofit_columns(ws, filter_buttons=True)

    if errors:
        es = wb.create_sheet("Errors")
        es.append(["File", "Error"])
        for e in errors:
            es.append([_clean(e.path), _clean(e.message)])
        _force_text(es)
        autofit_columns(es)
    return wb


def _clean(value):
    """Make a string safe for openpyxl: drop control characters and unencodable (lone surrogate) code points."""
    if isinstance(value, str):
        value = ILLEGAL_CHARACTERS_RE.sub("", value)
        value = value.encode("utf-8", "ignore").decode("utf-8")
    return value


def _force_text(ws) -> None:
    """Strings from media metadata or file names must never become live formulas (openpyxl treats '=...' as one)."""
    for row in ws.iter_rows():
        for cell in row:
            if cell.data_type == "f":
                cell.data_type = "s"


def _split_cells(tracks: Sequence[Sequence[str]], n: int, width: int) -> list[str]:
    """Flatten the first n tracks' fields, padding missing tracks with empty cells."""
    cells: list[str] = []
    for i in range(n):
        cells.extend(tracks[i] if i < len(tracks) else [""] * width)
    return cells


def autofit_columns(ws, filter_buttons: bool = False) -> None:
    """Size every column to its longest value, like Excel's AutoFit (no cap).

    Width is in Excel character units; +PADDING keeps text off the gridline,
    and headers get FILTER_BUTTON more so the autofilter arrow doesn't cover them.
    """
    widths: dict[int, int] = {}
    for row_idx, row in enumerate(ws.iter_rows(values_only=True), 1):
        extra = FILTER_BUTTON if (row_idx == 1 and filter_buttons) else 0
        for col_idx, value in enumerate(row, 1):
            if value is None or value == "":
                continue
            w = len(str(value)) + extra
            if w > widths.get(col_idx, 0):
                widths[col_idx] = w
    for col_idx, w in widths.items():
        ws.column_dimensions[get_column_letter(col_idx)].width = w + PADDING


def write_workbook(records: Sequence[FileRecord], errors: Sequence[ScanError],
                   path: str | Path, opts: ExcelOptions | None = None) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    # Save under a temp name first so a failed save never leaves a truncated report.
    tmp = path.with_name(f"~tmp-{path.name}")
    try:
        build_workbook(records, errors, opts).save(tmp)
        os.replace(tmp, path)
    finally:
        if tmp.exists():
            tmp.unlink()
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
