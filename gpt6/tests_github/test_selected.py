from __future__ import annotations
import copy
import os
from pathlib import Path
import unittest
from unittest.mock import patch
from intuition_github.config import load_config
from intuition_github.memory import Memory
from intuition_github.selected import SelectedController
from intuition_github.util import GuardError, Redactor
from tests_github.fakes import LocalGitHub, ScriptedLLM

ROOT = Path(__file__).resolve().parents[1]


class SelectedControllerTests(unittest.TestCase):
    def setUp(self):
        self.config = load_config(ROOT / ".intuition/config.json")
        self.config["allowed_paths"] = ["demo_app/metrics.py"]
        self.hub = LocalGitHub()
        self.addCleanup(self.hub.close)
        self.env = patch.dict(os.environ, {"INTUITION_AUTOMERGE": "false"})
        self.env.start()
        self.addCleanup(self.env.stop)
        self.model = ScriptedLLM()
        self.memory = Memory(self.hub, self.config)

    def controller(self, model=None):
        self.memory = Memory(self.hub, self.config)
        return SelectedController(self.hub, self.memory, self.config, lambda: model or self.model, Redactor([]))

    def test_import_issue_success_and_idempotency(self):
        issue = self.hub.create_issue("Fix metrics calculation", "Please clarify metrics logic.")
        ctrl = self.controller()
        paths = ["demo_app/metrics.py"]
        acceptance = ["Ensure metrics return valid integers."]

        task = ctrl.import_issue(issue["number"], paths, acceptance)
        self.assertEqual(task["status"], "ready")
        self.assertEqual(task["issue_number"], issue["number"])
        self.assertEqual(task["transport"], "gitive-local-review")
        self.assertEqual(task["target_files"], paths)
        self.assertEqual(task["acceptance"], acceptance)

        # Re-import with identical scope should return same task without error
        task2 = ctrl.import_issue(issue["number"], paths, acceptance)
        self.assertEqual(task["id"], task2["id"])

        # Re-import with modified scope should be rejected to protect existing delivery
        with self.assertRaises(GuardError):
            ctrl.import_issue(issue["number"], paths, ["Different acceptance"])

    def test_import_issue_rejections(self):
        ctrl = self.controller()
        issue = self.hub.create_issue("Sample issue", "Details")

        # Closed issue
        self.hub.issue_items[issue["number"]]["state"] = "closed"
        with self.assertRaisesRegex(GuardError, "Select an open Issue"):
            ctrl.import_issue(issue["number"], ["demo_app/metrics.py"], ["Criterion"])
        self.hub.issue_items[issue["number"]]["state"] = "open"

        # Issue is a PR
        self.hub.issue_items[issue["number"]]["pull_request"] = {}
        with self.assertRaisesRegex(GuardError, "Select an open Issue"):
            ctrl.import_issue(issue["number"], ["demo_app/metrics.py"], ["Criterion"])
        del self.hub.issue_items[issue["number"]]["pull_request"]

        # Mismatched html_url
        self.hub.issue_items[issue["number"]]["html_url"] = "https://github.com/other/repo/issues/1"
        with self.assertRaisesRegex(GuardError, "identity mismatch"):
            ctrl.import_issue(issue["number"], ["demo_app/metrics.py"], ["Criterion"])
        self.hub.issue_items[issue["number"]]["html_url"] = f"https://github.com/{self.hub.repository}/issues/{issue['number']}"

        # Unallowed path
        with self.assertRaisesRegex(GuardError, "bounded existing allowlisted"):
            ctrl.import_issue(issue["number"], ["unallowed/path.py"], ["Criterion"])

        # Invalid acceptance criteria
        with self.assertRaisesRegex(GuardError, "Provide 1–8 concrete acceptance"):
            ctrl.import_issue(issue["number"], ["demo_app/metrics.py"], [])
        with self.assertRaisesRegex(GuardError, "Provide 1–8 concrete acceptance"):
            ctrl.import_issue(issue["number"], ["demo_app/metrics.py"], ["x"] * 9)

        # Competing PR already exists
        self.hub.advance_ref("competing-branch", self.hub.ref("main"), None)
        competing = self.hub.create_pull("competing-branch", "main", "Competing PR", f"Closes #{issue['number']}")
        with self.assertRaisesRegex(GuardError, "already has an open/merged PR"):
            ctrl.import_issue(issue["number"], ["demo_app/metrics.py"], ["Criterion"])

    def test_escaped_body_of_merged_pr_is_still_a_duplicate(self):
        issue = self.hub.create_issue("Already delivered", "Details")
        self.hub.advance_ref("merged-branch", self.hub.ref("main"), None)
        pr = self.hub.create_pull("merged-branch", "main", "Delivered", f"x\\\\n\\\\nCloses #{issue['number']}.")
        self.hub.pull_items[pr["number"]]["state"] = "closed"
        self.hub.pull_items[pr["number"]]["merged_at"] = "2026-09-10T21:00:00Z"
        with self.assertRaisesRegex(GuardError, "already has an open/merged PR"):
            self.controller().import_issue(issue["number"], ["demo_app/metrics.py"], ["Criterion"])

    def test_cycle_issue_successful_flow(self):
        issue = self.hub.create_issue("Fix metrics calculation", "Please clarify metrics logic.")
        ctrl = self.controller()
        task = ctrl.import_issue(issue["number"], ["demo_app/metrics.py"], ["Ensure metrics return valid integers."])
        tid = task["id"]

        def fake_verifier(pr, head, base):
            return {"status": "passed", "head_sha": head, "base_sha": base, "output": "1 passed in 0.05s"}

        # Cycle 1: generate patch, create PR, run verifier, advance to awaiting_review
        res = ctrl.cycle_issue(tid, fake_verifier)
        self.assertEqual(res["status"], "awaiting_review")
        self.assertIsNotNone(res["pr_number"])
        self.assertEqual(len(res["attempts"]), 1)
        self.assertEqual(res["attempts"][0]["outcome"], "local_pass")

        # Verify PR was created
        pr = self.hub.pull(res["pr_number"])
        self.assertEqual(pr["state"], "open")
        self.assertIn(f"Closes #{issue['number']}", pr["body"])

        # Cycle 2: identical base -> no-op in awaiting_review
        res2 = ctrl.cycle_issue(tid, fake_verifier)
        self.assertEqual(res2["status"], "awaiting_review")
        self.assertEqual(len(self.model.calls), 1)  # No extra LLM call

    def test_cycle_issue_test_failure_and_retry(self):
        issue = self.hub.create_issue("Fix metrics calculation", "Please clarify metrics logic.")
        ctrl = self.controller()
        task = ctrl.import_issue(issue["number"], ["demo_app/metrics.py"], ["Ensure metrics return valid integers."])
        tid = task["id"]

        fail_verifier = lambda pr, head, base: {"status": "failed", "head_sha": head, "base_sha": base, "output": "AssertionError"}
        pass_verifier = lambda pr, head, base: {"status": "passed", "head_sha": head, "base_sha": base, "output": "1 passed"}

        # Cycle 1: verifier fails -> status returns to ready, evidence added
        res1 = ctrl.cycle_issue(tid, fail_verifier)
        self.assertEqual(res1["status"], "ready")
        self.assertEqual(res1["attempts"][0]["outcome"], "local_fail")
        self.assertTrue(any("local-test:" in e["id"] for e in res1["evidence"]))

        # Cycle 2: retry with pass_verifier -> generates 2nd attempt, succeeds
        ctrl2 = self.controller()
        res2 = ctrl2.cycle_issue(tid, pass_verifier)
        self.assertEqual(res2["status"], "awaiting_review")
        self.assertEqual(len(res2["attempts"]), 2)
        self.assertEqual(res2["attempts"][1]["outcome"], "local_pass")

    def test_cycle_issue_exceed_attempts_marks_needs_human(self):
        self.config["max_attempts_per_issue"] = 2
        issue = self.hub.create_issue("Fix metrics calculation", "Please clarify metrics logic.")
        ctrl = self.controller()
        task = ctrl.import_issue(issue["number"], ["demo_app/metrics.py"], ["Ensure metrics return valid integers."])
        tid = task["id"]

        fail_verifier = lambda pr, head, base: {"status": "failed", "head_sha": head, "base_sha": base, "output": "AssertionError"}

        ctrl.cycle_issue(tid, fail_verifier)
        ctrl2 = self.controller()
        res = ctrl2.cycle_issue(tid, fail_verifier)
        self.assertEqual(res["status"], "needs_human")
        self.assertIn("attempt limit reached", res["human_reason"])

    def test_cycle_issue_remote_changes(self):
        issue = self.hub.create_issue("Fix metrics calculation", "Please clarify metrics logic.")
        ctrl = self.controller()
        task = ctrl.import_issue(issue["number"], ["demo_app/metrics.py"], ["Ensure metrics return valid integers."])
        tid = task["id"]
        fake_verifier = lambda pr, head, base: {"status": "passed", "head_sha": head, "base_sha": base}
        ctrl.cycle_issue(tid, fake_verifier)

        # 1. PR merged remotely -> task marked completed
        ctrl_merge = self.controller()
        self.hub.pull_items[task["pr_number"]]["merged"] = True
        res = ctrl_merge.cycle_issue(tid, fake_verifier)
        self.assertEqual(res["status"], "completed")

        # 2. Remote issue closed -> task marked abandoned
        issue2 = self.hub.create_issue("Another issue", "Details")
        ctrl_iso = self.controller()
        task2 = ctrl_iso.import_issue(issue2["number"], ["demo_app/metrics.py"], ["Pass"])
        self.hub.issue_items[issue2["number"]]["state"] = "closed"
        ctrl_closed = self.controller()
        res2 = ctrl_closed.cycle_issue(task2["id"], fake_verifier)
        self.assertEqual(res2["status"], "abandoned")

        # 3. Issue body changed remotely -> marked needs_human
        issue3 = self.hub.create_issue("Third issue", "Original body")
        ctrl_iso2 = self.controller()
        task3 = ctrl_iso2.import_issue(issue3["number"], ["demo_app/metrics.py"], ["Pass"])
        self.hub.issue_items[issue3["number"]]["body"] = "Tampered body"
        ctrl_tampered = self.controller()
        res3 = ctrl_tampered.cycle_issue(task3["id"], fake_verifier)
        self.assertEqual(res3["status"], "needs_human")
        self.assertIn("Issue changed", res3["human_reason"])
