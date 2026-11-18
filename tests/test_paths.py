import tempfile
import unittest
from pathlib import Path
from unittest import mock

from mediareport import paths


class TestResolveExportDir(unittest.TestCase):
    def test_relative_under_app_dir(self):
        with tempfile.TemporaryDirectory() as d:
            app = Path(d)
            with mock.patch.object(paths, "app_dir", return_value=app):
                p, note = paths.resolve_export_dir("out/reports")
                self.assertEqual(p, app / "out" / "reports")
                self.assertIsNone(note)
                self.assertTrue(p.is_dir())

    def test_empty_means_export(self):
        with tempfile.TemporaryDirectory() as d:
            with mock.patch.object(paths, "app_dir", return_value=Path(d)):
                p, note = paths.resolve_export_dir("  ")
                self.assertEqual(p, Path(d) / "export")
                self.assertIsNone(note)

    def test_absolute(self):
        with tempfile.TemporaryDirectory() as d, tempfile.TemporaryDirectory() as app:
            with mock.patch.object(paths, "app_dir", return_value=Path(app)):
                p, note = paths.resolve_export_dir(str(Path(d) / "x"))
                self.assertEqual(p, Path(d) / "x")
                self.assertIsNone(note)

    def test_fallback(self):
        with tempfile.TemporaryDirectory() as d, tempfile.TemporaryDirectory() as docs:
            fb = Path(docs) / "Video Metadata Reporter"
            with mock.patch.object(paths, "app_dir", return_value=Path(d)), \
                 mock.patch.object(paths, "is_writable_dir", return_value=False), \
                 mock.patch.object(paths, "documents_export_dir", return_value=fb):
                p, note = paths.resolve_export_dir("")
                self.assertEqual(p, fb)
                self.assertIn("Can't write", note)
                self.assertIn(str(Path(d) / "export"), note)
                self.assertIn(str(fb), note)

    def test_is_writable_dir(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertTrue(paths.is_writable_dir(Path(d) / "new"))
            f = Path(d) / "file"
            f.write_text("x")
            self.assertFalse(paths.is_writable_dir(f / "sub"))


class TestVendoredMediaInfo(unittest.TestCase):
    def test_found_in_app_dir(self):
        with tempfile.TemporaryDirectory() as d:
            dll = Path(d) / "vendor" / "mediainfo" / "MediaInfo.dll"
            dll.parent.mkdir(parents=True)
            dll.write_bytes(b"")
            with mock.patch.object(paths, "app_dir", return_value=Path(d)), \
                    mock.patch.object(paths.sys, "platform", "win32"):
                self.assertEqual(paths.vendored_mediainfo(), dll)

    def test_missing_gives_none(self):
        with tempfile.TemporaryDirectory() as d:
            with mock.patch.object(paths, "app_dir", return_value=Path(d)), \
                    mock.patch.object(paths.sys, "platform", "win32"):
                self.assertIsNone(paths.vendored_mediainfo())

    def test_non_windows_gives_none(self):
        with mock.patch.object(paths.sys, "platform", "linux"):
            self.assertIsNone(paths.vendored_mediainfo())


if __name__ == "__main__":
    unittest.main()
