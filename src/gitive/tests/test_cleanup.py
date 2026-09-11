import json
import os
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch

from gitive.cleanup import clean_data, dir_size
from gitive.presentation import render


class CleanupTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.data = Path(self.temp.name)

    def _create_run(self, name, age_days=0, size_kb=10):
        folder = self.data / name
        folder.mkdir(parents=True, exist_ok=True)
        file = folder / "test.log"
        file.write_bytes(b"x" * (size_kb * 1024))
        mtime = time.time() - (age_days * 86400)
        os.utime(folder, (mtime, mtime))
        os.utime(file, (mtime, mtime))
        return folder

    def test_dir_size_calculates_recursive_bytes(self):
        folder = self._create_run("20260901T120000Z-abcdef", size_kb=5)
        sub = folder / "sub"
        sub.mkdir()
        (sub / "subfile.txt").write_bytes(b"y" * 1024)
        self.assertEqual(dir_size(folder), 6 * 1024)

    def test_clean_data_protects_keep_last(self):
        runs = []
        for i in range(10):
            name = f"2026090{i}T120000Z-aaaa{i:02d}"
            runs.append(self._create_run(name, age_days=10 - i, size_kb=1))

        res = clean_data(self.data, days=3, keep_last=5, dry_run=False)
        self.assertTrue(res["ok"])
        self.assertFalse(res["dry_run"])
        self.assertEqual(res["cleaned_count"], 5)
        self.assertEqual(res["kept_count"], 5)
        self.assertEqual(res["freed_bytes"], 5 * 1024)

        for folder in runs[:5]:
            self.assertFalse(folder.exists())
        for folder in runs[5:]:
            self.assertTrue(folder.exists())

    def test_clean_data_dry_run_leaves_directories(self):
        runs = []
        for i in range(7):
            name = f"2026090{i}T120000Z-bbbb{i:02d}"
            runs.append(self._create_run(name, age_days=10 - i, size_kb=2))

        res = clean_data(self.data, days=3, keep_last=3, dry_run=True)
        self.assertTrue(res["dry_run"])
        self.assertEqual(res["cleaned_count"], 4)
        self.assertEqual(res["kept_count"], 3)
        self.assertEqual(res["freed_bytes"], 8 * 1024)

        for folder in runs:
            self.assertTrue(folder.exists())

    def test_clean_data_protects_active_run_even_if_old(self):
        active = self._create_run("20260901T100000Z-active0", age_days=20, size_kb=5)
        old1 = self._create_run("20260902T100000Z-oldold1", age_days=15, size_kb=5)
        old2 = self._create_run("20260903T100000Z-oldold2", age_days=10, size_kb=5)

        res = clean_data(self.data, active_run="20260901T100000Z-active0", days=1, keep_last=1)
        self.assertTrue(active.exists())
        self.assertIn("20260901T100000Z-active0", res["kept_runs"])

    def test_clean_data_cleans_stale_web_checks(self):
        stale_wc = self.data / "web-check-abc"
        stale_wc.mkdir()
        (stale_wc / "file.txt").write_bytes(b"data")
        mtime = time.time() - (2 * 86400)
        os.utime(stale_wc, (mtime, mtime))

        fresh_wc = self.data / "web-check-fresh"
        fresh_wc.mkdir()
        (fresh_wc / "file.txt").write_bytes(b"data")

        res = clean_data(self.data, days=0, keep_last=0)
        self.assertFalse(stale_wc.exists())
        self.assertTrue(fresh_wc.exists())

    def test_presentation_render_clean(self):
        value = {
            "ok": True,
            "dry_run": True,
            "freed_bytes": 1024 * 1024 * 2 + 512 * 1024,
            "cleaned_count": 2,
            "kept_count": 5,
            "cleaned_runs": ["20260901T000000Z-111111", "20260902T000000Z-222222"],
        }
        text = render(value, kind="clean")
        self.assertIn("[podgląd]", text)
        self.assertIn("2.5 MB", text)
        self.assertIn("usunięto 2", text)
        self.assertIn("zachowano 5", text)
        self.assertIn("20260901T000000Z-111111", text)
