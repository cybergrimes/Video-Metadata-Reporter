import tempfile
import unittest
from pathlib import Path

from mediareport import excel
from mediareport.core import BASE_COLUMNS, FileRecord, ScanError


def rec(name, a, s):
    return FileRecord(folder="D:/x", file=name,
                      audio=[f"a{i}" for i in range(a)], subs=[f"s{i}" for i in range(s)])


def rows(ws):
    return [[c.value for c in row] for row in ws.iter_rows()]


class TestWorkbook(unittest.TestCase):
    def test_header_and_padding(self):
        wb = excel.build_workbook([rec("a", 1, 3), rec("b", 2, 0)], [])
        r = rows(wb["Library"])
        self.assertEqual(r[0], BASE_COLUMNS + ["Audio 1", "Audio 2", "Sub 1", "Sub 2", "Sub 3"])
        n = len(BASE_COLUMNS)
        self.assertEqual(r[1][n:], ["a0", "", "s0", "s1", "s2"])
        self.assertEqual(r[2][n:], ["a0", "a1", "", "", ""])
        self.assertEqual(r[1][BASE_COLUMNS.index("# Audio")], 1)
        self.assertEqual(r[1][BASE_COLUMNS.index("# Subs")], 3)

    def test_padding_is_empty_string_in_memory(self):
        ws = excel.build_workbook([rec("a", 1, 0), rec("b", 2, 0)], [])["Library"]
        self.assertIn(ws.cell(row=2, column=len(BASE_COLUMNS) + 2).value, ("", None))

    def test_caps_keep_true_count(self):
        wb = excel.build_workbook([rec("a", 5, 4)], [], excel.ExcelOptions(max_audio=2, max_subs=1))
        r = rows(wb["Library"])
        self.assertEqual(r[0][len(BASE_COLUMNS):], ["Audio 1", "Audio 2", "Sub 1"])
        self.assertEqual(r[1][BASE_COLUMNS.index("# Audio")], 5)
        self.assertEqual(r[1][BASE_COLUMNS.index("# Subs")], 4)
        self.assertEqual(r[1][len(BASE_COLUMNS):], ["a0", "a1", "s0"])

    def test_cap_larger_than_actual(self):
        wb = excel.build_workbook([rec("a", 1, 1)], [], excel.ExcelOptions(max_audio=9, max_subs=9))
        self.assertEqual(rows(wb["Library"])[0][len(BASE_COLUMNS):], ["Audio 1", "Sub 1"])

    def test_formatting(self):
        ws = excel.build_workbook([rec("a", 1, 1)], [])["Library"]
        self.assertEqual(ws.freeze_panes, "C2")
        self.assertTrue(ws.auto_filter.ref)
        self.assertTrue(all(c.font.bold for c in ws[1]))

    def test_errors_sheet(self):
        wb = excel.build_workbook([rec("a", 1, 1)], [])
        self.assertEqual(wb.sheetnames, ["Library"])
        wb = excel.build_workbook([rec("a", 1, 1)], [ScanError("p.mkv", "bad")])
        self.assertEqual(wb.sheetnames, ["Library", "Errors"])
        self.assertEqual(rows(wb["Errors"]), [["File", "Error"], ["p.mkv", "bad"]])

    def test_zero_records(self):
        wb = excel.build_workbook([], [])
        self.assertEqual(rows(wb["Library"]), [BASE_COLUMNS])
        wb = excel.build_workbook([], [ScanError("p", "m")])
        self.assertIn("Errors", wb.sheetnames)

    def test_write_workbook(self):
        with tempfile.TemporaryDirectory() as d:
            p = excel.write_workbook([rec("a", 1, 1)], [], Path(d) / "new" / "r.xlsx")
            self.assertTrue(p.exists())


class TestUniquePath(unittest.TestCase):
    def test_unique(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "r.xlsx"
            self.assertEqual(excel.unique_path(p), p)
            p.write_bytes(b"")
            self.assertEqual(excel.unique_path(p), Path(d) / "r (2).xlsx")
            (Path(d) / "r (2).xlsx").write_bytes(b"")
            self.assertEqual(excel.unique_path(p), Path(d) / "r (3).xlsx")


if __name__ == "__main__":
    unittest.main()
