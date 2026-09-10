"""Reference planner: Python standard library only. No model-supplied scores."""
from __future__ import annotations
import copy
import hashlib
import json
import math
import re
from dataclasses import dataclass
from typing import Any


def number(value: Any, label: str, lo: float = 0, hi: float = math.inf) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{label}: expected a number")
    if not math.isfinite(value) or not lo <= value <= hi:
        raise ValueError(f"{label}: out of range")
    return float(value)


def text(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > 10000:
        raise ValueError(f"{label}: expected nonempty text, max 10000 characters")
    return value


def identifier(value: Any, label: str) -> str:
    value = text(value, label)
    if not re.fullmatch(r"[A-Za-z0-9_:.-]{1,128}", value):
        raise ValueError(f"{label}: invalid identifier")
    return value


def identifiers(value: Any, label: str) -> list[str]:
    if not isinstance(value, list):
        raise ValueError(f"{label}: expected a list")
    values = [identifier(v, label) for v in value]
    if len(values) != len(set(values)):
        raise ValueError(f"{label}: duplicate identifier")
    return values


def entropy(p: float) -> float:
    number(p, "probability", 0, 1)
    return 0.0 if p in (0, 1) else -p * math.log2(p) - (1-p) * math.log2(1-p)


def information_gain(prior: float, sensitivity: float, false_positive: float) -> float:
    """I(H;Y) in bits for a binary observation, conditional on a usable result."""
    p = number(prior, "prior", 0, 1)
    s = number(sensitivity, "sensitivity", 0, 1)
    f = number(false_positive, "false_positive", 0, 1)
    q = p*s + (1-p)*f
    return max(0.0, entropy(q) - p*entropy(s) - (1-p)*entropy(f))


def posterior(prior: float, sensitivity: float, false_positive: float, positive: bool) -> float:
    p = number(prior, "prior", 0, 1)
    s = number(sensitivity, "sensitivity", 0, 1)
    f = number(false_positive, "false_positive", 0, 1)
    if type(positive) is not bool:
        raise ValueError("positive: expected boolean")
    a, b = (s, f) if positive else (1-s, 1-f)
    denominator = p*a + (1-p)*b
    if denominator == 0:
        raise ValueError("Observation impossible under the declared model; review the model")
    return p*a / denominator


@dataclass(frozen=True)
class Task:
    id: str
    title: str
    profile: str
    facts: tuple[str, ...]
    depends_on: tuple[str, ...]
    acceptance: str

    @classmethod
    def parse(cls, raw: Any) -> Task:
        keys = {"id", "title", "profile", "facts", "depends_on", "acceptance"}
        if not isinstance(raw, dict) or set(raw) != keys:
            raise ValueError("Task: incorrect fields; LLM may not supply scores or commands")
        return cls(identifier(raw["id"], "id"), text(raw["title"], "title"),
                   identifier(raw["profile"], "profile"), tuple(identifiers(raw["facts"], "facts")),
                   tuple(identifiers(raw["depends_on"], "depends_on")), text(raw["acceptance"], "acceptance"))

    def key(self, goal: str) -> str:
        # ASCII serialization is identical in both reference implementations.
        raw = json.dumps([goal, self.profile, sorted(self.facts)], ensure_ascii=True, separators=(",", ":"))
        return hashlib.sha256(raw.encode()).hexdigest()


def validate_state(state: dict) -> None:
    text(state["goal"], "goal")
    for name in ("budget", "information_weight", "min_score"):
        number(state[name], name, 0, 1e12)
    number(state["max_risk"], "max_risk", 0, 1e12)
    facts = state["facts"]
    if not isinstance(facts, list):
        raise ValueError("facts: expected a list")
    identifiers([f["id"] for f in facts], "fact IDs")
    for fact in facts:
        text(fact["text"], "fact text")
        text(fact["source"], "fact source")
        if fact["status"] not in ("observed", "reported", "disputed"):
            raise ValueError("Invalid fact status")
    for value in state["hypotheses"].values():
        number(value, "hypothesis", 0, 1)
    for profile in state["profiles"].values():
        number(profile["alpha"], "alpha", 1e-12, 1e12)
        number(profile["beta"], "beta", 1e-12, 1e12)
        for name in ("benefit", "cost", "risk"):
            number(profile[name], name, 0, 1e12)
        for name in ("sensitivity", "false_positive"):
            number(profile[name], name, 0, 1)
        if type(profile["allowed"]) is not bool:
            raise ValueError("allowed: expected boolean")
        for name in ("diagnostic_hypothesis", "effect_hypothesis"):
            if profile[name] is not None and profile[name] not in state["hypotheses"]:
                raise ValueError("Unknown profile hypothesis")
    for name in ("completed_keys", "completed_ids", "successful_ids", "seen_evidence", "seen_events"):
        identifiers(state[name], name)


def rank(state: dict, raw_tasks: Any) -> dict:
    validate_state(state)
    if state["pending"] is not None:
        raise ValueError("Observe or resolve the pending task before another plan")
    if not isinstance(raw_tasks, list) or len(raw_tasks) > 8:
        raise ValueError("Expected at most eight candidate tasks")
    tasks = [Task.parse(t) for t in raw_tasks]
    identifiers([t.id for t in tasks], "task IDs")
    known_facts = {f["id"] for f in state["facts"]}
    completed = set(state["completed_ids"])
    successful = set(state["successful_ids"])
    candidate_ids = {t.id for t in tasks}
    valid: list[dict] = []
    rejected: list[dict] = []
    keys: set[str] = set()
    # Entire proposal is rejected if any citation/profile/dependency is invented.
    for task in tasks:
        if not task.facts or not set(task.facts) <= known_facts:
            raise ValueError(f"{task.id}: missing or unknown facts")
        if task.profile not in state["profiles"]:
            raise ValueError(f"{task.id}: unknown profile")
        if not set(task.depends_on) <= completed | candidate_ids or task.id in task.depends_on:
            raise ValueError(f"{task.id}: invalid dependencies")
    # Validate the proposed dependency DAG.
    by_id = {t.id: t for t in tasks}
    visiting: set[str] = set()
    visited: set[str] = set()
    def visit(tid: str) -> None:
        if tid in visiting:
            raise ValueError("Cyclic dependencies")
        if tid in visited or tid not in by_id:
            return
        visiting.add(tid)
        for dependency in by_id[tid].depends_on:
            visit(dependency)
        visiting.remove(tid)
        visited.add(tid)
    for task in tasks:
        visit(task.id)
    for task in tasks:
        profile = state["profiles"][task.profile]
        key = task.key(state["goal"])
        reason = None
        if task.id in completed or key in state["completed_keys"] or key in keys:
            reason = "duplicate"
        elif not set(task.depends_on) <= successful:
            reason = "blocked"
        elif not profile["allowed"] or profile["risk"] > state["max_risk"]:
            reason = "policy"
        elif profile["cost"] > state["budget"]:
            reason = "budget"
        # Deduplicate feasible candidates only, so a blocked duplicate cannot hide one.
        if reason:
            rejected.append({"id": task.id, "reason": reason})
            continue
        keys.add(key)
        p = profile["alpha"] / (profile["alpha"] + profile["beta"])
        h = profile["diagnostic_hypothesis"]
        ig = 0.0 if h is None else information_gain(state["hypotheses"][h], profile["sensitivity"], profile["false_positive"])
        effect = profile["effect_hypothesis"]
        relevance = 1.0 if effect is None else state["hypotheses"][effect]
        gain = profile["benefit"] * relevance
        score = p * (gain + state["information_weight"] * ig) - profile["cost"] - profile["risk"]
        valid.append({"task": {"id": task.id, "title": task.title, "profile": task.profile,
                               "facts": list(task.facts), "depends_on": list(task.depends_on), "acceptance": task.acceptance},
                      "key": key, "probability": p, "information_gain": ig, "expected_benefit": p*gain, "score": score})
    valid.sort(key=lambda v: (-v["score"], v["task"]["id"]))
    selected = valid[0] if valid and valid[0]["score"] > state["min_score"] else None
    return {"selected": selected, "ranking": valid, "rejected": rejected,
            "status": "selected" if selected else "stop_or_request_evidence"}


def accept_plan(state: dict, decision: dict) -> dict:
    updated = copy.deepcopy(state)
    updated["pending"] = copy.deepcopy(decision["selected"])
    return updated


def observe(state: dict, event: dict, evidence: bytes) -> dict:
    validate_state(state)
    required = {"event_id", "task_id", "success", "positive", "summary"}
    if not isinstance(event, dict) or set(event) != required:
        raise ValueError("Invalid observation fields")
    identifier(event["event_id"], "event_id")
    text(event["summary"], "summary")
    if type(event["success"]) is not bool:
        raise ValueError("success must be a verified binary result, not unknown")
    if not evidence or len(evidence) > 1_000_000:
        raise ValueError("Evidence must contain 1..1000000 bytes")
    digest = hashlib.sha256(evidence).hexdigest()
    if event["event_id"] in state["seen_events"] or digest in state["seen_evidence"]:
        raise ValueError("Reused evidence/event cannot be counted twice")
    pending = state["pending"]
    if pending is None or event["task_id"] != pending["task"]["id"]:
        raise ValueError("No matching pending task")
    updated = copy.deepcopy(state)
    profile = updated["profiles"][pending["task"]["profile"]]
    h = profile["diagnostic_hypothesis"]
    if h is not None and event["success"]:
        updated["hypotheses"][h] = posterior(updated["hypotheses"][h], profile["sensitivity"], profile["false_positive"], event["positive"])
    elif event["positive"] is not None:
        raise ValueError("A failed/non-diagnostic task must have positive=null")
    profile["alpha" if event["success"] else "beta"] += 1
    updated["budget"] = max(0.0, updated["budget"] - profile["cost"])
    updated["completed_keys"].append(pending["key"])
    updated["completed_ids"].append(event["task_id"])
    if event["success"]:
        updated["successful_ids"].append(event["task_id"])
    updated["seen_evidence"].append(digest)
    updated["seen_events"].append(event["event_id"])
    fact_id = "observation:" + event["event_id"]
    if fact_id in {f["id"] for f in updated["facts"]}:
        raise ValueError("Duplicate observation fact ID")
    updated["facts"].append({"id": fact_id, "text": event["summary"], "status": "reported",
                             "source": "evidence/" + digest + ".bin"})
    # Imported observation is 'reported': bytes/hash do not prove its interpretation.
    updated["pending"] = None
    return updated
