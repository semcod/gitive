"""Trusted workflow helpers. Never execute candidate code in this process."""
from __future__ import annotations
import re
from pathlib import Path
from .config import path_allowed
from .util import GuardError, integer, sha, canonical, digest


def resolve_candidate(hub, config: dict, number: int, expected_head: str) -> dict:
    number, expected_head = integer(number), sha(expected_head)
    info = hub.repository_info()
    pr = hub.pull(number)
    if (pr["state"] != "open" or (pr["head"].get("repo") or {}).get("full_name") != hub.repository
            or pr["base"]["ref"] != info["default_branch"]
            or not re.fullmatch(r"intuition/issue-\d+-[0-9a-f]{12}", pr["head"]["ref"])
            or pr["head"]["sha"] != expected_head):
        raise GuardError("Candidate PR identity/source/head does not match the dispatched request")
    files = hub.pages(f"{hub.prefix}/pulls/{number}/files")
    if not 1 <= len(files) <= config["max_files_per_patch"]:
        raise GuardError("Candidate file count is outside policy")
    if any(f["status"] != "modified" or not path_allowed(f["filename"], config) for f in files):
        raise GuardError("Candidate changes protected/new/deleted/renamed paths")
    # A retry PR can contain several incremental patches, but still has a total bound.
    if sum(f.get("changes", 0) for f in files) > config["max_patch_changed_lines"] * config["max_attempts_per_issue"]:
        raise GuardError("Total candidate diff is too large")
    tree = hub.tree(expected_head)
    if any(tree.get(f["filename"], {}).get("mode") != "100644" for f in files):
        raise GuardError("Symlinks/executables/submodules are not allowed")
    base = sha(pr["base"]["sha"])
    if hub.ref(info["default_branch"]) != base:
        raise GuardError("PR base is not current")
    merge = sha(pr.get("merge_commit_sha"))
    parents = hub.api(f"{hub.prefix}/git/commits/{merge}")["parents"]
    if [p["sha"] for p in parents] != [base, expected_head]:
        raise GuardError("Merge result does not bind the current base and candidate")
    return {"repository": hub.repository, "merge_sha": merge,
            "test_profile_digest": profile_digest(config), "pr_number": number, "head_sha": expected_head, "default_branch": info["default_branch"],
            "base_sha": sha(pr["base"]["sha"]), "files": [f["filename"] for f in files]}


def profile_digest(config: dict) -> str:
    root = Path(__file__).resolve().parents[1]
    paths = [root / "scripts/test_all.py", root / ".github/workflows/verify-candidate.yml"]
    for directory in ("tests_github", "python", "typescript", "tests"):
        paths.extend(p for p in (root / directory).rglob("*") if p.is_file() and not {"__pycache__", "node_modules", "dist"}.intersection(p.parts) and p.suffix in {".py", ".ts", ".json"})
    return digest(canonical({"config": config, "files": {str(p.relative_to(root)): digest(p.read_bytes()) for p in sorted(paths)}}))


def receipt_description(value: dict) -> str:
    keys = ("repository", "pr_number", "head_sha", "base_sha", "merge_sha", "test_profile_digest")
    return "verified:" + digest(canonical({k: value[k] for k in keys}))


def report_candidate(hub, config: dict, number: int, head: str, test_result: str, run_url: str,
                     *, tested: dict | None = None) -> None:
    try:
        current = resolve_candidate(hub, config, number, head)
    except GuardError:
        hub.set_status(sha(head), "failure", run_url)
        raise
    if tested is None or receipt_description(tested) != receipt_description(current):
        hub.set_status(head, "failure", run_url)
        raise GuardError("Verification receipt missing or stale: re-test current head/base/merge/profile")
    if test_result not in ("success", "failure", "cancelled", "skipped"):
        raise GuardError("Unexpected trusted job result")
    state = "success" if test_result == "success" else "failure"
    hub.set_status(head, state, run_url, description=receipt_description(current))
