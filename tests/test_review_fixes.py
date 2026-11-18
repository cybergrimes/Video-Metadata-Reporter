import tempfile
import unittest
from pathlib import Path

from mediareport import core, excel, settings
from mediareport.core import BASE_COLUMNS, FileRecord


class TestExcelSafety(unittest.TestCase):
    def test_control_characters_and_surrogates_are_stripped(self):
        r = FileRecord(folder="D:/x", file="a\x01b\udc80.mkv", audio=["x\x00y"], subs=[])
        wb = excel.build_workbook([r], [])
        ws = wb["Library"]
        self.assertEqual(ws.cell(row=2, column=2).value, "ab.mkv")
        with tempfile.TemporaryDirectory() as d:
            excel.write_workbook([r], [], Path(d) / "r.xlsx")    # must not raise

    def test_equals_prefixed_text_is_not_a_formula(self):
        r = FileRecord(folder="D:/x", file="=1+1.mkv", audio=["=HYPERLINK(1)"], audio_split=[["", "", "", "", "=A1", ""]])
        ws = excel.build_workbook([r], [])["Library"]
        self.assertEqual(ws.cell(row=2, column=2).data_type, "s")
        self.assertEqual(ws.cell(row=2, column=len(BASE_COLUMNS) + 1).data_type, "s")

    def test_negative_caps_are_ignored(self):
        r = FileRecord(folder="D:/x", file="a", audio=["a0", "a1"], subs=["s0"])
        ws = excel.build_workbook([r], [], excel.ExcelOptions(max_audio=-1, max_subs=-1))["Library"]
        row = [c.value for c in ws[2]][len(BASE_COLUMNS):]
        self.assertEqual(row, ["a0", "a1", 1, "s0"])


