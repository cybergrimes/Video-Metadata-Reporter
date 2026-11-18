"""Video Metadata Reporter - GUI launcher (no console window on Windows).

    py VideoMetadataReporter.pyw
"""
import sys
import traceback


def _report_startup_failure() -> None:
    """There's no console under pythonw, so show the error and keep a copy on disk."""
    text = traceback.format_exc()
    try:
        from mediareport.paths import user_config_dir
        log = user_config_dir() / "startup-error.log"
        log.parent.mkdir(parents=True, exist_ok=True)
        log.write_text(text, encoding="utf-8")
        text += f"\n(Saved to {log})"
    except Exception:
        pass
    try:
        import tkinter as tk
        from tkinter import messagebox
        root = tk.Tk()
        root.withdraw()
        messagebox.showerror("Video Metadata Reporter could not start", text[-2000:])
        root.destroy()
    except Exception:
        print(text, file=sys.stderr)


if __name__ == "__main__":
    try:
        from mediareport.gui import main
        code = main()
    except Exception:
        _report_startup_failure()
        code = 1
    sys.exit(code)
