import tempfile
import unittest
from datetime import datetime
from pathlib import Path

from mediareport import settings
from mediareport.core import DEFAULT_EXTRAS_FOLDERS


class TestSplitSetting(unittest.TestCase):
    def test_roundtrip_and_bad_value(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "m.ini"
            self.assertFalse(settings.load(p).split_tracks)
            settings.save(settings.Options(split_tracks=True), p)
            self.assertTrue(settings.load(p).split_tracks)
            p.write_text("[Video Metadata Reporter]\nsplit_tracks = banana\n", encoding="utf-8")
            self.assertFalse(settings.load(p).split_tracks)


class TestSettings(unittest.TestCase):
    def setUp(self):
        self._td = tempfile.TemporaryDirectory()
        self.addCleanup(self._td.cleanup)
        self.dir = Path(self._td.name)
        self.ini = self.dir / "settings.ini"

    def test_loads_pre_rename_settings(self):
        old = self.dir / "MediaReport.ini"
        old.write_text("[Media Report]\nmax_audio = 2\nfolders =\n    D:\\Movies\n", encoding="utf-8")
        o = settings.load(self.ini)            # new file missing -> falls back to the old one
        self.assertEqual((o.max_audio, o.folders), (2, ["D:\\Movies"]))
        settings.save(o, self.ini)             # saving writes the new name and section
        self.assertIn("[Video Metadata Reporter]", self.ini.read_text(encoding="utf-8"))

    def test_loads_from_old_config_folder(self):
        old_dir = self.dir / "MediaReport"
        old_dir.mkdir()
        (old_dir / "MediaReport.ini").write_text("[Media Report]
max_subs = 4
", encoding="utf-8")
        new_dir = self.dir / "VideoMetadataReporter"
        new_dir.mkdir()
        self.assertEqual(settings.load(new_dir / "settings.ini").max_subs, 4)

    def test_round_trip(self):
        o = settings.Options(folders=[r"D:\Movies", r"E:\TV Shows"], export_folder=r"D:\Out",
                             max_audio=3, max_subs=6, extras_folders=["extras", "bonus"], workers=8)
        settings.save(o, self.ini)
        self.assertEqual(settings.load(self.ini), o)

    def test_missing_file_defaults(self):
        self.assertEqual(settings.load(self.dir / "nope.ini"), settings.Options())

    def test_defaults_values(self):
        o = settings.Options()
        self.assertEqual((o.folders, o.export_folder, o.max_audio, o.max_subs, o.workers),
                         ([], "", 0, 0, 4))
        self.assertEqual(o.extras_folders, list(DEFAULT_EXTRAS_FOLDERS))

    def test_bad_ints(self):
        self.ini.write_text("[Video Metadata Reporter]\nmax_audio = abc\nmax_subs = 1.5\nworkers = x\n", encoding="utf-8")
        o = settings.load(self.ini)
        self.assertEqual((o.max_audio, o.max_subs, o.workers), (0, 0, 4))

    def test_workers_min_1(self):
        self.ini.write_text("[Video Metadata Reporter]\nworkers = 0\n", encoding="utf-8")
        self.assertEqual(settings.load(self.ini).workers, 1)
        self.ini.write_text("[Video Metadata Reporter]\nworkers = -5\nmax_audio = -2\n", encoding="utf-8")
        o = settings.load(self.ini)
        self.assertEqual((o.workers, o.max_audio), (1, 0))

    def test_percent_and_spaces(self):
        o = settings.Options(folders=["D:\\My 100% Movies\\a b", "/mnt/%USERPROFILE%/x y"],
                             export_folder="C:\\100% out")
        settings.save(o, self.ini)
        got = settings.load(self.ini)
        self.assertEqual(got.folders, o.folders)
        self.assertEqual(got.export_folder, o.export_folder)

    def test_garbage_file(self):
        self.ini.write_bytes(b"\x00\xff\xfe garbage \x80\x81")
        self.assertEqual(settings.load(self.ini), settings.Options())
        self.ini.write_text("this is not an ini\nat all", encoding="utf-8")
        self.assertEqual(settings.load(self.ini), settings.Options())
        self.ini.write_text("[Other]\nfoo = 1\n", encoding="utf-8")
        self.assertEqual(settings.load(self.ini), settings.Options())

    def test_empty_extras_and_folders(self):
        settings.save(settings.Options(folders=[], extras_folders=[]), self.ini)
        got = settings.load(self.ini)
        self.assertEqual(got.folders, [])
        self.assertEqual(got.extras_folders, [])

    def test_save_creates_parent_and_no_tmp(self):
        p = self.dir / "sub" / "settings.ini"
        settings.save(settings.Options(), p)
        self.assertTrue(p.exists())
        self.assertFalse(p.with_name(p.name + ".tmp").exists())

    def test_report_name(self):
        self.assertEqual(settings.Options().report_name(datetime(2026, 1, 2, 3, 4)),
                         "report-2026-01-02_0304.xlsx")


if __name__ == "__main__":
    unittest.main()
