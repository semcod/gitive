"""Trusted workflow helpers. Never execute candidate code in this process."""
from __future__ import annotations
import re
from .config import path_allowed
from .util import GuardError, integer, sha


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
    return {"pr_number": number, "head_sha": expected_head, "default_branch": info["default_branch"],
            "base_sha": sha(pr["base"]["sha"]), "files": [f["filename"] for f in files]}


def report_candidate(hub, config: dict, number: int, head: str, test_result: str, run_url: str) -> None:
    # Resolve again to close the time-of-check/time-of-use window before status publication.
    resolve_candidate(hub, config, number, head)
    if test_result not in ("success", "failure", "cancelled", "skipped"):
        raise GuardError("Unexpected trusted job result")
    state = "success" if test_result == "success" else "failure"
    hub.set_status(head, state, run_url)