class TestMisc(unittest.TestCase):
    def test_apostrophe_folder_name(self):
        p = Path("D:/L/director's cut/a.mkv")
        self.assertEqual(core.content_type(p, ["Director's Cut"], Path("D:/L")), "Director's Cut")

    def test_find_files_reports_unreadable_folders(self):
        errors = []
        core.find_files([Path(tempfile.gettempdir()) / "no-such-folder-xyz"], on_error=errors.append)
        self.assertEqual(len(errors), 1)

    def test_workers_capped_on_load(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "x.ini"
            p.write_text("[Video Metadata Reporter]\nworkers = 100000\n", encoding="utf-8")
            self.assertEqual(settings.load(p).workers, settings.MAX_WORKERS)


if __name__ == "__main__":
    unittest.main()


class TestRenamedColumns(unittest.TestCase):
    def test_category_and_split_headers(self):
        r = FileRecord(folder="D:/x", file="a", audio=["a"], subs=["s"],
                       audio_split=[["", "", "", "", "", ""]], subs_split=[["", "", "", "", ""]])
        hdr = [c.value for c in excel.build_workbook([r], [], excel.ExcelOptions(split_tracks=True))["Library"][1]]
        self.assertIn("Category", hdr)
        self.assertNotIn("Type", hdr)
        self.assertIn("Audio 1 codec", hdr)
        self.assertIn("Sub 1 format", hdr)
        self.assertNotIn("Audio 1 Type", hdr)


class TestNewColumnsAndSelection(unittest.TestCase):
    def test_new_columns_follow_container(self):
        i = BASE_COLUMNS.index("Container")
        self.assertEqual(BASE_COLUMNS[i + 1:i + 4], ["Encoded date", "Writing application", "Writing library"])

    def test_record_reads_general_track(self):
        from types import SimpleNamespace as NS
        gen = NS(track_type="General", format="Matroska", encoded_date="2021-03-14 09:12:33 UTC",
                 writing_application="mkvmerge v60", writing_library="libebml v1.4.2")
        r = core.record_from_tracks(Path("D:/L/a.mkv"), [gen])
        self.assertEqual((r.encoded_date, r.writing_app, r.writing_lib),
                         ("2021-03-14", "mkvmerge 60", "libebml v1.4.2"))
        self.assertEqual(core.date_only("UTC 2019-12-01 23:59:59"), "2019-12-01")
        self.assertEqual(core.date_only(None), "")
        self.assertEqual(r.base_values()[BASE_COLUMNS.index("Writing application")], "mkvmerge 60")
        blank = core.record_from_tracks(Path("D:/L/a.mkv"), [NS(track_type="General")])
        self.assertEqual((blank.encoded_date, blank.writing_app, blank.writing_lib), ("", "", ""))

    def test_hidden_columns(self):
        r = FileRecord(folder="D:/x", file="a", writing_app="app", audio=["a0"], subs=["s0"])
        opts = excel.ExcelOptions(hidden_columns=frozenset({"container", "Writing library", "Size (GB)"}))
        hdr = [c.value for c in excel.build_workbook([r], [], opts)["Library"][1]]
        for gone in ("Container", "Writing library", "Size (GB)"):
            self.assertNotIn(gone, hdr)
        self.assertEqual(hdr[:5], ["Folder", "File", "Category", "Encoded date", "Writing application"])
        row = [c.value for c in excel.build_workbook([r], [], opts)["Library"][2]]
        self.assertEqual(len(row), len(hdr))
        self.assertEqual(row[hdr.index("Writing application")], "app")

    def test_folder_and_file_cannot_be_hidden(self):
        r = FileRecord(folder="D:/x", file="a")
        hdr = [c.value for c in excel.build_workbook(
            [r], [], excel.ExcelOptions(hidden_columns=frozenset({"Folder", "File"})))["Library"][1]]
        self.assertEqual(hdr[:2], ["Folder", "File"])
        self.assertNotIn("Folder", core.OPTIONAL_COLUMNS)

    def test_hide_track_groups(self):
        r = FileRecord(folder="D:/x", file="a", audio=["a0"], subs=["s0"],
                       audio_split=[["", "", "", "", "", ""]], subs_split=[["", "", "", "", ""]])
        for split in (False, True):
            opts = excel.ExcelOptions(split_tracks=split, hidden_columns=frozenset({"Audio"}))
            ws = excel.build_workbook([r], [], opts)["Library"]
            hdr = [c.value for c in ws[1]]
            self.assertFalse([h for h in hdr if h.startswith("Audio") or h == "# Audio"])
            self.assertIn("# Subs", hdr)
            self.assertEqual(len([c.value for c in ws[2]]), len(hdr))
            opts = excel.ExcelOptions(split_tracks=split, hidden_columns=frozenset({"Subtitles"}))
            hdr = [c.value for c in excel.build_workbook([r], [], opts)["Library"][1]]
            self.assertFalse([h for h in hdr if h.startswith("Sub") or h == "# Subs"])
            self.assertIn("# Audio", hdr)

    def test_hide_everything_optional(self):
        r = FileRecord(folder="D:/x", file="a", audio=["a0"], subs=["s0"])
        opts = excel.ExcelOptions(hidden_columns=frozenset(core.OPTIONAL_COLUMNS))
        ws = excel.build_workbook([r], [], opts)["Library"]
        self.assertEqual([c.value for c in ws[1]], ["Folder", "File"])
        self.assertEqual([c.value for c in ws[2]], ["D:/x", "a"])

    def test_normalize(self):
        self.assertEqual(core.normalize_hidden_columns(["writing library", " CONTAINER ", "bogus", "Folder"]),
                         ["Container", "Writing library"])

    def test_settings_round_trip(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "m.ini"
            settings.save(settings.Options(hidden_columns=["Writing library", "Audio"]), p)
            self.assertEqual(settings.load(p).hidden_columns, ["Writing library", "Audio"])
            self.assertEqual(settings.load(Path(d) / "none.ini").hidden_columns, [])
            p.write_text("[Video Metadata Reporter]\nhidden_columns = frame rate, nonsense, folder\n", encoding="utf-8")
            self.assertEqual(settings.load(p).hidden_columns, ["Frame rate"])

    def test_cli_rejects_unknown_column(self):
        from mediareport import cli
        import contextlib, io
        with self.assertRaises(SystemExit), contextlib.redirect_stderr(io.StringIO()):
            cli.main(["D:/x", "--hide-columns", "Bogus"])
