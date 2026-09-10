"""One bounded cycle. Actions events and a schedule provide repetition, not while True."""
from __future__ import annotations
import os
from datetime import datetime, timezone
from urllib.parse import quote
from .config import path_allowed
from .evidence import accepted_run, ingest_run, verification_identity
from .github import GhError
from .llm import LiteLLMClient, SYSTEM
from .planning import TASK_CONTRACT, PATCH_CONTRACT, issue_body, validate_patch, validate_tasks
from .util import GuardError, Redactor, canonical, digest, now

TERMINAL = {"completed", "abandoned", "needs_human", "no_change"}


class Controller:
    def __init__(self, hub, memory, config: dict, llm_factory=None, redactor=None):
        self.hub, self.memory, self.config = hub, memory, config
        self.redactor = redactor or Redactor()
        self.llm_factory = llm_factory or (lambda: LiteLLMClient(config))
        self.calls = 0
        self.state = memory.state
        self.info = hub.repository_info()
        self.default = self.info["default_branch"]
        self.base = hub.ref(self.default)
        if not self.base:
            raise GuardError("The repository needs an existing default-branch commit")
        self.new_facts = 0

    def call(self, purpose: str, payload: dict) -> dict:
        if self.calls >= self.config["max_calls_per_cycle"]:
            raise GuardError("Per-cycle LLM budget exhausted")
        client = self.llm_factory()  # validate key/provider before reserving a paid attempt
        chars = len(canonical({"purpose": purpose, **payload}).decode()) + len(SYSTEM)
        self.memory.reserve_call(self.config, purpose, chars)
        self.calls += 1
        try:
            response, tokens = client.complete(purpose, payload)
        except GuardError:
            self.memory.record_usage(getattr(client, "last_tokens", 0))
            raise
        self.memory.record_usage(tokens)
        return response

    def mark_human(self, task: dict, reason: str) -> None:
        task["status"] = "needs_human"
        task["human_reason"] = reason
        self.memory.save("task_needs_human", {"id": task["id"], "reason": reason})
        if task.get("issue_number"):
            self.hub.needs_human(task["issue_number"])
            self.hub.comment(task["issue_number"], "Automatyzacja wstrzymana: " + self.redactor.public_text(reason))

    def collect(self, run_id: int | None = None) -> None:
        runs = [self.hub.run(run_id)] if run_id else self.hub.recent_runs(100)
        selected = [r for r in runs if accepted_run(r, self.hub.repository, self.default, self.config)
                    and f"{r['id']}:{r.get('run_attempt', 1)}" not in self.state["seen_runs"]]
        # Recent first for a busy repository. --run-id allows explicit historical backfill.
        for stub in selected[:self.config["max_runs_per_cycle"]]:
            run = self.hub.run(stub["id"])
            observation = ingest_run(self.hub, self.memory, run, self.config, self.default, self.redactor)
            if observation:
                self.new_facts += len(observation["fact_ids"])
                self.apply_verification(observation)
        # Recovery: a process may have committed facts but crashed before updating the learner.
        for task in list(self.state["tasks"].values()):
            for attempt in task["attempts"]:
                if attempt.get("outcome") is not None:
                    continue
                for run in runs:
                    identity = verification_identity(run)
                    if identity == (task.get("pr_number"), attempt["head_sha"]) and accepted_run(
                            run, self.hub.repository, self.default, self.config):
                        jobs = self.hub.run_jobs(run["id"], run.get("run_attempt", 1))
                        self.apply_verification({"run": run, "jobs": jobs, "fact_ids": []})

    def apply_verification(self, observation: dict) -> None:
        run = observation["run"]
        identity = verification_identity(run)
        if not identity:
            return
        number, head = identity
        # Only the fixed test job determines the Beta observation. Cancelled/infra/unknown != failure.
        test_jobs = [j for j in observation["jobs"] if j.get("name") == "Test candidate"]
        if len(test_jobs) != 1 or test_jobs[0].get("conclusion") not in {"success", "failure"}:
            return
        executed = [s for s in test_jobs[0].get("steps", [])
                    if s.get("name") == "Run fixed tests with a clean child environment"]
        if len(executed) != 1 or executed[0].get("conclusion") not in {"success", "failure"}:
            return  # setup/checkout failures are not evidence that candidate tests ran
        outcome = executed[0]["conclusion"]
        # A green test without a completed green resolver/reporter is not a trusted verification.
        if outcome == "success" and run.get("conclusion") != "success":
            return
        for task in self.state["tasks"].values():
            if task.get("pr_number") != number or task["status"] in TERMINAL:
                continue
            for attempt in task["attempts"]:
                if attempt["head_sha"] != head or attempt.get("outcome") is not None:
                    continue
                # Only the current candidate can change the task's execution state.
                if task["attempts"][-1]["head_sha"] != head:
                    continue
                current = self.hub.pull(number)
                if current["head"]["sha"] != head:
                    return
                attempt["outcome"] = outcome
                attempt["verification_run"] = run["id"]
                attempt["verification_attempt"] = run.get("run_attempt", 1)
                counts = self.state["profile_counts"][task["profile"]]
                counts["alpha" if outcome == "success" else "beta"] += 1
                self.state["consecutive_failures"] = 0 if outcome == "success" else self.state["consecutive_failures"] + 1
                task["status"] = "awaiting_merge" if outcome == "success" else "ready"
                if self.state["consecutive_failures"] >= self.config["max_failures_before_pause"]:
                    self.state["paused_reason"] = "Consecutive verified candidate failures reached the safety threshold"
                self.memory.save("candidate_verified", {"task": task["id"], "sha": head, "outcome": outcome,
                                                        "run_id": run["id"], "meaning": "pipeline test outcome, not proof of acceptance"})
                if outcome == "failure" and len(task["attempts"]) >= self.config["max_attempts_per_issue"]:
                    self.mark_human(task, "Wyczerpano limit prób poprawki dla tego zadania.")
                return

    def reconcile(self) -> None:
        for task in list(self.state["tasks"].values()):
            if task["status"] in TERMINAL:
                continue
            if task.get("issue_number") and not task.get("pr_number"):
                issue = self.hub.issue(task["issue_number"])
                if issue["state"] == "closed":
                    task["status"] = "abandoned"
                    self.memory.save("issue_closed_by_maintainer", {"task": task["id"]})
                    continue
            if not task.get("pr_number"):
                continue
            pr = self.hub.pull(task["pr_number"])
            if pr.get("merged"):
                task["status"] = "completed"
                self.state["facts"].append({"id": "merge:" + str(pr["number"]), "kind": "pull_request_merge",
                    "status": "observed", "text": f"PR #{pr['number']} was merged by GitHub; deployment outcome is separate.",
                    "source": pr["html_url"], "observed_at": now(), "head_sha": pr["head"]["sha"]})
                self.memory.save("pull_request_merged", {"task": task["id"], "pr": pr["number"]})
                continue
            if pr["state"] == "closed":
                task["status"] = "abandoned"
                self.memory.save("pull_request_closed_without_merge", {"task": task["id"]})
                continue
            expected = task["attempts"][-1]["head_sha"] if task["attempts"] else None
            prepared_head = (task.get("prepared") or {}).get("commit")
            if pr["head"]["sha"] not in {expected, prepared_head}:
                self.mark_human(task, "Gałąź PR została zmieniona poza kontrolerem; brak automatycznego nadpisywania.")
                continue
            if (pr["head"].get("repo") or {}).get("full_name") != self.hub.repository:
                self.mark_human(task, "PR nie pochodzi z zaufanego repozytorium.")
                continue
            if task["status"] == "awaiting_merge" and not self.state["paused_reason"]:
                self.maybe_auto_merge(task)
            elif task["status"] == "verifying" and task["attempts"]:
                attempt = task["attempts"][-1]
                stamp = attempt.get("dispatch_at")
                age = (datetime.now(timezone.utc) - datetime.fromisoformat(stamp)).total_seconds() if stamp else 1e9
                if age > 3600:
                    if attempt.get("dispatches", 0) < 2:
                        self.dispatch(task)
                    else:
                        self.mark_human(task, "Nie uzyskano wiarygodnego wyniku weryfikacji po dwóch uruchomieniach.")

    def maybe_auto_merge(self, task: dict) -> None:
        if os.getenv("INTUITION_AUTOMERGE", "false").lower() != "true" or task.get("automerge_requested"):
            return
        try:
            protection = self.hub.api(f"{self.hub.prefix}/branches/{quote(self.default, safe='')}/protection")
            required = protection.get("required_status_checks") or {}
            contexts = set(required.get("contexts", [])) | {x.get("context") for x in required.get("checks", [])}
            if (not required.get("strict") or "Intuition / verified" not in contexts
                    or not protection.get("enforce_admins", {}).get("enabled")
                    or protection.get("allow_force_pushes", {}).get("enabled")):
                raise GuardError("Auto-merge requires strict classic protection, Intuition / verified, enforced admins and no force pushes")
            pr = self.hub.pull(task["pr_number"])
            head = task["attempts"][-1]["head_sha"]
            if pr["head"]["sha"] != head or pr["base"]["ref"] != self.default:
                raise GuardError("PR identity changed")
            statuses = self.hub.api(f"{self.hub.prefix}/commits/{head}/status")["statuses"]
            matching = [s for s in statuses if s["context"] == "Intuition / verified"]
            if not matching or matching[0]["state"] != "success":
                raise GuardError("The exact candidate SHA has no successful trusted status")
            self.hub.command(["pr", "merge", str(pr["number"]), "--repo", self.hub.repository,
                              "--auto", "--squash", "--match-head-commit", head])
            task["automerge_requested"] = True
            self.memory.save("automerge_requested", {"task": task["id"], "sha": head})
        except (GuardError, GhError):
            # Fail closed. No --admin, direct branch push, ruleset bypass, or relaxed fallback.
            if not task.get("automerge_blocked"):
                task["automerge_blocked"] = True
                self.memory.save("automerge_blocked", {"task": task["id"]})
                self.hub.comment(task["issue_number"], "Auto-merge zablokowany: sprawdź uprawnienia odczytu ochrony gałęzi, wymagane statusy i reguły. PR pozostaje do ręcznego scalenia.")

    def snapshot(self) -> tuple[dict[str, bytes], list[dict]]:
        tree = self.hub.tree(self.base)
        paths = sorted(p for p, item in tree.items() if path_allowed(p, self.config)
                       and item.get("mode") == "100644" and item.get("type") == "blob")[:12]
        source, facts = {}, []
        remaining = self.config["max_input_chars"] // 3
        existing_ids = {f["id"] for f in self.state["facts"]}
        for path in paths:
            if tree[path].get("size", 0) > self.config["max_file_bytes"]:
                continue
            raw = self.hub.blob(tree[path]["sha"], self.config["max_file_bytes"])
            try:
                value = raw.decode("utf-8")
            except UnicodeDecodeError:
                continue
            if self.redactor.clean(value) != value or len(value) > remaining:
                continue
            remaining -= len(value)
            source[path] = raw
            fid = "code:" + self.base + ":" + digest(path.encode())[:12]
            fact = {"id": fid, "kind": "source_snapshot", "status": "observed", "head_sha": self.base,
                    "text": f"Source file {path} at commit {self.base}, sha256 {digest(raw)}.",
                    "source": f"https://github.com/{self.hub.repository}/blob/{self.base}/{path}", "observed_at": now()}
            facts.append(fact)
            if fid not in existing_ids:
                self.state["facts"].append(fact)
        self.state["facts"] = self.state["facts"][-200:]
        if facts:
            self.memory.save("source_snapshot", {"sha": self.base, "files": list(source)})
        return source, facts

    def context_facts(self, candidates: list[dict]) -> list[dict]:
        # Select recent unique records within a serialized budget; keep full originals in Git.
        selected, seen = [], set()
        remaining = self.config["max_input_chars"] // 4
        for fact in reversed(candidates):
            if fact["id"] in seen:
                continue
            seen.add(fact["id"])
            item = {**fact, "text": fact["text"][-2000:]}
            cost = len(canonical(item).decode())
            if cost > remaining:
                continue
            remaining -= cost
            selected.append(item)
            if len(selected) >= self.config["max_context_facts"]:
                break
        return list(reversed(selected))

    def ensure_issue(self, task: dict) -> None:
        if task.get("issue_number"):
            return
        marker = f"<!-- intuition-task:{task['id']} -->"
        matches = [i for i in self.hub.issues() if marker in (i.get("body") or "") and "pull_request" not in i]
        if len(matches) > 1:
            raise GuardError("Multiple matching issues; manual deduplication required")
        issue = matches[0] if matches else self.hub.create_issue(
            "[Intuition] " + self.redactor.public_text(task["title"]),
            issue_body(task, task["evidence"], self.hub.repository, self.redactor))
        task["issue_number"] = issue["number"]
        task["status"] = "ready" if issue["state"] == "open" else "abandoned"
        self.memory.save("issue_linked", {"task": task["id"], "issue": issue["number"]})

    def propose(self) -> None:
        issues = self.hub.issues()
        if sum(i["state"] == "open" and "pull_request" not in i for i in issues) >= self.config["max_open_issues"]:
            return
        source, _ = self.snapshot()
        if not source:
            return
        facts = self.context_facts(self.state["facts"])
        context_key = digest(canonical([self.base, [f["id"] for f in facts], self.config]))
        if self.state["last_plan_context"] == context_key:
            return
        payload = {"goal": self.config["goal"], "base_sha": self.base, "output_contract": TASK_CONTRACT,
                   "profiles": list(self.config["profiles"]), "untrusted_facts": facts,
                   "untrusted_source_files": {p: b.decode() for p, b in source.items()},
                   "existing_tasks": [{"profile": t["profile"], "target_files": t["target_files"], "status": t["status"]}
                                      for t in list(self.state["tasks"].values())[-30:]]}
        previous = self.state.get("plan_failure", {})
        failures = previous.get("count", 0) if previous.get("context") == context_key else 0
        if failures >= self.config["max_attempts_per_issue"]:
            return
        if failures:
            payload["validation_feedback"] = previous["reason"]
        calls_before = self.calls
        try:
            response = self.call("propose_tasks", payload)
            tasks = validate_tasks(response, self.base, facts, list(source), self.config, self.state)
        except GuardError as exc:
            if self.calls == calls_before:
                raise  # Budget/configuration rejection is not a model failure.
            reason = str(exc) if str(exc).startswith("schema_") else type(exc).__name__
            self.state["plan_failure"] = {"context": context_key, "count": failures + 1, "reason": reason}
            self.memory.save("plan_generation_rejected", self.state["plan_failure"])
            return  # Retry on the next cycle, with existing daily/cycle limits.
        self.state.pop("plan_failure", None)
        self.state["last_plan_context"] = context_key
        for task in tasks[:self.config["max_new_issues_per_cycle"]]:
            task["evidence"] = [f for f in facts if f["id"] in task["fact_ids"]]
            self.state["tasks"][task["id"]] = task
        self.memory.save("tasks_ranked", {"candidate_count": len(tasks), "context": context_key})
        for task in tasks[:self.config["max_new_issues_per_cycle"]]:
            self.ensure_issue(task)

    def generate_patch(self, task: dict) -> None:
        if task.get("prepared"):
            self.publish_prepared(task)
            return
        if len(task["attempts"]) >= self.config["max_attempts_per_issue"]:
            self.mark_human(task, "Limit prób dla zadania został wyczerpany.")
            return
        base = task["attempts"][-1]["head_sha"] if task["attempts"] else self.base
        if not task["attempts"] and task["base_sha"] != self.base:
            self.mark_human(task, "Baza zadania jest nieaktualna; wymagane ponowne rozpatrzenie dowodów.")
            return
        original = self.hub.files(base, task["target_files"], self.config["max_file_bytes"])
        if any(self.redactor.clean(data.decode()) != data.decode() for data in original.values()):
            self.mark_human(task, "Plik źródłowy może zawierać sekret; nie wysłano go do LLM.")
            return
        payload = {"base_sha": base, "output_contract": PATCH_CONTRACT,
                   "task": {k: task[k] for k in ("title", "profile", "acceptance", "rationale", "target_files")},
                   "untrusted_facts": self.context_facts(task["evidence"] + self.state["facts"][-12:]),
                   "untrusted_files": [{"path": p, "sha256": digest(data), "content": data.decode()}
                                       for p, data in original.items()],
                   "max_changed_lines": self.config["max_patch_changed_lines"]}
        try:
            response = self.call("propose_patch", payload)
            files = validate_patch(response, base, original, self.config, self.redactor)
        except GuardError as exc:
            # Budget exhaustion does not mean the task failed.
            if "budget" in str(exc).lower() or "limit exceeded" in str(exc).lower() and self.calls == 0:
                raise
            task["generation_failures"] += 1
            self.memory.save("patch_generation_rejected", {"task": task["id"], "reason_type": type(exc).__name__})
            if task["generation_failures"] >= self.config["max_attempts_per_issue"]:
                self.mark_human(task, "Model nie dostarczył poprawnej propozycji w dozwolonym limicie.")
            return
        if not files:
            task["status"] = "no_change"
            self.memory.save("no_justified_change", {"task": task["id"]})
            self.hub.comment(task["issue_number"], "Model nie zaproponował uzasadnionej zmiany. Nie utworzono pustego PR; decyzja należy do opiekuna.")
            return
        branch = f"intuition/issue-{task['issue_number']}-{task['id'][:12]}"
        commit = self.hub.create_commit(base, files, f"refactor: intuition task {task['id']} attempt {len(task['attempts'])+1}")
        task["prepared"] = {"commit": commit, "parent": base, "branch": branch,
                            "summary": self.redactor.public_text(response["summary"])}
        # Store the immutable remote commit ID BEFORE moving a branch or creating a PR.
        self.memory.save("patch_prepared", {"task": task["id"], "commit": commit, "files": list(files)})
        self.publish_prepared(task)

    def publish_prepared(self, task: dict) -> None:
        pending = task["prepared"]
        expected = pending["parent"] if task["attempts"] else None
        self.hub.advance_ref(pending["branch"], pending["commit"], expected)
        pulls = self.hub.pulls(pending["branch"], "all")
        if len(pulls) > 1:
            raise GuardError("Ambiguous existing pull request")
        body = (f"<!-- intuition-task:{task['id']} -->\nCloses #{task['issue_number']}\n\n"
                + pending["summary"] + "\n\nKod wygenerowany przez LLM. Weryfikacja odbywa się w osobnym jobie bez klucza LLM. "
                "Zielone testy nie zastępują przeglądu bezpieczeństwa i kryteriów odbioru.")
        pr = pulls[0] if pulls else self.hub.create_pull(pending["branch"], self.default,
                "[Intuition] " + self.redactor.public_text(task["title"]), body)
        if pr["state"] != "open" or pr["head"]["sha"] != pending["commit"]:
            self.mark_human(task, "PR zamknięty lub niezgodny z przygotowanym commitem.")
            return
        task["pr_number"] = pr["number"]
        if not any(a["head_sha"] == pending["commit"] for a in task["attempts"]):
            task["attempts"].append({"head_sha": pending["commit"], "created_at": now(), "outcome": None,
                                     "dispatches": 0, "dispatch_at": None})
        task["prepared"] = None
        task["status"] = "verifying"
        self.memory.save("pull_request_published", {"task": task["id"], "pr": pr["number"]})
        self.dispatch(task)

    def dispatch(self, task: dict) -> None:
        attempt = task["attempts"][-1]
        if attempt.get("outcome") is not None:
            return
        current = self.hub.pull(task["pr_number"])
        if current["head"]["sha"] != attempt["head_sha"] or current["state"] != "open":
            self.mark_human(task, "PR zmienił się przed uruchomieniem weryfikacji.")
            return
        attempt["dispatches"] += 1
        attempt["dispatch_at"] = now()
        self.memory.save("verification_dispatch_reserved", {"task": task["id"], "sha": attempt["head_sha"]})
        self.hub.set_status(attempt["head_sha"], "pending", current["html_url"])
        self.hub.dispatch_verification(task["pr_number"], attempt["head_sha"], self.default)

    def ensure_default_ci(self) -> None:
        # GITHUB_TOKEN pushes/merges need not trigger push workflows. Explicit reconciliation.
        if self.state["last_ci_requested_sha"] == self.base:
            return
        runs = self.hub.recent_runs(100)
        exists = any(r.get("head_sha") == self.base and r.get("head_branch") == self.default
                     and r.get("path", "").split("@")[0] == ".github/workflows/ci.yml"
                     and r.get("event") in {"push", "workflow_dispatch"} for r in runs)
        if not exists:
            self.hub.dispatch_ci(self.default)
        # A failed remote dispatch must not permanently latch this SHA as requested.
        # A crash after dispatch can cause one harmless duplicate CI run, not a paid LLM retry.
        self.state["last_ci_requested_sha"] = self.base
        self.memory.save("default_ci_observed" if exists else "default_ci_dispatched", {"sha": self.base})

    def cycle(self, run_id: int | None = None, reset_circuit: bool = False) -> dict:
        self.hub.ensure_labels()
        if reset_circuit:
            self.state["paused_reason"], self.state["consecutive_failures"] = None, 0
            self.memory.save("circuit_reset_by_operator")
        self.collect(run_id)
        self.reconcile()
        if self.state["paused_reason"]:
            return self.summary("paused")
        self.ensure_default_ci()
        # Recover queued work before generating any new idea.
        for task in list(self.state["tasks"].values()):
            if task["status"] == "proposed":
                self.ensure_issue(task)
        ready = [t for t in self.state["tasks"].values() if t["status"] == "ready" or t.get("prepared")]
        open_prs = [p for p in self.hub.pulls() if p["head"]["ref"].startswith("intuition/")]
        if not ready and len(open_prs) < self.config["max_open_prs"]:
            self.propose()
            ready = [t for t in self.state["tasks"].values() if t["status"] == "ready"]
        for task in sorted(ready, key=lambda t: (-t["score"], t["id"])):
            if task["status"] in TERMINAL:
                continue
            if task.get("pr_number") or len(open_prs) < self.config["max_open_prs"]:
                self.generate_patch(task)
                break  # one patch/cycle, including retries
        return self.summary("complete")

    def summary(self, status: str) -> dict:
        return {"status": status, "memory_commit": self.memory.head, "default_sha": self.base,
                "new_facts": self.new_facts, "llm_calls": self.calls, "paused_reason": self.state["paused_reason"],
                "tasks": [{"id": t["id"], "issue": t["issue_number"], "pr": t["pr_number"], "status": t["status"]}
                          for t in self.state["tasks"].values()]}
