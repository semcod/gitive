"""Fact ingestion.

A fact is an immutable observation with a timestamp. Two families:

  achievement  commit, merged PR, closed issue, green CI run
               -> accumulate into the state vector s_t ("what the project is")

  friction     failed CI run + its error signature, revert, FIXME/TODO marker
               -> accumulate into the friction vector r_t ("what hurts")

Keeping them separate matters: a red pipeline is not progress, and folding it
into s_t would make the model believe the failure is already handled.
"""
from __future__ import annotations

import json
import re
import subprocess
from datetime import datetime, timezone
from typing import Any, Iterable

from .store import content_id

ACHIEVEMENT = {"commit", "pr_merged", "issue_closed", "ci_success"}
FRICTION = {"ci_failure", "revert", "marker"}

_TS = re.compile(r"^\S*\s*\d{4}-\d{2}-\d{2}T[\d:.]+Z\s?")
_NOISE = re.compile(r"^(\s*at |\s*\d+ \| |##\[group\]|##\[endgroup\]|Download|Requirement already)")
_SIGNAL = re.compile(
    r"(Traceback|Error|error:|ERROR|FAILED|FAIL:|AssertionError|Exception|"
    r"npm ERR!|panic:|fatal:|exit code|Process completed with exit code|"
    r"undefined reference|cannot find|not found|timed out|SIGSEGV)"
)


def _run(args: list[str], cwd: str | None = None, timeout: int = 120) -> str:
    try:
        p = subprocess.run(args, cwd=cwd, capture_output=True, text=True, timeout=timeout)
    except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
        print(f"[intuition] {' '.join(args[:2])} unavailable: {exc}")
        return ""
    if p.returncode != 0 and not p.stdout:
        print(f"[intuition] {' '.join(args[:3])} failed: {p.stderr.strip()[:200]}")
        return ""
    return p.stdout


def _iso(ts: str) -> float:
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00")).timestamp()
    except ValueError:
        return datetime.now(timezone.utc).timestamp()


# --------------------------------------------------------------------------
# git
# --------------------------------------------------------------------------

def git_facts(limit: int = 200, cwd: str | None = None) -> list[dict[str, Any]]:
    sep = "\x1e"
    fmt = sep.join(["%H", "%ct", "%an", "%s", "%b"]) + "\x1d"
    out = _run(["git", "log", f"-{limit}", f"--pretty=format:{fmt}", "--no-merges"], cwd)
    facts: list[dict[str, Any]] = []
    for rec in out.split("\x1d"):
        rec = rec.strip("\n")
        if not rec.strip():
            continue
        parts = rec.split(sep)
        if len(parts) < 4:
            continue
        sha, ct, author, subject = parts[0], parts[1], parts[2], parts[3]
        body = parts[4] if len(parts) > 4 else ""
        files = _run(["git", "show", "--name-only", "--pretty=format:", sha], cwd)
        paths = [f for f in files.splitlines() if f.strip()][:20]
        kind = "revert" if subject.lower().startswith("revert") else "commit"
        text = f"{subject}\n{body}\n" + "\n".join(paths)
        facts.append({
            "id": content_id("git", sha),
            "ts": float(ct),
            "kind": kind,
            "source": "git",
            "ref": sha[:12],
            "author": author,
            "paths": paths,
            "text": text.strip(),
        })
    return facts


def marker_facts(cwd: str | None = None, limit: int = 60) -> list[dict[str, Any]]:
    """FIXME/HACK markers are friction the compiler never reports."""
    out = _run(["git", "grep", "-nI", "-E", r"(FIXME|HACK|XXX|TODO\(.*\)):?"], cwd)
    now = datetime.now(timezone.utc).timestamp()
    facts = []
    for line in out.splitlines()[:limit]:
        parts = line.split(":", 2)
        if len(parts) < 3:
            continue
        path, lineno, body = parts
        facts.append({
            "id": content_id("marker", path, lineno, body.strip()),
            "ts": now,
            "kind": "marker",
            "source": "grep",
            "ref": f"{path}:{lineno}",
            "paths": [path],
            "text": f"{path}: {body.strip()}",
        })
    return facts


# --------------------------------------------------------------------------
# GitHub Actions
# --------------------------------------------------------------------------

def error_signature(log: str, max_lines: int = 30) -> str:
    """Compress a CI log down to the lines that actually carry information."""
    seen: set[str] = set()
    keep: list[str] = []
    for raw in log.splitlines():
        line = _TS.sub("", raw).rstrip()
        if not line or _NOISE.match(line) or not _SIGNAL.search(line):
            continue
        norm = re.sub(r"0x[0-9a-f]+|\b\d{3,}\b|/tmp/\S+", "N", line)[:220]
        if norm in seen:
            continue
        seen.add(norm)
        keep.append(line[:220])
        if len(keep) >= max_lines:
            break
    return "\n".join(keep)


def ci_facts(limit: int = 20, cwd: str | None = None, fetch_logs: bool = True) -> list[dict[str, Any]]:
    fields = "databaseId,workflowName,conclusion,headBranch,createdAt,event,displayTitle"
    out = _run(["gh", "run", "list", "--limit", str(limit), "--json", fields], cwd)
    if not out.strip():
        return []
    try:
        runs = json.loads(out)
    except json.JSONDecodeError:
        return []

    facts: list[dict[str, Any]] = []
    for r in runs:
        rid = str(r.get("databaseId"))
        concl = (r.get("conclusion") or "").lower()
        if concl not in ("success", "failure", "timed_out"):
            continue
        ts = _iso(r.get("createdAt", ""))
        wf = r.get("workflowName", "workflow")
        title = r.get("displayTitle", "")
        branch = r.get("headBranch", "")
        if concl == "success":
            facts.append({
                "id": content_id("ci", rid),
                "ts": ts,
                "kind": "ci_success",
                "source": "actions",
                "ref": rid,
                "paths": [],
                "text": f"CI green: {wf} on {branch} ({title})",
            })
            continue

        sig = ""
        if fetch_logs:
            log = _run(["gh", "run", "view", rid, "--log-failed"], cwd, timeout=180)
            sig = error_signature(log)
        facts.append({
            "id": content_id("ci", rid),
            "ts": ts,
            "kind": "ci_failure",
            "source": "actions",
            "ref": rid,
            "paths": [],
            "text": f"CI FAILING: {wf} on {branch} ({title})\n{sig}".strip(),
        })
    return facts


def collect(cfg: Any, cwd: str | None = None) -> list[dict[str, Any]]:
    facts: list[dict[str, Any]] = []
    facts += git_facts(cfg.git_lookback, cwd)
    facts += ci_facts(cfg.ci_lookback, cwd)
    facts += marker_facts(cwd)
    return facts


def dedupe(new: Iterable[dict[str, Any]], known: set[str]) -> list[dict[str, Any]]:
    out, seen = [], set(known)
    for f in new:
        if f["id"] in seen:
            continue
        seen.add(f["id"])
        out.append(f)
    return out
