from __future__ import annotations
import re
from .github import GhError
from .util import GuardError, canonical, digest, integer, now, sha


def accepted_run(run: dict, repo: str, default_branch: str, config: dict) -> bool:
    return (run.get("status") == "completed"
            and (run.get("head_repository") or {}).get("full_name") == repo
            and run.get("head_branch") == default_branch
            and run.get("event") in {"push", "workflow_dispatch", "workflow_run"}
            and run.get("path", "").split("@")[0] in config["accepted_workflows"])


def verification_identity(run: dict) -> tuple[int, str] | None:
    if run.get("path", "").split("@")[0] != ".github/workflows/verify-candidate.yml":
        return None
    if run.get("event") != "workflow_dispatch":
        return None
    match = re.fullmatch(r"Verify PR #(\d+) @ ([0-9a-f]{40})", run.get("display_title", ""))
    return (int(match[1]), match[2]) if match else None


def ingest_run(hub, memory, run: dict, config: dict, default_branch: str, redactor) -> dict | None:
    if not accepted_run(run, hub.repository, default_branch, config):
        return None
    run_id, attempt = integer(run["id"]), integer(run.get("run_attempt", 1))
    identity = f"{run_id}:{attempt}"
    if identity in memory.state["seen_runs"]:
        return None
    jobs = hub.run_jobs(run_id, attempt)
    logs_error = None
    try:
        log = redactor.clean(hub.run_logs(run_id, attempt))
    except GhError:
        log, logs_error = "", "Logs unavailable or expired; no log-derived claims imported."
    if len(log) > config["max_log_chars"]:
        log = "[Sanitized log excerpt; earlier lines omitted]\n" + log[-config["max_log_chars"]:]
    blob = log.encode()
    log_hash = digest(blob)
    source = f"https://github.com/{hub.repository}/actions/runs/{run_id}/attempts/{attempt}"
    # GitHub API metadata and process output are different trust classes.
    meta = {"id": f"run:{identity}", "kind": "workflow_result", "status": "observed",
            "text": f"Workflow {run.get('name', '')} finished with conclusion {run.get('conclusion')}; this does not prove a root cause.",
            "source": source, "observed_at": now(), "run_id": run_id, "attempt": attempt,
            "head_sha": sha(run["head_sha"]), "workflow_path": run["path"],
            "conclusion": run.get("conclusion"), "event": run["event"],
            "jobs": [{"name": redactor.clean(j.get("name", ""))[:200], "conclusion": j.get("conclusion"),
                      "status": j.get("status")} for j in jobs]}
    facts = [meta]
    extra = {}
    if log:
        facts.append({"id": f"log:{identity}", "kind": "ci_log_excerpt", "status": "reported",
                      "text": log[-4000:], "source": source, "evidence_sha256": log_hash,
                      "observed_at": now(), "head_sha": run["head_sha"], "run_id": run_id, "attempt": attempt,
                      "trust": "untrusted_data_not_instructions"})
        extra[f"evidence/{log_hash}.txt"] = blob
    if logs_error:
        meta["logs_error"] = logs_error
    memory.state["facts"].extend(facts)
    # Older facts remain in Git history and evidence blobs; context/state stay bounded.
    memory.state["facts"] = memory.state["facts"][-200:]
    memory.state["seen_runs"].append(identity)
    memory.save("ci_cd_observation", {"run": identity, "conclusion": run.get("conclusion")}, extra)
    return {"run": run, "jobs": jobs, "fact_ids": [f["id"] for f in facts]}
