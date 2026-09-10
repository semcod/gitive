"""All network operations use the official gh CLI. No shell interpolation."""
from __future__ import annotations
import base64
import json
import os
import re
import subprocess
import tempfile
from pathlib import Path
from urllib.parse import quote
from .util import GuardError, Redactor, canonical, integer, sha


class GhError(RuntimeError):
    def __init__(self, message: str, status: int | None = None):
        super().__init__(message)
        self.status = status


class GitHub:
    def __init__(self, repository: str, redactor: Redactor | None = None):
        if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repository):
            raise GuardError("Use OWNER/REPOSITORY, not a URL or shell expression")
        self.repository = repository
        self.prefix = f"repos/{repository}"
        self.redactor = redactor or Redactor()

    def command(self, args: list[str], data: bytes | None = None,
                limit: int = 8_000_000, tail: bool = False) -> str:
        env = dict(os.environ)
        env.update({"GH_PROMPT_DISABLED": "1", "GH_PAGER": "cat", "NO_COLOR": "1", "GH_HOST": "github.com"})
        with tempfile.TemporaryFile() as out, tempfile.TemporaryFile() as err:
            try:
                result = subprocess.run(["gh", *args], input=data, stdout=out, stderr=err,
                                        env=env, timeout=180, check=False, shell=False)
            except FileNotFoundError as exc:
                raise GhError("Install GitHub CLI (gh) and authenticate first") from exc
            except subprocess.TimeoutExpired as exc:
                raise GhError("GitHub CLI timed out; no automatic retry of a write") from exc
            err.seek(0)
            error = self.redactor.clean(err.read(8000).decode(errors="replace"))
            if result.returncode:
                code = re.search(r"HTTP\s+(\d{3})", error)
                raise GhError(error or "GitHub CLI failed", int(code[1]) if code else None)
            size = out.tell()
            if size > limit and not tail:
                raise GhError("GitHub response exceeds the configured size limit")
            out.seek(max(0, size-limit) if tail else 0)
            output = out.read(limit).decode(errors="replace")
            return ("[Earlier output omitted]\n" if size > limit else "") + output

    def api(self, path: str, method: str = "GET", payload: dict | None = None,
            missing_ok: bool = False):
        args = ["api", "--hostname", "github.com", "--method", method,
                "-H", "Accept: application/vnd.github+json", "-H", "X-GitHub-Api-Version: 2022-11-28", path]
        if payload is not None:
            args += ["--input", "-"]
        try:
            result = self.command(args, canonical(payload) if payload is not None else None)
        except GhError as exc:
            if missing_ok and exc.status == 404:
                return None
            raise
        return json.loads(result) if result.strip() else None

    def pages(self, path: str, key: str | None = None, max_pages: int = 10) -> list:
        result = []
        for page in range(1, max_pages + 1):
            sep = "&" if "?" in path else "?"
            response = self.api(f"{path}{sep}per_page=100&page={page}")
            items = response[key] if key else response
            result.extend(items)
            if len(items) < 100:
                return result
        raise GhError("Pagination limit reached; refusing an incomplete inventory")

    def repository_info(self) -> dict:
        return self.api(self.prefix)

    def ref(self, branch: str) -> str | None:
        value = self.api(f"{self.prefix}/git/ref/heads/{quote(branch, safe='/')}", missing_ok=True)
        return sha(value["object"]["sha"]) if value else None

    def commit(self, commit_sha: str) -> dict:
        return self.api(f"{self.prefix}/git/commits/{sha(commit_sha)}")

    def tree(self, commit_sha: str, recursive: bool = True) -> dict:
        tree_sha = self.commit(commit_sha)["tree"]["sha"]
        value = self.api(f"{self.prefix}/git/trees/{sha(tree_sha)}" + ("?recursive=1" if recursive else ""))
        if value.get("truncated"):
            raise GhError("Truncated Git tree; narrow the repository before using this reference agent")
        return {item["path"]: item for item in value["tree"]}

    def blob(self, blob_sha: str, max_bytes: int = 1_000_000) -> bytes:
        value = self.api(f"{self.prefix}/git/blobs/{sha(blob_sha)}")
        if value.get("encoding") != "base64" or value.get("size", 0) > max_bytes:
            raise GuardError("Unsupported or oversized Git blob")
        result = base64.b64decode(value["content"])
        if len(result) > max_bytes:
            raise GuardError("Oversized decoded Git blob")
        return result

    def files(self, commit_sha: str, paths: list[str], max_bytes: int = 64000) -> dict[str, bytes]:
        tree = self.tree(commit_sha)
        output = {}
        for path in paths:
            item = tree.get(path)
            if not item or item["type"] != "blob" or item["mode"] != "100644":
                raise GuardError("Only existing ordinary non-executable files can be edited")
            output[path] = self.blob(item["sha"], max_bytes)
        return output

    def create_commit(self, parent: str | None, files: dict[str, bytes], message: str) -> str:
        entries = []
        for path, data in sorted(files.items()):
            value = self.api(f"{self.prefix}/git/blobs", "POST", {
                "content": base64.b64encode(data).decode(), "encoding": "base64"})
            entries.append({"path": path, "mode": "100644", "type": "blob", "sha": sha(value["sha"])})
        payload = {"tree": entries}
        if parent:
            payload["base_tree"] = self.commit(parent)["tree"]["sha"]
        tree = self.api(f"{self.prefix}/git/trees", "POST", payload)
        result = self.api(f"{self.prefix}/git/commits", "POST", {
            "message": message, "tree": tree["sha"], "parents": [sha(parent)] if parent else []})
        return sha(result["sha"])

    def advance_ref(self, branch: str, new: str, expected: str | None) -> None:
        current = self.ref(branch)
        if current == new:  # recovery after a successful write followed by a client crash
            return
        if current != expected:
            raise GuardError("Concurrent/stale branch update rejected")
        if current is None:
            self.api(f"{self.prefix}/git/refs", "POST", {"ref": f"refs/heads/{branch}", "sha": sha(new)})
        else:
            # Two children of the same expected parent cannot both fast-forward the branch.
            self.api(f"{self.prefix}/git/refs/heads/{quote(branch, safe='/')}", "PATCH",
                     {"sha": sha(new), "force": False})

    def recent_runs(self, count: int = 30) -> list[dict]:
        count = integer(count, 1, 100)
        return self.api(f"{self.prefix}/actions/runs?per_page={count}")["workflow_runs"]

    def run(self, run_id: int) -> dict:
        return self.api(f"{self.prefix}/actions/runs/{integer(run_id)}")

    def run_jobs(self, run_id: int, attempt: int) -> list[dict]:
        return self.pages(f"{self.prefix}/actions/runs/{integer(run_id)}/attempts/{integer(attempt)}/jobs", "jobs")

    def run_logs(self, run_id: int, attempt: int) -> str:
        return self.command(["run", "view", str(integer(run_id)), "--repo", self.repository,
                             "--attempt", str(integer(attempt)), "--log"], limit=2_000_000, tail=True)

    def ensure_labels(self) -> None:
        for name, color, description in [
            ("intuition:managed", "7057ff", "Managed evidence-backed task"),
            ("intuition:needs-human", "b60205", "Automation paused; maintainer review needed")]:
            self.command(["label", "create", name, "--repo", self.repository, "--color", color,
                          "--description", description, "--force"])

    def issues(self) -> list[dict]:
        return self.pages(f"{self.prefix}/issues?state=all&labels=intuition%3Amanaged")

    def create_issue(self, title: str, body: str) -> dict:
        url = self.command(["issue", "create", "--repo", self.repository, "--title", title,
                            "--body-file", "-", "--label", "intuition:managed"], body.encode()).strip()
        match = re.fullmatch(r"https://github\.com/" + re.escape(self.repository) + r"/issues/(\d+)", url)
        if not match:
            raise GhError("Issue created but URL could not be parsed; next run will reconcile by marker")
        return {"number": int(match[1]), "html_url": url, "state": "open", "body": body}

    def issue(self, number: int) -> dict:
        return self.api(f"{self.prefix}/issues/{integer(number)}")

    def comment(self, number: int, body: str) -> None:
        self.command(["issue", "comment", str(integer(number)), "--repo", self.repository,
                      "--body-file", "-"], body.encode())

    def needs_human(self, number: int) -> None:
        self.command(["issue", "edit", str(integer(number)), "--repo", self.repository,
                      "--add-label", "intuition:needs-human"])

    def pull(self, number: int) -> dict:
        return self.api(f"{self.prefix}/pulls/{integer(number)}")

    def pulls(self, branch: str | None = None, state: str = "open") -> list[dict]:
        query = f"{self.prefix}/pulls?state={state}"
        if branch:
            query += "&head=" + quote(self.repository.split('/')[0] + ':' + branch, safe='')
        return self.pages(query)

    def create_pull(self, branch: str, base: str, title: str, body: str) -> dict:
        url = self.command(["pr", "create", "--repo", self.repository, "--head", branch,
                            "--base", base, "--title", title, "--body-file", "-"], body.encode()).strip()
        match = re.fullmatch(r"https://github\.com/" + re.escape(self.repository) + r"/pull/(\d+)", url)
        if not match:
            raise GhError("PR created but URL could not be parsed; next run will reconcile by branch")
        return self.pull(int(match[1]))

    def dispatch_verification(self, number: int, head: str, default_branch: str) -> None:
        self.command(["workflow", "run", "verify-candidate.yml", "--repo", self.repository,
                      "--ref", default_branch, "--raw-field", f"pr_number={integer(number)}",
                      "--raw-field", f"head_sha={sha(head)}"])

    def dispatch_ci(self, default_branch: str) -> None:
        self.command(["workflow", "run", "ci.yml", "--repo", self.repository, "--ref", default_branch])

    def set_status(self, head: str, state: str, run_url: str, *, description: str | None = None) -> None:
        if state not in ("success", "failure", "pending", "error"):
            raise GuardError("Invalid commit status")
        self.api(f"{self.prefix}/statuses/{sha(head)}", "POST", {
            "state": state, "context": "Intuition / verified", "target_url": run_url,
            "description": description or "Candidate verification has no bound receipt"})
