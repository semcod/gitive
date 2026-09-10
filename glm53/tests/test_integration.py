import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from intuition.store import Store
from intuition.core import run_step, replay
from intuition.llm import Client
from intuition.ci_facts import sync_ci_facts, redact
from intuition.refactor import refactor_step, validate_edits, request_auto_merge


class RepoTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.store = Store(self.root)
        self.store.git("init", "-b", "main")
        self.store.git("config", "user.name", "Test")
        self.store.git("config", "user.email", "test@example.invalid")
        with self.store.lock():
            self.store.init("Teoria grafów: jakie własności warto zbadać?")

    def tearDown(self):
        self.temp.cleanup()

    def test_end_to_end_and_replay(self):
        for _ in range(3):
            with self.store.lock():
                run_step(self.store, Client("mock"))
        report = replay(self.store)
        self.assertEqual(report["steps"], 3)
        self.assertGreater(report["reward"], 0)
        self.assertEqual(self.store.git("status", "--porcelain"), "")
        self.assertEqual(len(self.store.rows()), 3)

    def test_dry_run_has_no_writes(self):
        before = self.store.git("rev-parse", "HEAD")
        with self.store.lock():
            result = run_step(self.store, Client("mock"), dry_run=True)
        self.assertIn("probabilities", result)
        self.assertEqual(self.store.git("rev-parse", "HEAD"), before)
        self.assertEqual(self.store.state()["step"], 0)

    def test_commit_failure_rolls_back(self):
        hook = self.root / ".git/hooks/pre-commit"
        hook.write_text("#!/bin/sh\nexit 1\n")
        hook.chmod(0o755)
        before = self.store.state()
        with self.assertRaises(RuntimeError), self.store.lock():
            run_step(self.store, Client("mock"))
        self.assertEqual(self.store.state(), before)
        self.assertEqual(len(self.store.facts()), 1)
        self.assertFalse((self.root / ".intuition-pending.json").exists())
        self.assertEqual(self.store.git("status", "--porcelain"), "")

    def test_no_overwrite_or_dirty_staging(self):
        with self.assertRaises(ValueError):
            self.store.transaction({"facts/f_0001.json": "{}"}, "bad")
        (self.root / "user.txt").write_text("unrelated")
        with self.assertRaises(ValueError), self.store.lock():
            run_step(self.store, Client("mock"))
        self.assertEqual(self.store.git("diff", "--cached", "--name-only"), "")

    def test_corrupt_fact_fails(self):
        (self.root / "facts/f_0001.json").write_text("{")
        with self.assertRaises(ValueError):
            self.store.facts()

    def test_lock_exclusion(self):
        with self.store.lock():
            with self.assertRaises(RuntimeError), self.store.lock():
                pass

    def test_replay_detects_modified_history(self):
        f = self.root / "facts/f_0001.json"
        f.write_text(f.read_text().replace("Teoria", "Zmiana"))
        self.store.git("add", "facts")
        self.store.git("commit", "-m", "illegal edit")
        with self.assertRaises(ValueError):
            replay(self.store)

    def test_ci_idempotency_and_rerun(self):
        class FakeGH:
            repo = "owner/repo"
            attempt = 1
            def api(self, endpoint):
                return {"workflow_runs": [dict(id=123, status="completed", conclusion="failure" if self.attempt == 1 else "success",
                         run_attempt=self.attempt, updated_at="2026-09-10T00:00:00Z", name="CI", head_branch="main",
                         head_sha="abcdef", html_url="https://github.com/owner/repo/actions/runs/123")]}
            def call(self, *args):
                return "test failed"
        gh = FakeGH()
        self.assertEqual(sync_ci_facts(self.store, gh), 1)
        self.assertEqual(sync_ci_facts(self.store, gh), 0)
        gh.attempt = 2
        self.assertEqual(sync_ci_facts(self.store, gh), 1)
        from intuition.facts import frontier
        self.assertEqual(frontier(self.store.facts())["open"], ["f_0001"])

    def test_preview_refactor_real_tests_in_clone(self):
        (self.root / "examples").mkdir()
        (self.root / "examples/demo.py").write_text("def add(a, b):\n    result = a + b\n    return result\n")
        self.store.git("add", "examples")
        self.store.git("commit", "-m", "target")
        head = self.store.git("rev-parse", "HEAD")
        test = ["python3", "-B", "-c", "from examples.demo import add; assert add(2, 3) == 5"]
        result = refactor_step(self.store, Client("mock"), None, 7, ["examples"], test)
        self.assertTrue(result["passed"])
        self.assertIn("return a + b", result["diff"])
        self.assertEqual(head, self.store.git("rev-parse", "HEAD"))
        self.assertIn("result =", (self.root / "examples/demo.py").read_text())

    def test_scope_and_redaction(self):
        with self.assertRaises(ValueError):
            validate_edits({"files": [{"path": "../.env", "content": "bad"}]}, {"src/a.py": ""})
        with patch.dict(os.environ, {"GH_TOKEN": "super-secret-token"}):
            self.assertNotIn("super-secret-token", redact("token super-secret-token"))

    def test_auto_merge_gate(self):
        class GH:
            repo = "o/r"
            calls = []
            checks = []
            def call(self, *args):
                self.calls.append(args)
                if args[:2] == ("pr", "view"):
                    return json.dumps(dict(headRefOid="abc", headRefName="intuition/issue-1", isDraft=False, state="OPEN"))
                if args[:2] == ("pr", "checks"):
                    return json.dumps(self.checks)
                return "queued"
        gh = GH()
        with self.assertRaises(ValueError):
            request_auto_merge(gh, 1)
        gh.checks = [{"name": "test", "bucket": "pass"}]
        self.assertEqual(request_auto_merge(gh, 1), "queued")
        self.assertIn("--match-head-commit", gh.calls[-1])
        self.assertEqual(gh.calls[-1][-1], "abc")
