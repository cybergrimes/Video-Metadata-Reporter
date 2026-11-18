# Media Report

Scan a library of movie and TV rips and export the details MediaInfo reports (video, audio, subtitles) to an Excel workbook, one row per video file.

Media Report uses the [MediaInfo](https://mediaarea.net/en/MediaInfo) library but is an independent project, not affiliated with or endorsed by MediaArea.net SARL. See [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).

![platform: Windows](https://img.shields.io/badge/platform-Windows-blue)

## Quick start (Windows)

1. Download and unzip the release.
2. Run `MediaReport.exe`.
3. Click **Add...** and choose one or more library folders (Ctrl-click or Shift-click to pick several), then **Start scan**.
4. When it finishes, click **Open report**.

Nothing is installed and no console window opens. Progress and errors appear in the log pane.

macOS and Linux builds are planned but not available yet. You can run from source on those systems (see below), but this is untested there.

## What you get

One workbook per scan with a **Library** sheet (one row per video file) and, if any files couldn't be read, an **Errors** sheet.

Columns: `Folder, File, Category, Container, Encoded date, Writing application, Writing library, Size (GB), Duration (min), Video codec, Resolution, Aspect ratio, Frame rate, Bit depth, Dynamic range, Video bitrate, # Audio`, then `Audio 1..N`, then `# Subs`, then `Sub 1..N`.

- Audio cell: `English | Dolby TrueHD with Dolby Atmos | 7.1 | 4,000 kb/s | "Title" | Default`
- Subtitle cell: `English | PGS | "Title" | Forced | Default`
- **External subtitles** next to a video (`.srt`, `.ass`, `.ssa`, `.vtt`, `.sub`/`.idx`, `.sup`) are added after the embedded tracks and count in `# Subs`. They must be named like the video, e.g. `Movie (2020).en.forced.srt`. If two videos share a name prefix (`Movie.mkv` and `Movie.Trailer.mkv`), a subtitle goes to the video with the longest matching name. The language, `forced` and `default` come from the name, other words become the Name, and no language shows `und`. Two-letter codes that are also words (`no`, `it`, `id`, `he`, `hi`) count as a language only in lower case. The cell ends with `External` (or the Format shows `SRT (external)` in separate-column mode). Subtitle files in a separate `Subs` folder are not picked up.
- **Category** is `Main`, or `Extras` / `Featurettes` / `Scenes` when a folder below the one you scanned has that name (editable in the app).
- **Dynamic range** is one of `Dolby Vision [+ HDR10]`, `HDR10+`, `HDR10`, `HLG`, `SDR`.
- The header row is bold and frozen, filters are on, and columns are auto-sized to fit their longest value.
- Files scanned: mkv, mp4, m4v, avi, mov, ts, m2ts, wmv, mpg, mpeg, webm.

## Options

| Option | Meaning |
|---|---|
| Save reports to | Where reports go. Default is an `export` folder next to the app. If that isn't writable, reports go to `Documents\Media Report` and the log says so. |
| Max audio / subtitle columns | Cap the number of `Audio N` / `Sub N` columns. `0` means no cap. The `# Audio` / `# Subs` columns always show the true count. |
| Choose report fields | Pick which fields (columns) go in the report. Folder and File are always included; every other column (including the audio and subtitle groups) can be switched off. Saved as `hidden_columns` in the ini; `--hide-columns "Writing library,Aspect ratio"` on the command line. |
| Separate columns | Off: one combined cell per track. On: each detail gets its own column, grouped by track. Audio N: language, codec, channels, bitrate, name, default. Sub N: language, format, name, forced, default. Also `split_tracks` in the ini and `--split-tracks` on the command line. |
| Files at once | How many files are scanned in parallel. |
| Extras folder names | Comma-separated folder names treated as non-main content. Videos in them are still scanned but get the folder name in the `Category` column instead of `Main`. If this is left empty, the `Category` column is left out of the report. |

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

Command line (no GUI; uses the same scan and report code as the app, and never overwrites an existing `-o` file):

```
py media_report.py "D:\Movies" "D:\TV" -o out.xlsx --max-audio 3 --max-subs 6
```

Other flags: `--workers`, `--extras`, `--split-tracks`, `--hide-columns`. Run `py media_report.py --help` for the full list.

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
  core.py          file discovery, track parsing -> FileRecord
  scanner.py       parallel, cancellable scan
  excel.py         workbook writer
  job.py           find -> scan -> write, toolkit-agnostic
  settings.py      MediaReport.ini load/save
  paths.py         app/config/export folders, open file or folder
  folderpicker.py  multi-select folder dialog (Windows system dialog)
  gui.py           Tkinter front-end
  cli.py           command-line front-end
MediaReport.pyw   GUI launcher (no console)
media_report.py   CLI launcher
```

All logic lives in the package; `gui.py` only calls it, so the interface can be swapped without touching the scanner.

## Licence

See [LICENSE](LICENSE) for this project and [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) for the libraries it uses and bundles.
