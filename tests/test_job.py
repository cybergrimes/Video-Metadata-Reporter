import tempfile
import threading
import time
import unittest
from datetime import datetime
from pathlib import Path
from unittest import mock

import openpyxl

from mediareport import job
from mediareport.core import FileRecord
from mediareport.settings import Options

NOW = datetime(2024, 5, 6, 7, 8)
STAMP_NAME = "report-2024-05-06_0708.xlsx"


def fake_scan(path, extras):
    if path.name == "bad.mkv":
        raise RuntimeError("corrupt")
    return FileRecord(folder=str(path.parent), file=path.name)


class JobTestBase(unittest.TestCase):
    def setUp(self):
        self._td = tempfile.TemporaryDirectory()
        self.addCleanup(self._td.cleanup)
        root = Path(self._td.name)
        self.lib = root / "lib"
        self.export = root / "out"
        self.export.mkdir()
        (self.lib / "Extras").mkdir(parents=True)
        for rel in ("a.mkv", "Extras/b.mp4", "bad.mkv", "notes.txt"):
            (self.lib / rel).write_bytes(b"")
        self.logs = []
        self.prog = []
        self.cancel = threading.Event()

    def opts(self, folders=None):
        return Options(folders=[str(self.lib)] if folders is None else folders,
                       export_folder=str(self.export), workers=2)

    def run_job(self, opts=None, **kw):
        kw.setdefault("now", NOW)
        kw.setdefault("scan_fn", fake_scan)
        return job.run_job(opts or self.opts(), self.logs.append,
                           lambda *a: self.prog.append(a), self.cancel, **kw)

    def xlsx(self):
        return list(self.export.glob("*.xlsx"))


class TestRunJob(JobTestBase):
    def test_done(self):
        res = self.run_job()
        self.assertEqual(res.status, job.DONE)
        self.assertEqual(res.report, self.export / STAMP_NAME)
        self.assertTrue(res.report.exists())
        self.assertEqual((res.files, res.records, res.errors), (3, 2, 1))
        wb = openpyxl.load_workbook(res.report)
        self.assertEqual(wb.sheetnames, ["Library", "Errors"])
        self.assertEqual(wb["Library"].max_row, 3)  # header + 2
        self.assertEqual(wb["Errors"].max_row, 2)   # header + 1
        self.assertIn("bad.mkv", wb["Errors"]["A2"].value)

    def test_second_run_gets_unique_name(self):
        self.run_job()
        res = self.run_job()
        self.assertEqual(res.status, job.DONE)
        self.assertEqual(res.report.name, STAMP_NAME.replace(".xlsx", " (2).xlsx"))
        self.assertEqual(len(self.xlsx()), 2)

    def test_missing_folder_skipped(self):
        missing = str(self.lib / "nope")
        res = self.run_job(self.opts([missing, str(self.lib)]))
        self.assertEqual(res.status, job.DONE)
        self.assertIn(f"Skipping missing folder: {missing}", self.logs)

    def test_only_missing_folder_is_no_files(self):
        res = self.run_job(self.opts([str(self.lib / "nope")]))
        self.assertEqual(res.status, job.NO_FILES)
        self.assertIn("Skipping missing folder", "\n".join(self.logs))

    def test_no_folders(self):
        for folders in ([], ["", "  "]):
            res = self.run_job(self.opts(folders))
            self.assertEqual(res.status, job.NO_FILES)
        self.assertEqual(self.xlsx(), [])

    def test_folder_without_videos(self):
        empty = Path(self._td.name) / "empty"
        empty.mkdir()
        (empty / "readme.txt").write_bytes(b"")
        res = self.run_job(self.opts([str(empty)]))
        self.assertEqual(res.status, job.NO_FILES)
        self.assertIsNone(res.report)
        self.assertEqual(self.xlsx(), [])

    def test_cancel_before_start(self):
        self.cancel.set()
        res = self.run_job()
        self.assertEqual(res.status, job.CANCELLED)
        self.assertIsNone(res.report)
        self.assertEqual(self.xlsx(), [])

    def test_cancel_mid_scan(self):
        for i in range(8):
            (self.lib / f"x{i}.mkv").write_bytes(b"")

        def slow(path, extras):
            time.sleep(0.3)
            return FileRecord(folder=str(path.parent), file=path.name)

        timer = threading.Timer(0.1, self.cancel.set)
        timer.start()
        self.addCleanup(timer.cancel)
        res = self.run_job(scan_fn=slow)
        self.assertEqual(res.status, job.CANCELLED)
        self.assertIsNone(res.report)
        self.assertEqual(self.xlsx(), [])

    def test_write_failure(self):
        with mock.patch("mediareport.excel.write_workbook", side_effect=OSError("disk full")):
            res = self.run_job()
        self.assertEqual(res.status, job.FAILED)
        self.assertIsNone(res.report)
        self.assertIn("disk full", res.message)
        self.assertEqual(self.xlsx(), [])

    def test_progress_once_per_file(self):
        res = self.run_job()
        self.assertEqual(len(self.prog), res.files)
        self.assertEqual(sorted(p[0] for p in self.prog), [1, 2, 3])
        self.assertTrue(all(p[1] == 3 for p in self.prog))
        errs = [p for p in self.prog if p[3]]
        self.assertEqual(len(errs), 1)
        self.assertEqual(errs[0][2].name, "bad.mkv")


class TestFormatDuration(unittest.TestCase):
    def test_format(self):
        self.assertEqual(job.format_duration(5), "5s")
        self.assertEqual(job.format_duration(65), "1m 05s")
        self.assertEqual(job.format_duration(3725), "1h 02m 05s")


if __name__ == "__main__":
    unittest.main()
