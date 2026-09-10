from __future__ import annotations
import copy
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch
from intuition_github.config import load_config
from intuition_github.controller import Controller
from intuition_github.evidence import accepted_run, ingest_run
from intuition_github.github import GhError
from intuition_github.memory import Memory
from intuition_github.util import GuardError, Redactor, canonical, now
from intuition_github.verification import resolve_candidate, report_candidate, receipt_description
from tests_github.fakes import LocalGitHub, ScriptedLLM

ROOT = Path(__file__).resolve().parents[1]


class GitHubIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.config = load_config(ROOT / ".intuition/config.json")
        self.hub = LocalGitHub()
        self.addCleanup(self.hub.close)
        self.env = patch.dict(os.environ, {"INTUITION_AUTOMERGE": "false"})
        self.env.start()
        self.addCleanup(self.env.stop)
        self.model = ScriptedLLM()
        self.memory = Memory(self.hub, self.config)

    def controller(self, model=None):
        self.memory = Memory(self.hub, self.config)
        return Controller(self.hub, self.memory, self.config, lambda: model or self.model, Redactor([]))

    def test_patch_rejection_survives_restart_and_reaches_next_request(self):
        original = self.model.complete
        def invalid_once(purpose, payload):
            reply, tokens = original(purpose, payload)
            if purpose == "propose_patch":
                reply["edits"][0]["content"] += "\ndef unwanted_public_api(x): return x\n"
            return reply, tokens
        with patch.object(self.model, "complete", side_effect=invalid_once):
            self.controller().cycle()
        task = next(iter(self.memory.state["tasks"].values()))
        self.assertIn("api_signature_mismatch", task["patch_rejection"])
        self.controller().cycle()
        patches = [payload for purpose, payload in self.model.calls if purpose == "propose_patch"]
        self.assertIn("added=1", patches[-1]["previous_rejection"])
        task = next(iter(self.memory.state["tasks"].values()))
        self.assertNotIn("patch_rejection", task)
        self.assertEqual(task["status"], "verifying")

    def first_candidate(self):
        controller = self.controller()
        result = controller.cycle()
        task = next(iter(self.memory.state["tasks"].values()))
        self.assertEqual(task["status"], "verifying")
        self.assertEqual(result["llm_calls"], 2)
        return task

    def verified_run(self, task, outcome="success", run_id=20, attempt=1):
        return self.hub.add_run(run_id, path="verify-candidate.yml", event="workflow_dispatch",
            conclusion=outcome, pr=task["pr_number"], candidate=task["attempts"][-1]["head_sha"],
            logs=f"Synthetic candidate result: {outcome}\n", attempt=attempt)

    def test_plan_failure_survives_restart_and_recovers(self):
        class BrokenPlan:
            def complete(self, purpose, payload):
                return {}, 2
        controller = self.controller(BrokenPlan())
        result = controller.cycle()
        self.assertEqual(result["llm_calls"], 1)
        self.assertEqual(self.memory.state["plan_failure"]["count"], 1)
        self.assertFalse(self.memory.state["tasks"])
        task = self.first_candidate()
        self.assertNotIn("plan_failure", self.memory.state)
        self.verified_run(task, "failure")
        self.controller().cycle()
        self.assertEqual(len(self.memory.state["tasks"][task["id"]]["attempts"]), 2)

    def test_plan_failures_are_bounded_across_restarts(self):
        class BrokenPlan:
            def complete(self, purpose, payload):
                return {}, 2
        for _ in range(self.config["max_attempts_per_issue"]):
            self.assertEqual(self.controller(BrokenPlan()).cycle()["llm_calls"], 1)
        self.assertEqual(self.controller(BrokenPlan()).cycle()["llm_calls"], 0)

    def test_memory_roundtrip_uses_actual_git_objects(self):
        self.memory.state["facts"].append({"id": "f1", "text": "synthetic"})
        first = self.memory.save("one")
        self.memory.save("two")
        restored = Memory(self.hub, self.config)
        self.assertEqual(restored.state["sequence"], 2)
        self.assertEqual(restored.state["facts"][0]["id"], "f1")
        parents = self.hub.commit(restored.head)["parents"]
        self.assertEqual(parents, [{"sha": first}])
        self.assertEqual(len([p for p in self.hub.tree(restored.head) if p.startswith("events/")]), 2)

    def test_stale_memory_write_rejected(self):
        a, b = Memory(self.hub, self.config), Memory(self.hub, self.config)
        a.save("writer_a")
        with self.assertRaises(GuardError):
            b.save("writer_b")
        self.assertEqual(self.hub.ref("intuition-memory"), a.head)

    def test_non_fast_forward_git_ref_rejected(self):
        parent = self.hub.ref("main")
        a = self.hub.create_commit(parent, {"demo_app/metrics.py": b"a = 1\n"}, "a")
        b = self.hub.create_commit(parent, {"demo_app/metrics.py": b"b = 1\n"}, "b")
        self.hub.advance_ref("main", a, parent)
        with self.assertRaises(GhError):
            self.hub.api(self.hub.prefix + "/git/refs/heads/main", "PATCH", {"sha": b, "force": False})
        self.assertEqual(self.hub.ref("main"), a)

    def test_existing_successful_ref_update_is_idempotent(self):
        head = self.hub.ref("main")
        self.hub.advance_ref("main", head, "0" * 40)
        self.assertEqual(self.hub.ref("main"), head)

    def test_memory_branch_and_evidence_paths_are_restricted(self):
        with self.assertRaises(GuardError):
            Memory(self.hub, {**self.config, "memory_branch": "main"})
        with self.assertRaises(GuardError):
            self.memory.save("unsafe", extra={"../escape": b"no"})

    def test_daily_budget_persists_before_llm_failure(self):
        bad = ScriptedLLM(fail=True)
        c = self.controller(bad)
        with self.assertRaises(GuardError):
            c.call("propose_tasks", {"fixture": True})
        restored = Memory(self.hub, self.config)
        self.assertEqual(restored.state["budgets"][now()[:10]]["calls"], 1)
        self.assertEqual(len(bad.calls), 1)

    def test_budget_limit_prevents_another_model_call(self):
        self.config["max_calls_per_day"] = 1
        c = self.controller()
        self.memory.reserve_call(self.config, "first", 100)
        with self.assertRaises(GuardError):
            c.call("propose_tasks", {"fixture": True})
        self.assertEqual(len(self.model.calls), 0)

    def test_oversized_context_not_sent_or_counted(self):
        c = self.controller()
        with self.assertRaises(GuardError):
            c.call("propose_tasks", {"too_large": "x" * self.config["max_input_chars"]})
        self.assertEqual(len(self.model.calls), 0)
        self.assertEqual(self.memory.state["budgets"][now()[:10]]["calls"], 0)

    def test_log_redaction_and_attempt_deduplication(self):
        secret = "a-realistic-but-synthetic-secret-value"
        run = self.hub.add_run(11, logs="token=" + secret + "\n\x1b[31mfailed test\x1b[0m\n")
        redactor = Redactor([secret])
        self.assertIsNotNone(ingest_run(self.hub, self.memory, run, self.config, "main", redactor))
        head = self.memory.head
        self.assertIsNone(ingest_run(self.hub, self.memory, run, self.config, "main", redactor))
        self.assertEqual(self.memory.head, head)
        stored = self.hub.files(head, [p for p in self.hub.tree(head) if p.startswith("evidence/")])
        self.assertNotIn(secret, canonical(self.memory.state).decode())
        self.assertNotIn(secret, b"".join(stored.values()).decode())
        run = self.hub.add_run(11, attempt=2)
        ingest_run(self.hub, self.memory, run, self.config, "main", redactor)
        self.assertEqual(self.memory.state["seen_runs"], ["11:1", "11:2"])

    def test_fork_feature_branch_and_unknown_workflow_not_ingested(self):
        original = self.hub.run(10)
        for change in ({"head_repository": {"full_name": "fork/project"}}, {"head_branch": "feature"},
                       {"path": ".github/workflows/untrusted.yml"}, {"event": "pull_request"},
                       {"status": "in_progress"}):
            with self.subTest(change=change):
                run = {**original, **change}
                self.assertFalse(accepted_run(run, self.hub.repository, "main", self.config))
                self.assertIsNone(ingest_run(self.hub, self.memory, run, self.config, "main", Redactor([])))
        self.assertIsNone(self.memory.head)

    def test_expired_logs_preserve_metadata_without_fabricated_text(self):
        run = self.hub.add_run(11, logs=GhError("expired", 410))
        obs = ingest_run(self.hub, self.memory, run, self.config, "main", Redactor([]))
        self.assertEqual(obs["fact_ids"], ["run:11:1"])
        self.assertIn("logs_error", self.memory.state["facts"][0])

    def test_full_issue_pr_failure_retry_success_merge_cd_lifecycle(self):
        first = self.first_candidate()
        issue, pr = first["issue_number"], first["pr_number"]
        self.verified_run(first, "failure")
        second_cycle = self.controller()
        second_cycle.cycle(run_id=20)
        task = self.memory.state["tasks"][first["id"]]
        self.assertEqual(task["status"], "verifying")
        self.assertEqual(len(task["attempts"]), 2)
        self.assertNotEqual(task["attempts"][0]["head_sha"], task["attempts"][1]["head_sha"])
        self.assertEqual(self.memory.state["profile_counts"]["refactor"], {"alpha": 4, "beta": 3})
        self.verified_run(task, "success", 21)
        self.controller().cycle(run_id=21)
        task = self.memory.state["tasks"][first["id"]]
        self.assertEqual(task["status"], "awaiting_merge")
        self.assertEqual(self.memory.state["profile_counts"]["refactor"], {"alpha": 5, "beta": 3})
        self.assertEqual(len(self.hub.issue_items), 1)
        self.assertEqual(len(self.hub.pull_items), 1)
        current = self.hub.pull(pr)
        self.hub.advance_ref("main", current["head"]["sha"], self.hub.ref("main"))
        self.hub.pull_items[pr].update(state="closed", merged=True)
        self.hub.issue_items[issue]["state"] = "closed"
        self.hub.add_run(22, path="cd.yml", event="workflow_run", logs="Synthetic release ZIP published")
        empty = ScriptedLLM(empty=True)
        self.controller(empty).cycle(run_id=22)
        task = self.memory.state["tasks"][first["id"]]
        self.assertEqual(task["status"], "completed")
        self.assertTrue(any(f.get("workflow_path") == ".github/workflows/cd.yml" for f in self.memory.state["facts"]))
        self.assertTrue(any(f["kind"] == "pull_request_merge" for f in self.memory.state["facts"]))
        self.assertEqual(self.memory.state["budgets"][now()[:10]]["calls"], 4)
        self.assertEqual(sum(op[0] == "create_issue" for op in self.hub.operations), 1)
        self.assertEqual(sum(op[0] == "create_pull" for op in self.hub.operations), 1)

    def test_issue_creation_lost_response_recovers_without_duplicate(self):
        self.hub.fail_next_issue_response = True
        with self.assertRaises(GhError):
            self.controller().cycle()
        self.assertEqual(len(self.hub.issue_items), 1)
        result = self.controller().cycle()
        self.assertEqual(result["llm_calls"], 1)
        self.assertEqual(len(self.hub.issue_items), 1)
        self.assertEqual(len(self.hub.pull_items), 1)

    def test_prepared_commit_recovers_without_regenerating_patch(self):
        c = self.controller()
        with patch.object(c, "publish_prepared", side_effect=GhError("synthetic process interruption")):
            with self.assertRaises(GhError):
                c.cycle()
        task = next(iter(Memory(self.hub, self.config).state["tasks"].values()))
        prepared = task["prepared"]["commit"]
        result = self.controller().cycle()
        self.assertEqual(result["llm_calls"], 0)
        task = next(iter(self.memory.state["tasks"].values()))
        self.assertEqual(task["attempts"][0]["head_sha"], prepared)

    def test_observation_save_before_learning_crash_recovers(self):
        first = self.first_candidate()
        run = self.verified_run(first)
        ingest_run(self.hub, self.memory, run, self.config, "main", Redactor([]))
        self.controller().cycle(run_id=20)
        self.assertEqual(self.memory.state["tasks"][first["id"]]["status"], "awaiting_merge")
        self.assertEqual(self.memory.state["profile_counts"]["refactor"]["alpha"], 5)

    def test_same_sha_rerun_does_not_train_twice(self):
        first = self.first_candidate()
        self.verified_run(first)
        self.controller().cycle(run_id=20)
        self.verified_run(first, attempt=2)
        self.controller().cycle(run_id=20)
        self.assertEqual(self.memory.state["profile_counts"]["refactor"]["alpha"], 5)
        self.assertIn("20:2", self.memory.state["seen_runs"])

    def test_cancelled_run_does_not_count_as_failure(self):
        first = self.first_candidate()
        self.verified_run(first, "cancelled")
        self.controller().cycle(run_id=20)
        self.assertEqual(self.memory.state["profile_counts"]["refactor"], {"alpha": 4, "beta": 2})
        self.assertEqual(self.memory.state["tasks"][first["id"]]["status"], "verifying")

    def test_failed_reporter_does_not_count_green_test_as_trusted_success(self):
        first = self.first_candidate()
        self.verified_run(first, "failure")
        self.hub.job_items[(20, 1)][0]["conclusion"] = "success"
        self.hub.job_items[(20, 1)][0]["steps"][0]["conclusion"] = "success"
        self.controller().cycle(run_id=20)
        self.assertEqual(self.memory.state["profile_counts"]["refactor"]["alpha"], 4)

    def test_setup_failure_is_not_a_failed_candidate_test(self):
        first = self.first_candidate()
        self.verified_run(first, "failure")
        self.hub.job_items[(20, 1)][0]["steps"][0]["conclusion"] = "skipped"
        self.controller().cycle(run_id=20)
        self.assertEqual(self.memory.state["profile_counts"]["refactor"], {"alpha": 4, "beta": 2})
        self.assertEqual(self.memory.state["tasks"][first["id"]]["status"], "verifying")

    def test_stale_candidate_result_cannot_approve_new_sha(self):
        first = self.first_candidate()
        branch = self.hub.pull(first["pr_number"])["head"]["ref"]
        old = first["attempts"][-1]["head_sha"]
        newer = self.hub.create_commit(old, {"demo_app/metrics.py": b"value = 3\n"}, "external edit")
        self.hub.advance_ref(branch, newer, old)
        self.verified_run(first)
        self.controller().cycle(run_id=20)
        self.assertEqual(self.memory.state["tasks"][first["id"]]["status"], "needs_human")
        self.assertEqual(self.memory.state["profile_counts"]["refactor"]["alpha"], 4)

    def test_two_failures_stop_task_and_no_third_patch(self):
        first = self.first_candidate()
        self.verified_run(first, "failure")
        self.controller().cycle(run_id=20)
        task = self.memory.state["tasks"][first["id"]]
        self.verified_run(task, "failure", 21)
        result = self.controller().cycle(run_id=21)
        task = self.memory.state["tasks"][first["id"]]
        self.assertEqual(task["status"], "needs_human")
        self.assertEqual(len(task["attempts"]), 2)
        self.assertEqual(result["llm_calls"], 0)

    def test_circuit_breaker_prevents_following_paid_patch(self):
        self.config["max_failures_before_pause"] = 1
        first = self.first_candidate()
        self.verified_run(first, "failure")
        result = self.controller().cycle(run_id=20)
        self.assertEqual(result["status"], "paused")
        self.assertEqual(result["llm_calls"], 0)

    def test_empty_plan_is_not_repeated_for_same_context(self):
        empty = ScriptedLLM(empty=True)
        self.controller(empty).cycle()
        self.controller(empty).cycle()
        self.assertEqual(len(empty.calls), 1)
        self.assertEqual(self.hub.issue_items, {})

    def test_default_ci_failed_dispatch_can_be_retried(self):
        self.hub.run_items.clear()
        self.hub.fail_ci_dispatch = True
        c = self.controller()
        with self.assertRaises(GhError):
            c.ensure_default_ci()
        self.assertIsNone(c.state["last_ci_requested_sha"])
        self.hub.fail_ci_dispatch = False
        c.ensure_default_ci()
        self.assertEqual(c.state["last_ci_requested_sha"], c.base)

    def test_context_selection_is_bounded_and_deduplicated(self):
        c = self.controller()
        facts = [{"id": str(n), "text": "x" * 10000} for n in range(100)]
        selected = c.context_facts(facts + facts)
        self.assertEqual(len({f["id"] for f in selected}), len(selected))
        self.assertLess(len(canonical(selected)), self.config["max_input_chars"] // 4 + 100)

    def test_default_auto_merge_is_off(self):
        task = self.first_candidate()
        self.verified_run(task)
        self.controller().cycle(run_id=20)
        self.assertFalse(any(op[0] == "gh" and op[1][:2] == ["pr", "merge"] for op in self.hub.operations))

    def test_auto_merge_fails_closed_without_protection(self):
        first = self.first_candidate()
        self.verified_run(first)
        with patch.dict(os.environ, {"INTUITION_AUTOMERGE": "true"}):
            self.controller().cycle(run_id=20)
        self.assertTrue(self.memory.state["tasks"][first["id"]]["automerge_blocked"])
        self.assertFalse(any(op[0] == "gh" and op[1][:2] == ["pr", "merge"] for op in self.hub.operations))

    def test_auto_merge_requires_exact_status_and_strict_policy(self):
        first = self.first_candidate()
        self.verified_run(first)
        head = first["attempts"][-1]["head_sha"]
        self.hub.protection = {"required_status_checks": {"strict": True, "contexts": ["Intuition / verified"]},
                               "enforce_admins": {"enabled": True}, "allow_force_pushes": {"enabled": False}}
        self.hub.set_status(head, "success", "https://github.com/example/project/actions/runs/20",
            description=receipt_description(resolve_candidate(self.hub, self.config, first["pr_number"], head)))
        with patch.dict(os.environ, {"INTUITION_AUTOMERGE": "true"}):
            self.controller().cycle(run_id=20)
        commands = [op[1] for op in self.hub.operations if op[0] == "gh" and op[1][:2] == ["pr", "merge"]]
        self.assertEqual(len(commands), 1)
        self.assertIn("--match-head-commit", commands[0])
        self.assertNotIn("--admin", commands[0])

    def test_resolver_and_reporter_check_exact_sha(self):
        task = self.first_candidate()
        head = task["attempts"][-1]["head_sha"]
        result = resolve_candidate(self.hub, self.config, task["pr_number"], head)
        self.assertEqual(result["head_sha"], head)
        report_candidate(self.hub, self.config, task["pr_number"], head, "success",
                         "https://github.com/example/project/actions/runs/20", tested=result)
        self.assertEqual(self.hub.status_items[head][0]["state"], "success")
        with self.assertRaises(GuardError):
            resolve_candidate(self.hub, self.config, task["pr_number"], "0" * 40)

    def test_resolver_rejects_protected_added_renamed_and_excessive_diff(self):
        task = self.first_candidate()
        head = task["attempts"][-1]["head_sha"]
        for file in ({"filename": ".github/workflows/ci.yml", "status": "modified", "changes": 1},
                     {"filename": "demo_app/metrics.py", "status": "added", "changes": 1},
                     {"filename": "demo_app/metrics.py", "status": "renamed", "changes": 1},
                     {"filename": "demo_app/metrics.py", "status": "modified", "changes": 1000}):
            with self.subTest(file=file):
                self.hub.changed_files_override = [file]
                with self.assertRaises(GuardError):
                    resolve_candidate(self.hub, self.config, task["pr_number"], head)

    def test_git_symlink_or_executable_cannot_be_read_as_editable(self):
        parent = self.hub.ref("main")
        blob = self.hub.tree(parent)["demo_app/metrics.py"]["sha"]
        for mode in ("120000", "100755"):
            tree = self.hub.api(self.hub.prefix + "/git/trees", "POST", {"base_tree": self.hub.commit(parent)["tree"]["sha"],
                "tree": [{"path": "demo_app/metrics.py", "mode": mode, "type": "blob", "sha": blob}]})
            commit = self.hub.api(self.hub.prefix + "/git/commits", "POST", {
                "tree": tree["sha"], "parents": [parent], "message": "unsafe mode fixture"})["sha"]
            with self.assertRaises(GuardError):
                self.hub.files(commit, ["demo_app/metrics.py"])


if __name__ == "__main__":
    unittest.main()
