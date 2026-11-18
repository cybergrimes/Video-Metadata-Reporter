# Third-party software

Video Metadata Reporter uses the following software. Each keeps its own licence.

| Component | Used for | Licence |
|---|---|---|
| [MediaInfo](https://mediaarea.net/en/MediaInfo) library (MediaArea.net SARL) | Reading video, audio and subtitle details | BSD-2-Clause. Version 26.10 is bundled; the full text is in `_internal\vendor\mediainfo\License.html` in the Windows build. |
| [pymediainfo](https://github.com/sbraz/pymediainfo) | Python wrapper for MediaInfo (its own bundled `MediaInfo.dll` is only a fallback) | MIT. Text in `_internal\pymediainfo-*.dist-info\licenses\LICENSE`. |
| [openpyxl](https://openpyxl.readthedocs.io/) | Writing the Excel workbook | MIT |
| [Python](https://www.python.org/) and Tcl/Tk | Runtime and GUI, bundled into the Windows build by PyInstaller | PSF licence; Tcl/Tk licence |
| [PyInstaller](https://pyinstaller.org/) | Building the Windows exe (build tool only) | GPL-2.0 with a bootloader exception that permits distributing the built app under any licence |

Video Metadata Reporter is an independent project. It is not affiliated with, sponsored by or endorsed by MediaArea.net SARL, the makers of MediaInfo.
