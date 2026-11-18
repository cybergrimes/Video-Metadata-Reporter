"""Tkinter front-end. Holds no scanning logic: it edits Options and calls job.run_job().

Threading rule: the worker thread never touches Tk. It puts messages on a
queue.Queue that the Tk thread drains with after().
"""
from __future__ import annotations

import os
import queue
import sys
import threading
import tkinter as tk
import traceback
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from tkinter.scrolledtext import ScrolledText

from . import APP_NAME, __version__, settings
from .core import parse_extras
from .folderpicker import ask_directories
from .job import CANCELLED, DONE, JobResult, run_job
from .paths import open_path
from .settings import Options

POLL_MS = 100
MAX_LOG_LINES = 5000     # oldest lines are trimmed beyond this
PAD = 8
MAX_TRACK_COLS = 99
MAX_WORKERS = 32


def _missing_deps() -> list[str]:
    missing = []
    for mod in ("pymediainfo", "openpyxl"):
        try:
            __import__(mod)
        except ImportError:
            missing.append(mod)
    return missing


class App:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.opts = settings.load()
        self.queue: queue.Queue = queue.Queue()
        self.worker: threading.Thread | None = None
        self.cancel_event = threading.Event()
        self.last_report: Path | None = None
        self.closing = False     # quit once the cancelled scan stops
        self.closed = False

        root.title(f"{APP_NAME} {__version__}")
        root.minsize(620, 520)
        root.protocol("WM_DELETE_WINDOW", self.on_close)
        root.report_callback_exception = self.on_tk_error

        self._build()
        self._load_into_widgets()
        self._set_running(False)
        self.btn_open_report.state(["disabled"])
        self.log(f"Settings: {settings.settings_path()}")
        missing = _missing_deps()
        if missing:
            self.log("Missing package(s): " + ", ".join(missing)
                     + ". Install with: py -m pip install " + " ".join(missing))
        self._after_id = root.after(POLL_MS, self._poll)

    # ------------------------------------------------------------------ layout

    def _build(self) -> None:
        root = self.root
        root.columnconfigure(0, weight=1)
        root.rowconfigure(3, weight=1)

        # Scan: what to read
        ff = ttk.LabelFrame(root, text="Scan", padding=PAD)
        ff.grid(row=0, column=0, sticky="nsew", padx=PAD, pady=(PAD, 0))
        ff.columnconfigure(1, weight=1)
        self.folder_list = tk.Listbox(ff, height=5, selectmode="extended", activestyle="none")
        self.folder_list.grid(row=0, column=0, rowspan=3, columnspan=2, sticky="nsew")
        sb = ttk.Scrollbar(ff, orient="vertical", command=self.folder_list.yview)
        sb.grid(row=0, column=2, rowspan=3, sticky="ns")
        self.folder_list.configure(yscrollcommand=sb.set)
        self.btn_add = ttk.Button(ff, text="Add", command=self.add_folder)
        self.btn_add.grid(row=0, column=3, sticky="ew", padx=(PAD, 0))
        self.btn_remove = ttk.Button(ff, text="Remove", command=self.remove_folders)
        self.btn_remove.grid(row=1, column=3, sticky="ew", padx=(PAD, 0), pady=(4, 0))
        self.btn_clear = ttk.Button(ff, text="Clear", command=self.clear_folders)
        self.btn_clear.grid(row=2, column=3, sticky="ew", padx=(PAD, 0), pady=(4, 0))
        self.folder_list.bind("<Delete>", lambda e: self.remove_folders())

        ttk.Label(ff, text="Extras folder names:").grid(row=3, column=0, sticky="w", pady=(PAD, 0))
        self.var_extras = tk.StringVar()
        self.ent_extras = ttk.Entry(ff, textvariable=self.var_extras)
        self.ent_extras.grid(row=3, column=1, columnspan=3, sticky="ew", padx=(PAD, 0), pady=(PAD, 0))
        # Explicit line breaks (no wraplength) so no single word ever drops onto its own line.
        ttk.Label(ff, text="Separate names with commas. Videos in these folders are still scanned.\n"
                           "They get the folder name in the Category column instead of 'Main'.\n"
                           "Leave empty to omit the Category column.",
                  foreground="gray", justify="left",
                  ).grid(row=4, column=1, columnspan=3, sticky="w", padx=(PAD, 0))

        ttk.Label(ff, text="Files at once:").grid(row=5, column=0, sticky="w", pady=(PAD, 0))
        self.var_workers = tk.StringVar()
        workers = ttk.Frame(ff)
        workers.grid(row=5, column=1, columnspan=3, sticky="w", padx=(PAD, 0), pady=(PAD, 0))
        sp = ttk.Spinbox(workers, from_=1, to=MAX_WORKERS, width=4, textvariable=self.var_workers)
        sp.grid(row=0, column=0)
        ttk.Label(workers, text="Parallel reads. Lower for slow drives.", foreground="gray",
                  ).grid(row=0, column=1, padx=(PAD, 0))
        self.spinboxes = [sp]

        # Report: what the workbook looks like
        of = ttk.LabelFrame(root, text="Report", padding=PAD)
        of.grid(row=1, column=0, sticky="ew", padx=PAD, pady=(PAD, 0))
        of.columnconfigure(1, weight=1)

        ttk.Label(of, text="Save reports to:").grid(row=0, column=0, sticky="w")
        self.var_export = tk.StringVar()
        self.ent_export = ttk.Entry(of, textvariable=self.var_export)
        self.ent_export.grid(row=0, column=1, sticky="ew", padx=(PAD, 4))
        self.btn_browse = ttk.Button(of, text="Browse...", command=self.browse_export)
        self.btn_browse.grid(row=0, column=2)
        ttk.Button(of, text="Open folder", command=self.open_export_folder).grid(row=0, column=3, padx=(4, 0))
        ttk.Label(of, text="If left empty, reports are saved to an 'export' folder next to the app.",
                  foreground="gray").grid(row=1, column=1, columnspan=3, sticky="w", padx=(PAD, 0))

        nums = ttk.Frame(of)
        nums.grid(row=2, column=0, columnspan=4, sticky="w", pady=(PAD, 0))
        self.var_audio = tk.StringVar()
        self.var_subs = tk.StringVar()
        for col, (label, var) in enumerate([
            ("Max audio columns", self.var_audio),
            ("Max subtitle columns", self.var_subs),
        ]):
            ttk.Label(nums, text=label).grid(row=0, column=col * 2, sticky="w", padx=(0 if col == 0 else 16, 4))
            sp = ttk.Spinbox(nums, from_=0, to=MAX_TRACK_COLS, width=4, textvariable=var)
            sp.grid(row=0, column=col * 2 + 1, sticky="w")
            self.spinboxes.append(sp)
        ttk.Label(of, text="Tracks beyond the maximum are left out of the report (0 = no maximum).",
                  foreground="gray").grid(row=3, column=0, columnspan=4, sticky="w")

        self.var_split = tk.BooleanVar()
        self.chk_split = ttk.Checkbutton(
            of, text="Separate columns for each audio/subtitle detail "
                     "(Audio 1 Language, Audio 1 Codec, Audio 1 Channels, ...)",
            variable=self.var_split)
        self.chk_split.grid(row=4, column=0, columnspan=4, sticky="w", pady=(PAD, 0))

        # Run controls
        rf = ttk.Frame(root, padding=(PAD, PAD, PAD, 0))
        rf.grid(row=2, column=0, sticky="ew")
        rf.columnconfigure(2, weight=1)
        self.btn_start = ttk.Button(rf, text="Start scan", command=self.start)
        self.btn_start.grid(row=0, column=0)
        self.btn_cancel = ttk.Button(rf, text="Cancel", command=self.cancel)
        self.btn_cancel.grid(row=0, column=1, padx=(4, 0))
        self.btn_open_report = ttk.Button(rf, text="Open report", command=self.open_report)
        self.btn_open_report.grid(row=0, column=3)
        self.progress = ttk.Progressbar(rf, mode="determinate")
        self.progress.grid(row=1, column=0, columnspan=4, sticky="ew", pady=(PAD, 0))
        self.var_status = tk.StringVar(value="Ready.")
        ttk.Label(rf, textvariable=self.var_status, anchor="w").grid(
            row=2, column=0, columnspan=4, sticky="ew", pady=(4, 0))

        # Log
        lf = ttk.LabelFrame(root, text="Log", padding=4)
        lf.grid(row=3, column=0, sticky="nsew", padx=PAD, pady=PAD)
        lf.columnconfigure(0, weight=1)
        lf.rowconfigure(0, weight=1)
        self.log_text = ScrolledText(lf, height=10, wrap="none", state="disabled")
        self.log_text.grid(row=0, column=0, sticky="nsew")
        self.log_text.tag_configure("error", foreground="#b00020")

    # ------------------------------------------------------------------ options <-> widgets

    def _load_into_widgets(self) -> None:
        o = self.opts
        self.folder_list.delete(0, "end")
        for f in o.folders:
            self.folder_list.insert("end", f)
        self.var_export.set(o.export_folder)
        self.var_audio.set(str(o.max_audio))
        self.var_subs.set(str(o.max_subs))
        self.var_workers.set(str(o.workers))
        self.var_split.set(o.split_tracks)
        self.var_extras.set(", ".join(o.extras_folders))

    @staticmethod
    def _int(var: tk.StringVar, default: int, lo: int, hi: int) -> int:
        """Spinbox value clamped to [lo, hi]; bad text becomes default. Writes the result back."""
        try:
            value = min(hi, max(lo, int(var.get().strip())))
        except ValueError:
            value = default
        var.set(str(value))
        return value

    def _options_from_widgets(self) -> Options:
        o = self.opts
        return Options(
            folders=list(self.folder_list.get(0, "end")),
            export_folder=self.var_export.get().strip(),
            max_audio=self._int(self.var_audio, min(o.max_audio, MAX_TRACK_COLS), 0, MAX_TRACK_COLS),
            max_subs=self._int(self.var_subs, min(o.max_subs, MAX_TRACK_COLS), 0, MAX_TRACK_COLS),
            split_tracks=bool(self.var_split.get()),
            extras_folders=parse_extras(self.var_extras.get()),
            workers=self._int(self.var_workers, min(o.workers, MAX_WORKERS), 1, MAX_WORKERS),
        )

    def _save_settings(self) -> None:
        self.opts = self._options_from_widgets()
        try:
            settings.save(self.opts)
        except OSError as e:
            self.log(f"Couldn't save settings: {e}", error=True)

    # ------------------------------------------------------------------ actions

    def add_folder(self) -> None:
        start = self.folder_list.get("end") or None
        chosen = ask_directories(self.root, "Add folders to scan", initialdir=start)
        have = {os.path.normcase(d) for d in self.folder_list.get(0, "end")}
        added = False
        for d in chosen:
            d = str(Path(d))
            if os.path.normcase(d) not in have:
                have.add(os.path.normcase(d))
                self.folder_list.insert("end", d)
                added = True
        if added:
            self._save_settings()

    def remove_folders(self) -> None:
        if self.worker:
            return
        sel = list(self.folder_list.curselection())
        for i in reversed(sel):
            self.folder_list.delete(i)
        if sel:
            self._save_settings()

    def clear_folders(self) -> None:
        if self.worker or not self.folder_list.size():
            return
        self.folder_list.delete(0, "end")
        self._save_settings()

    def browse_export(self) -> None:
        d = filedialog.askdirectory(parent=self.root, title="Save reports to")
        if d:
            self.var_export.set(str(Path(d)))
            self._save_settings()

    def open_export_folder(self) -> None:
        folder, note = self._options_from_widgets().export_dir()
        if note:
            self.log(note)
        self._open(folder)

    def open_report(self) -> None:
        if self.last_report:
            self._open(self.last_report)

    def _open(self, path: Path) -> None:
        try:
            open_path(path)
        except OSError as e:
            self.log(f"Couldn't open {path}: {e}", error=True)

    def start(self) -> None:
        if self.worker:
            return
        missing = _missing_deps()
        if missing:
            messagebox.showerror(APP_NAME, "Missing package(s): " + ", ".join(missing)
                                 + "\n\nInstall with:\npy -m pip install " + " ".join(missing),
                                 parent=self.root)
            return
        self._save_settings()
        if not self.opts.folders:
            messagebox.showinfo(APP_NAME, "Add at least one folder to scan.", parent=self.root)
            return

        self.cancel_event = threading.Event()
        self.last_report = None
        self.progress.configure(value=0, maximum=1)
        self.var_status.set("Looking for video files...")
        self.log("-" * 40)
        export_dir, note = self.opts.export_dir()
        self.log(note or f"Reports will be saved to {export_dir}")
        self._set_running(True)

        opts = self.opts
        q = self.queue
        cancel = self.cancel_event

        def work():
            try:
                res = run_job(opts,
                              log=lambda m: q.put(("log", m)),
                              progress=lambda d, t, p, e: q.put(("progress", d, t, p, e)),
                              cancel_event=cancel)
            except Exception:
                q.put(("log_error", traceback.format_exc().rstrip()))
                res = JobResult(status="failed", message="The scan failed unexpectedly.")
            q.put(("finished", res))

        self.worker = threading.Thread(target=work, name="scan", daemon=True)
        self.worker.start()

    def cancel(self) -> None:
        if self.worker and not self.cancel_event.is_set():
            self.cancel_event.set()
            self.var_status.set("Cancelling... (waiting for files being read to finish)")
            self.btn_cancel.state(["disabled"])

    def on_close(self) -> None:
        if self.worker:
            if not messagebox.askyesno(APP_NAME, "A scan is running. Cancel it and quit?\n\n"
                                       "No report will be written.", parent=self.root):
                return
            if not self.worker:      # the scan finished while the dialog was open
                self._quit()
                return
            self.closing = True
            self.cancel()
            return  # _poll destroys the window once the worker has stopped
        self._quit()

    def _quit(self) -> None:
        self._save_settings()
        self.closed = True
        self.root.after_cancel(self._after_id)
        self.root.destroy()

    def on_tk_error(self, exc, val, tb) -> None:
        text = "".join(traceback.format_exception(exc, val, tb)).rstrip()
        self.log(text, error=True)
        messagebox.showerror(APP_NAME, f"Unexpected error:\n{val}", parent=self.root)

    # ------------------------------------------------------------------ queue / UI updates

    def _poll(self) -> None:
        try:
            self._drain_queue()
        finally:
            # Always reschedule, so one bad message can't freeze the UI.
            if not self.closed:
                self._after_id = self.root.after(POLL_MS, self._poll)

    def _drain_queue(self) -> None:
        """Apply queued worker messages to the UI."""
        lines: list[tuple[str, bool]] = []
        latest_progress = None
        finished: JobResult | None = None
        try:
            while True:
                msg = self.queue.get_nowait()
                kind = msg[0]
                if kind == "log":
                    lines.append((msg[1], False))
                elif kind == "log_error":
                    lines.append((msg[1], True))
                elif kind == "progress":
                    _, done, total, path, err = msg
                    latest_progress = (done, total, path)
                    if err:
                        lines.append((f"[{done}/{total}] {path.name}  -  {err}", True))
                    else:
                        lines.append((f"[{done}/{total}] {path.name}", False))
                elif kind == "finished":
                    finished = msg[1]
        except queue.Empty:
            pass

        if lines:
            self._append_log(lines)
        if latest_progress:
            done, total, path = latest_progress
            self.progress.configure(maximum=max(total, 1), value=done)
            self.var_status.set(f"Scanning {done} / {total}  -  {path.name}"
                                if not self.cancel_event.is_set() else
                                "Cancelling... (waiting for files being read to finish)")
        if finished:
            self._finished(finished)
            if self.closing:
                self.closed = True
                self.root.destroy()  # settings were saved when the scan started

    def _finished(self, res: JobResult) -> None:
        self.worker = None
        self._set_running(False)
        if res.status == DONE:
            self.last_report = res.report
            self.progress.configure(value=self.progress["maximum"])
        elif res.status == CANCELLED:
            self.progress.configure(value=0)
        self.var_status.set(res.message)
        self.btn_open_report.state(["!disabled"] if self.last_report else ["disabled"])

    def _set_running(self, running: bool) -> None:
        on, off = (["disabled"], ["!disabled"]) if running else (["!disabled"], ["disabled"])
        for w in (self.btn_start, self.btn_add, self.btn_remove, self.btn_clear, self.btn_browse,
                  self.ent_export, self.ent_extras, self.chk_split, *self.spinboxes):
            w.state(on)
        self.btn_cancel.state(off)
        self.folder_list.configure(state="disabled" if running else "normal")
        if running:
            self.btn_open_report.state(["disabled"])

    def log(self, text: str, error: bool = False) -> None:
        self._append_log([(text, error)])

    def _append_log(self, lines: list[tuple[str, bool]]) -> None:
        t = self.log_text
        at_bottom = t.yview()[1] >= 0.999
        t.configure(state="normal")
        for text, error in lines:
            t.insert("end", text + "\n", ("error",) if error else ())
        excess = int(t.index("end-1c").split(".")[0]) - MAX_LOG_LINES
        if excess > 0:
            t.delete("1.0", f"{excess + 1}.0")
        t.configure(state="disabled")
        if at_bottom:
            t.see("end")


def _enable_hidpi() -> None:
    if sys.platform == "win32":
        try:
            import ctypes
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except (AttributeError, OSError):
            pass


def main() -> int:
    _enable_hidpi()
    root = tk.Tk()
    style = ttk.Style(root)
    if style.theme_use() == "default" and "clam" in style.theme_names():
        style.theme_use("clam")   # nicer than Tk's 'default' on Linux
    App(root)
    root.mainloop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
