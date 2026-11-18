# Media Report

Scan a library of movie and TV rips and export the details MediaInfo reports (video, audio, subtitles) to an Excel workbook, one row per video file.

![platform: Windows](https://img.shields.io/badge/platform-Windows-blue)

## Quick start (Windows)

1. Download and unzip the release.
2. Run `MediaReport.exe`.
3. Click **Add...** to choose one or more library folders, then **Start scan**.
4. When it finishes, click **Open report**.

Nothing is installed and no console window opens. Progress and errors appear in the log pane.

macOS and Linux builds are planned but not available yet. You can run from source on those systems (see below), but this is untested there.

## What you get

One workbook per scan with a **Library** sheet (one row per video file) and, if any files couldn't be read, an **Errors** sheet.

Columns: `Folder, File, Type, Container, Size (GB), Duration (min), Video Codec, Resolution, Aspect, Frame Rate, Bit Depth, HDR, Video Bitrate, # Audio, # Subs`, followed by `Audio 1..N` and `Sub 1..N`.

- Audio cell: `English | Dolby TrueHD with Dolby Atmos | 7.1 | 4000 kb/s | "Title" | Default`
- Subtitle cell: `English | PGS | "Title" | Forced | Default`
- **Type** is `Main`, or `Extras` / `Featurettes` / `Scenes` when a parent folder has that name (editable in the app).
- **HDR** is one of `Dolby Vision [+ HDR10]`, `HDR10+`, `HDR10`, `HLG`, `SDR`.
- Header row is bold, panes are frozen, filters are on, and columns are auto-sized to fit their longest value.
- Files scanned: mkv, mp4, m4v, avi, mov, ts, m2ts, wmv, mpg, mpeg, webm.

## Options

| Option | Meaning |
|---|---|
| Save reports to | Where reports go. Default is an `export` folder next to the app. If that isn't writable, reports go to `Documents\Media Report` and the log says so. |
| Max audio / subtitle columns | Cap the number of `Audio N` / `Sub N` columns. `0` means no cap. The `# Audio` / `# Subs` columns always show the true count. |
| Files at once | How many files are scanned in parallel. |
| Extras folder names | Comma-separated folder names treated as non-main content. |

**Cancel** stops the scan and writes nothing. Reports are never overwritten; a repeat name gets ` (2)`, ` (3)`, and so on.

## Settings

Settings are saved to `MediaReport.ini` next to the app (or in `%APPDATA%\MediaReport` if that folder isn't writable). It's plain text and safe to edit by hand while the app is closed. Delete it to reset everything.

If the app fails to start, the error is shown in a dialog and saved to `startup-error.log` in `%APPDATA%\MediaReport`.

## Running from source

Requires a recent Python 3 with Tkinter (developed on 3.15).

```
py -m pip install -r requirements.txt
py MediaReport.pyw
```

Command line (no GUI):

```
py media_report.py "D:\Movies" "D:\TV" -o out.xlsx --max-audio 3 --max-subs 6
```

Other flags: `--workers`, `--extras`.

On Linux, install the MediaInfo library first (for example `libmediainfo0v5` on Debian/Ubuntu).

## Tests

```
py -m unittest discover -s tests -v
```

Tests use fake track data and temporary folders only.

## Building the Windows exe

```
py -m venv .venv
.venv\Scripts\python -m pip install -r requirements-dev.txt
.venv\Scripts\python -m PyInstaller MediaReport.spec --noconfirm
```

The result is `dist\MediaReport\`. Zip that folder to share it.

## Layout

```
mediareport/
  core.py      file discovery, track parsing -> FileRecord
  scanner.py   parallel, cancellable scan
  excel.py     workbook writer
  job.py       find -> scan -> write, toolkit-agnostic
  settings.py  MediaReport.ini load/save
  paths.py     app/config/export folders, open file or folder
  gui.py       Tkinter front-end
  cli.py       command-line front-end
MediaReport.pyw   GUI launcher (no console)
media_report.py   CLI launcher
```

All logic lives in the package; `gui.py` only calls it, so the interface can be swapped without touching the scanner.
