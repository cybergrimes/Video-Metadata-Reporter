"""Multi-select folder dialog.

On Windows this is the standard system folder dialog (IFileOpenDialog with the pick-folders and
multi-select options), so Ctrl-click / Shift-click work as usual. Elsewhere, or if the system
dialog can't be created, it falls back to Tk's single-folder dialog.
GUI-only; nothing else in the package uses it.
"""
from __future__ import annotations

import os
import tkinter as tk
from tkinter import filedialog

_CANCELLED = 0x800704C7          # HRESULT_FROM_WIN32(ERROR_CANCELLED)
_FOS_PICKFOLDERS = 0x20
_FOS_FORCEFILESYSTEM = 0x40
_FOS_ALLOWMULTISELECT = 0x200
_FOS_PATHMUSTEXIST = 0x800
_SIGDN_FILESYSPATH = 0x80058000


def ask_directories(parent: tk.Misc, title: str = "Add folders", initialdir: str | None = None) -> list[str]:
    """Return the folders the user chose (empty list if cancelled)."""
    if os.name == "nt":
        try:
            return _windows_dialog(parent, title, initialdir)
        except Exception:
            pass   # fall through to the single-folder dialog
    d = filedialog.askdirectory(parent=parent, title=title, initialdir=initialdir, mustexist=True)
    return [d] if d else []


def _windows_dialog(parent: tk.Misc, title: str, initialdir: str | None) -> list[str]:
    import ctypes
    from ctypes import POINTER, byref, c_void_p, c_wchar_p, windll, wintypes

    class GUID(ctypes.Structure):
        _fields_ = [("a", ctypes.c_uint32), ("b", ctypes.c_uint16), ("c", ctypes.c_uint16),
                    ("d", ctypes.c_ubyte * 8)]

    def guid(text: str) -> GUID:
        g = GUID()
        hr = windll.ole32.CLSIDFromString(c_wchar_p("{" + text + "}"), byref(g))
        if hr:
            raise OSError(f"bad GUID {text}")
        return g

    def call(obj, index: int, restype, *argtypes):
        """Bind method `index` of COM object `obj` (a pointer to a vtable pointer)."""
        vtbl = ctypes.cast(obj, POINTER(POINTER(c_void_p))).contents
        return ctypes.WINFUNCTYPE(restype, c_void_p, *argtypes)(vtbl[index])

    def check(hr: int, what: str) -> None:
        if hr < 0:
            raise OSError(f"{what} failed: 0x{hr & 0xFFFFFFFF:08X}")

    def release(obj) -> None:
        if obj:
            call(obj, 2, ctypes.c_ulong)(obj)

    windll.ole32.CoInitialize(None)   # harmless if this thread is already initialised

    dialog = c_void_p()
    check(windll.ole32.CoCreateInstance(
        byref(guid("DC1C5A9C-E88A-4DDE-A5A1-60F82A20AEF7")), None, 1,          # CLSID_FileOpenDialog, INPROC
        byref(guid("D57C7288-D4AD-4768-BE02-9D969532D960")), byref(dialog)),   # IID_IFileOpenDialog
        "CoCreateInstance")
    try:
        opts = wintypes.DWORD()
        check(call(dialog, 10, ctypes.c_long, POINTER(wintypes.DWORD))(dialog, byref(opts)), "GetOptions")
        flags = opts.value | _FOS_PICKFOLDERS | _FOS_ALLOWMULTISELECT | _FOS_FORCEFILESYSTEM | _FOS_PATHMUSTEXIST
        check(call(dialog, 9, ctypes.c_long, wintypes.DWORD)(dialog, flags), "SetOptions")
        check(call(dialog, 17, ctypes.c_long, c_wchar_p)(dialog, title), "SetTitle")
        check(call(dialog, 18, ctypes.c_long, c_wchar_p)(dialog, "Add"), "SetOkButtonLabel")

        if initialdir and os.path.isdir(initialdir):
            item = c_void_p()
            hr = windll.shell32.SHCreateItemFromParsingName(
                c_wchar_p(os.path.abspath(initialdir)), None,
                byref(guid("43826D1E-E718-42EE-BC55-A1E261C37BFE")), byref(item))   # IID_IShellItem
            if hr >= 0 and item:
                call(dialog, 12, ctypes.c_long, c_void_p)(dialog, item)             # SetFolder
                release(item)

        hwnd = wintypes.HWND(parent.winfo_id())
        hr = call(dialog, 3, ctypes.c_long, wintypes.HWND)(dialog, hwnd) & 0xFFFFFFFF   # Show
        if hr == _CANCELLED:
            return []
        check(hr - (1 << 32) if hr & 0x80000000 else hr, "Show")

        results = c_void_p()
        check(call(dialog, 27, ctypes.c_long, POINTER(c_void_p))(dialog, byref(results)), "GetResults")
        try:
            count = wintypes.DWORD()
            check(call(results, 7, ctypes.c_long, POINTER(wintypes.DWORD))(results, byref(count)), "GetCount")
            paths: list[str] = []
            for i in range(count.value):
                item = c_void_p()
                check(call(results, 8, ctypes.c_long, wintypes.DWORD, POINTER(c_void_p))(
                    results, i, byref(item)), "GetItemAt")
                try:
                    name = c_wchar_p()
                    check(call(item, 5, ctypes.c_long, wintypes.DWORD, POINTER(c_wchar_p))(
                        item, _SIGDN_FILESYSPATH, byref(name)), "GetDisplayName")
                    if name.value:
                        paths.append(name.value)
                    windll.ole32.CoTaskMemFree(name)
                finally:
                    release(item)
            return paths
        finally:
            release(results)
    finally:
        release(dialog)
