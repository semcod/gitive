"""Completed GitHub Actions attempts become immutable observations."""
import hashlib
import json
import os
import re
from .store import command


def redact(text):
    for key, value in os.environ.items():
        if any(part in key for part in ("TOKEN", "KEY", "SECRET", "PASSWORD")) and len(value) >= 8:
            text = text.replace(value, "[REDACTED]")
    return re.sub(r"(?i)(authorization:\s*(?:bearer|basic)\s+)\S+", r"\1[REDACTED]", text)


class GitHub:
    def __init__(self, repo, root):
        if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repo or ""):
            raise ValueError("Repo musi mieć format owner/repo")
        self.repo, self.root = repo, root

    def call(self, *args):
        return command(["gh", *args], self.root)

    def api(self, endpoint):
        return json.loads(self.call("api", f"repos/{self.repo}/{endpoint}"))


def sync_ci_facts(store, gh, limit=20):
    if not 1 <= limit <= 100:
        raise ValueError("limit musi należeć do 1..100")
    store.clean()
    runs = gh.api(f"actions/runs?status=completed&per_page={limit}")["workflow_runs"]
    existing = {f["id"] for f in store.facts()}
    repo_hash = hashlib.sha256(gh.repo.encode()).hexdigest()[:10]
    items = []
    for run in runs:
        if run["status"] != "completed":
            continue
        rid, attempt = run["id"], run.get("run_attempt", 1)
        fid = f"ci_{repo_hash}_{rid}_{attempt}"
        if fid in existing:
            continue
        status = run.get("conclusion") or "unknown"
        logs = ""
        if status != "success":
            try:
                logs = gh.call("run", "view", str(rid), "--repo", gh.repo, "--attempt", str(attempt), "--log-failed")
            except RuntimeError:
                logs = "Logi niedostępne; zachowano metadane uruchomienia."
        excerpt = redact("\n".join(logs.splitlines()[-100:]))[-12000:]
        item = dict(id=fid, content=f"CI {gh.repo} run {rid}, próba {attempt}, {status}\n{excerpt}",
                    tags=["ci", status, "closed" if status == "success" else "open", "observation"],
                    references=[], created=run["updated_at"],
                    metadata=dict(run_id=rid, attempt=attempt, status=status, workflow=run["name"],
                                  branch=run["head_branch"], head_sha=run["head_sha"], url=run["html_url"]))
        if status != "success":
            item["tags"].append("error" if status == "failure" else "warning")
        # A later attempt of the same run closes the previous attempt's frontier.
        earlier = [f for f in store.facts() if f.get("metadata", {}).get("run_id") == rid
                   and f["id"].startswith(f"ci_{repo_hash}_")]
        if earlier:
            item["supersedes"] = max(earlier, key=lambda f: f["metadata"]["attempt"])["id"]
        items.append(item)
        existing.add(fid)
    if items:
        files, _ = store.fact_files(items, f"github:{gh.repo}")
        store.transaction(files, f"sync(ci): +{len(items)} observations")
    return len(items)
