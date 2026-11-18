import threading
import time
import unittest
from pathlib import Path

from mediareport import scanner
from mediareport.core import FileRecord, ScanError


def rec(path):
    return FileRecord(folder=str(path.parent), file=path.name)


class TestScan(unittest.TestCase):
    def test_order_preserved(self):
        files = [Path(f"f{i}.mkv") for i in range(6)]
        delays = dict(zip(files, [0.25, 0.01, 0.15, 0.02, 0.1, 0.0]))

        def fn(p, extras):
            time.sleep(delays[p])
            return rec(p)
        res = scanner.scan(files, workers=4, scan_fn=fn)
        self.assertEqual([r.file for r in res.records], [f.name for f in files])

    def test_errors(self):
        files = [Path("a.mkv"), Path("bad.mkv"), Path("c.mkv"), Path("empty.mkv")]

        def fn(p, extras):
            if p.name == "bad.mkv":
                raise RuntimeError("boom")
            if p.name == "empty.mkv":
                raise ValueError()
            return rec(p)
        res = scanner.scan(files, workers=2, scan_fn=fn)
        self.assertEqual([r.file for r in res.records], ["a.mkv", "c.mkv"])
        self.assertEqual(len(res.errors), 2)
        self.assertIsInstance(res.errors[0], ScanError)
        self.assertEqual(res.errors[0].path, "bad.mkv")
        self.assertEqual(res.errors[0].message, "boom")
        self.assertEqual(res.errors[1].message, "ValueError")

    def test_progress(self):
        files = [Path(f"f{i}.mkv") for i in range(5)]
        calls = []

        def fn(p, extras):
            if p.name == "f2.mkv":
                raise RuntimeError("x")
            return rec(p)
        scanner.scan(files, workers=3, scan_fn=fn,
                     on_progress=lambda d, t, p, e: calls.append((d, t, p, e)))
        self.assertEqual([c[0] for c in calls], [1, 2, 3, 4, 5])
        self.assertTrue(all(c[1] == 5 for c in calls))
        self.assertEqual({c[2] for c in calls}, set(files))
        errs = [c for c in calls if c[3]]
        self.assertEqual(len(errs), 1)
        self.assertEqual(errs[0][2].name, "f2.mkv")

    def test_cancel(self):
        files = [Path(f"f{i}.mkv") for i in range(40)]
        ev = threading.Event()

        def fn(p, extras):
            time.sleep(0.01)
            return rec(p)

        def prog(d, t, p, e):
            if d >= 3:
                ev.set()
        res = scanner.scan(files, workers=2, scan_fn=fn, on_progress=prog, cancel_event=ev)
        self.assertLess(len(res.records), len(files))
        self.assertGreaterEqual(len(res.records), 3)

    def test_empty(self):
        res = scanner.scan([], scan_fn=lambda p, e: rec(p))
        self.assertEqual((res.records, res.errors), ([], []))

    def test_extras_passed(self):
        seen = []

        def fn(p, e):
            seen.append(tuple(e))
            return rec(p)
        scanner.scan([Path("a.mkv")], extras_folders=["bonus"], scan_fn=fn)
        self.assertEqual(seen, [("bonus",)])


if __name__ == "__main__":
    unittest.main()
