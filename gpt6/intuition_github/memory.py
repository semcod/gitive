"""Versioned memory on a dedicated branch using Git objects, accessed through gh."""
from __future__ import annotations
import json
import re
import uuid
from .util import GuardError, canonical, now


def initial_state(config: dict) -> dict:
    return {"schema_version": 2, "facts": [], "seen_runs": [], "tasks": {}, "budgets": {},
            "profile_counts": {k: {"alpha": v["alpha"], "beta": v["beta"]} for k, v in config["profiles"].items()},
            "consecutive_failures": 0, "paused_reason": None, "last_plan_context": None,
            "last_ci_requested_sha": None, "sequence": 0}


class Memory:
    def __init__(self, hub, config: dict):
        self.hub, self.branch = hub, config["memory_branch"]
        if not re.fullmatch(r"intuition-memory(?:-[a-z0-9-]+)?", self.branch):
            raise GuardError("Memory must use a dedicated intuition-memory[-suffix] branch")
        self.head = hub.ref(self.branch)
        if self.head:
            files = hub.files(self.head, ["state.json"], max_bytes=2_000_000)
            self.state = json.loads(files["state.json"])
            if self.state.get("schema_version") != 2:
                raise GuardError("Unsupported memory version; do not reset or discard budgets automatically")
        else:
            self.state = initial_state(config)

    def save(self, kind: str, detail: dict | None = None, extra: dict[str, bytes] | None = None) -> str:
        # Bound materialized state; all prior snapshots and full evidence remain in Git.
        self.state["facts"] = self.state["facts"][-200:]
        self.state["seen_runs"] = self.state["seen_runs"][-5000:]
        for task in self.state["tasks"].values():
            if task["status"] in {"completed", "abandoned", "needs_human", "no_change"}:
                for fact in task.get("evidence", []):
                    fact["text"] = fact["text"][:400]
        terminals = sorted((t for t in self.state["tasks"].values()
                            if t["status"] in {"completed", "abandoned", "needs_human", "no_change"}),
                           key=lambda t: t["created_at"])
        for task in terminals[:-100]:
            del self.state["tasks"][task["id"]]
        for day in sorted(self.state["budgets"])[:-90]:
            del self.state["budgets"][day]
        if len(canonical(self.state)) > 1_800_000:
            raise GuardError("Materialized memory limit reached; archive/compact under maintainer control")
        self.state["sequence"] += 1
        event = {"sequence": self.state["sequence"], "at": now(), "kind": kind, "detail": detail or {}}
        files = {"state.json": canonical(self.state),
                 f"events/{self.state['sequence']:09d}-{uuid.uuid4().hex}.json": canonical(event)}
        for path, data in (extra or {}).items():
            if not re.fullmatch(r"evidence/[0-9a-f]{64}\.(?:txt|json)", path):
                raise GuardError("Unapproved evidence path")
            files[path] = data
        commit = self.hub.create_commit(self.head, files, f"Intuition memory: {kind}")
        self.hub.advance_ref(self.branch, commit, self.head)
        self.head = commit
        return commit

    def reserve_call(self, config: dict, purpose: str, input_chars: int) -> None:
        day = now()[:10]  # UTC, independent of local operator timezone
        ledger = self.state["budgets"].setdefault(day, {"calls": 0, "reserved_output_tokens": 0,
                                                     "input_chars": 0, "actual_tokens": 0})
        if ledger["calls"] >= config["max_calls_per_day"]:
            raise GuardError("Daily LLM request budget exhausted")
        if input_chars > config["max_input_chars"]:
            raise GuardError("LLM context exceeds the configured character budget")
        ledger["calls"] += 1
        ledger["reserved_output_tokens"] += config["max_output_tokens"]
        ledger["input_chars"] += input_chars
        # Persist BEFORE the paid call, including failed/time-out requests.
        self.save("llm_call_reserved", {"purpose": purpose, "day": day, "input_chars": input_chars})

    def record_usage(self, total_tokens: int) -> None:
        day = now()[:10]
        ledger = self.state["budgets"].setdefault(day, {"calls": 0, "reserved_output_tokens": 0,
                                                     "input_chars": 0, "actual_tokens": 0})
        ledger["actual_tokens"] += max(0, int(total_tokens))
        self.save("llm_usage", {"tokens": max(0, int(total_tokens))})
