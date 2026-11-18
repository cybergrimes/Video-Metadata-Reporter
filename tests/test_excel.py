import tempfile
import unittest
from pathlib import Path

from mediareport import core, excel
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


class TestIncludeType(unittest.TestCase):
    def test_type_column_omitted(self):
        r = rec("a", 1, 0)
        r.type = "Extras"
        ws = excel.build_workbook([r], [], excel.ExcelOptions(include_type=False))["Library"]
        out = rows(ws)
        self.assertEqual(out[0][:4], ["Folder", "File", "Container", "Size (GB)"])
        self.assertNotIn("Type", out[0])
        self.assertEqual(len(out[0]), len(BASE_COLUMNS) - 1 + 1)
        self.assertEqual(out[1][:3], ["D:/x", "a", None])      # Container is None for this fake record
        self.assertNotIn("Extras", out[1])

    def test_type_column_kept_by_default(self):
        self.assertIn("Type", rows(excel.build_workbook([rec("a", 0, 0)], [])["Library"])[0])

    def test_split_and_freeze_unaffected(self):
        ws = excel.build_workbook([rec("a", 1, 1)], [],
                                  excel.ExcelOptions(include_type=False, split_tracks=True))["Library"]
        self.assertEqual(ws.freeze_panes, "C2")
        self.assertNotIn("Type", rows(ws)[0])


class TestSplitTracks(unittest.TestCase):
    def build(self, **kw):
        r = FileRecord(folder="D:/x", file="a.mkv",
                       audio=["mixed a1", "mixed a2"], subs=["mixed s1"],
                       audio_split=[["English", "AC-3", "5.1", "640 kb/s", "Main", "Default"],
                                    ["French", "AAC", "2.0", "128 kb/s", "", ""]],
                       subs_split=[["English", "PGS", "SDH", "", "Default"]])
        r2 = FileRecord(folder="D:/x", file="b.mkv", audio=["m"], audio_split=[["de", "AC-3", "", "", "", ""]])
        return excel.build_workbook([r, r2], [], excel.ExcelOptions(split_tracks=True, **kw))["Library"]

    def test_headers_grouped_by_track(self):
        r = rows(self.build())
        n = len(BASE_COLUMNS)
        expect = ([f"Audio {i} {f}" for i in (1, 2) for f in core.AUDIO_FIELDS]
                  + [f"Sub 1 {f}" for f in core.SUB_FIELDS])
        self.assertEqual(r[0][n:], expect)

    def test_values_and_padding(self):
        r = rows(self.build())
        n = len(BASE_COLUMNS)
        self.assertEqual(r[1][n:n + 6], ["English", "AC-3", "5.1", "640 kb/s", "Main", "Default"])
        self.assertEqual(r[1][-5:], ["English", "PGS", "SDH", "", "Default"])
        self.assertEqual(r[2][n + 6:n + 12], [""] * 6)       # file b has no 2nd audio
        self.assertEqual(r[2][-5:], [""] * 5)

    def test_caps_and_counts(self):
        ws = self.build(max_audio=1, max_subs=0)
        r = rows(ws)
        self.assertEqual(len(r[0]), len(BASE_COLUMNS) + 6 + 5)
        self.assertEqual(r[1][BASE_COLUMNS.index("# Audio")], 2)

    def test_off_by_default(self):
        ws = excel.build_workbook([FileRecord(folder="D:/x", file="a", audio=["m"])], [])["Library"]
        self.assertEqual(rows(ws)[0][-1], "Audio 1")


class TestAutofit(unittest.TestCase):
    def width(self, ws, header):
        letter = next(c.column_letter for c in ws[1] if c.value == header)
        return ws.column_dimensions[letter].width

    def test_long_values_are_not_capped(self):
        long_folder = "D:/" + "x" * 150
        r = FileRecord(folder=long_folder, file="a.mkv", audio=["English | " + "y" * 90])
        ws = excel.build_workbook([r], [])["Library"]
        self.assertEqual(self.width(ws, "Folder"), len(long_folder) + excel.PADDING)
        self.assertEqual(self.width(ws, "Audio 1"), 100 + excel.PADDING)

    def test_header_gets_room_for_filter_button(self):
        ws = excel.build_workbook([rec("a", 0, 0)], [])["Library"]
        self.assertEqual(self.width(ws, "HDR"), len("HDR") + excel.FILTER_BUTTON + excel.PADDING)

    def test_all_rows_measured(self):
        recs = [rec(f"f{i}", 0, 0) for i in range(600)]
        recs.append(FileRecord(folder="D:/x", file="z" * 80))   # row 602, past the old 500-row sample
        ws = excel.build_workbook(recs, [])["Library"]
        self.assertEqual(self.width(ws, "File"), 80 + excel.PADDING)

    def test_errors_sheet_autofit(self):
        wb = excel.build_workbook([], [ScanError("D:/" + "p" * 70, "boom")])
        es = wb["Errors"]
        self.assertEqual(es.column_dimensions["A"].width, 73 + excel.PADDING)
        self.assertEqual(es.column_dimensions["B"].width, len("Error") + excel.PADDING)


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
