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
            p.write_text("[Media Report]\nworkers = 100000\n", encoding="utf-8")
            self.assertEqual(settings.load(p).workers, settings.MAX_WORKERS)


if __name__ == "__main__":
    unittest.main()
