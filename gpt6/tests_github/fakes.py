"""GitHub API double backed by actual local Git objects. No network or credentials."""
from __future__ import annotations
import base64
import copy
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
from urllib.parse import unquote
from intuition_github.github import GitHub, GhError
from intuition_github.util import Redactor


class LocalGitHub(GitHub):
    def __init__(self):
        super().__init__("example/project", Redactor({}))
        self.tmp = tempfile.TemporaryDirectory(prefix="intuition-git-test-")
        self.gitdir = Path(self.tmp.name) / "repo.git"
        subprocess.run(["git", "init", "--bare", "--quiet", str(self.gitdir)], check=True)
        self.operations = []
        self.issue_items, self.pull_items = {}, {}
        self.run_items, self.job_items, self.log_items = {}, {}, {}
        self.status_items = {}
        self.protection = None
        self.changed_files_override = None
        self.fail_next_issue_response = False
        self.fail_ci_dispatch = False
        self.fail_verification_dispatch = False
        self.next_number = 1
        root = self.create_commit(None, {"demo_app/metrics.py": b"value = 1\n"}, "initial fixture")
        self.advance_ref("main", root, None)
        self.add_run(10)

    def close(self):
        self.tmp.cleanup()

    def git(self, *args, data=None, index=None, check=True):
        env = {**os.environ, "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": os.devnull,
               "GIT_AUTHOR_NAME": "Offline Test", "GIT_AUTHOR_EMAIL": "test@example.invalid",
               "GIT_COMMITTER_NAME": "Offline Test", "GIT_COMMITTER_EMAIL": "test@example.invalid"}
        if index is not None:
            env["GIT_INDEX_FILE"] = str(index)
        return subprocess.run(["git", "--git-dir", str(self.gitdir), *args], input=data,
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env, check=check).stdout

    def api(self, path, method="GET", payload=None, missing_ok=False):
        self.operations.append((method, path, copy.deepcopy(payload)))
        route = unquote(path.removeprefix(self.prefix).split("?")[0])
        if route == "" and method == "GET":
            return {"full_name": self.repository, "default_branch": "main"}
        if route.startswith("/git/ref/heads/") and method == "GET":
            ref = "refs/heads/" + route.removeprefix("/git/ref/heads/")
            result = self.git("rev-parse", "--verify", ref, check=False).decode().strip()
            if not re.fullmatch(r"[0-9a-f]{40}", result):
                if missing_ok:
                    return None
                raise GhError("not found", 404)
            return {"object": {"sha": result}}
        if route == "/git/blobs" and method == "POST":
            raw = base64.b64decode(payload["content"])
            return {"sha": self.git("hash-object", "-w", "--stdin", data=raw).decode().strip()}
        if route.startswith("/git/blobs/") and method == "GET":
            raw = self.git("cat-file", "blob", route.rsplit("/", 1)[1])
            return {"content": base64.b64encode(raw).decode(), "encoding": "base64", "size": len(raw)}
        if route == "/git/trees" and method == "POST":
            with tempfile.TemporaryDirectory(dir=self.tmp.name) as folder:
                index = Path(folder) / "index"
                if payload.get("base_tree"):
                    self.git("read-tree", payload["base_tree"], index=index)
                else:
                    self.git("read-tree", "--empty", index=index)
                entries = "".join(f"{x['mode']} {x['sha']}\t{x['path']}\n" for x in payload["tree"])
                self.git("update-index", "--index-info", data=entries.encode(), index=index)
                return {"sha": self.git("write-tree", index=index).decode().strip()}
        if route.startswith("/git/trees/") and method == "GET":
            tree = route.rsplit("/", 1)[1]
            records = self.git("ls-tree", "-r", "-z", tree).split(b"\0")
            items = []
            for record in records:
                if not record:
                    continue
                meta, filename = record.split(b"\t", 1)
                mode, kind, oid = meta.decode().split()
                size = int(self.git("cat-file", "-s", oid).decode())
                items.append({"path": filename.decode(), "mode": mode, "type": kind, "sha": oid, "size": size})
            return {"tree": items, "truncated": False}
        if route == "/git/commits" and method == "POST":
            args = ["commit-tree", payload["tree"]]
            for parent in payload["parents"]:
                args += ["-p", parent]
            return {"sha": self.git(*args, data=payload["message"].encode()).decode().strip()}
        if route.startswith("/git/commits/") and method == "GET":
            oid = route.rsplit("/", 1)[1]
            parts = self.git("show", "-s", "--format=%T %P", oid).decode().strip().split()
            return {"sha": oid, "tree": {"sha": parts[0]}, "parents": [{"sha": p} for p in parts[1:]]}
        if route == "/git/refs" and method == "POST":
            self.git("update-ref", payload["ref"], payload["sha"], "0" * 40)
            return {"object": {"sha": payload["sha"]}}
        if route.startswith("/git/refs/heads/") and method == "PATCH":
            ref = "refs/heads/" + route.removeprefix("/git/refs/heads/")
            old = self.git("rev-parse", ref).decode().strip()
            ancestors = self.git("rev-list", payload["sha"]).decode().splitlines()
            if not payload.get("force") and old not in ancestors:
                raise GhError("not fast-forward", 422)
            self.git("update-ref", ref, payload["sha"], old)
            return {"object": {"sha": payload["sha"]}}
        if route.endswith("/protection"):
            if self.protection is None:
                raise GhError("forbidden", 403)
            return copy.deepcopy(self.protection)
        if route.startswith("/statuses/") and method == "POST":
            oid = route.rsplit("/", 1)[1]
            self.status_items.setdefault(oid, []).insert(0, copy.deepcopy(payload))
            return payload
        if route.endswith("/status") and "/commits/" in route:
            oid = route.split("/")[-2]
            return {"statuses": copy.deepcopy(self.status_items.get(oid, []))}
        raise AssertionError(f"Unimplemented offline API: {method} {route}")

    def command(self, args, data=None, **kwargs):
        self.operations.append(("gh", args, data))
        return ""

    def ensure_labels(self):
        self.operations.append(("labels",))

    def issues(self):
        return copy.deepcopy(list(self.issue_items.values()))

    def create_issue(self, title, body):
        number = self.next_number
        self.next_number += 1
        value = {"number": number, "state": "open", "title": title, "body": body,
                 "html_url": f"https://github.com/{self.repository}/issues/{number}"}
        self.issue_items[number] = value
        self.operations.append(("create_issue", number))
        if self.fail_next_issue_response:
            self.fail_next_issue_response = False
            raise GhError("Simulated lost response after successful remote write")
        return copy.deepcopy(value)

    def issue(self, number):
        return copy.deepcopy(self.issue_items[number])

    def comment(self, number, body):
        self.operations.append(("comment", number, body))

    def needs_human(self, number):
        self.operations.append(("needs_human", number))

    def create_pull(self, branch, base, title, body):
        number = self.next_number
        self.next_number += 1
        value = {"number": number, "state": "open", "merged": False, "body": body,
                 "html_url": f"https://github.com/{self.repository}/pull/{number}",
                 "head": {"ref": branch, "sha": self.ref(branch), "repo": {"full_name": self.repository}},
                 "base": {"ref": base, "sha": self.ref(base)}}
        self.pull_items[number] = value
        self.operations.append(("create_pull", number))
        return copy.deepcopy(value)

    def pull(self, number):
        value = self.pull_items[number]
        value["head"]["sha"] = self.ref(value["head"]["ref"])
        return copy.deepcopy(value)

    def pulls(self, branch=None, state="open"):
        return [self.pull(n) for n, p in self.pull_items.items()
                if (state == "all" or p["state"] == state) and (branch is None or p["head"]["ref"] == branch)]

    def pages(self, path, key=None, max_pages=10):
        match = re.search(r"/pulls/(\d+)/files", path)
        if match:
            if self.changed_files_override is not None:
                return copy.deepcopy(self.changed_files_override)
            pr = self.pull(int(match[1]))
            names = self.git("diff", "--numstat", pr["base"]["sha"], pr["head"]["sha"]).decode()
            return [{"filename": line.split("\t")[2], "status": "modified",
                     "changes": int(line.split("\t")[0]) + int(line.split("\t")[1])}
                    for line in names.splitlines()]
        raise AssertionError(path)

    def add_run(self, run_id, *, path="ci.yml", conclusion="success", event="push", attempt=1,
                pr=None, candidate=None, logs="Synthetic fixture: tests completed.\n", test_result=None):
        value = {"id": run_id, "run_attempt": attempt, "name": {"ci.yml": "CI", "cd.yml": "CD",
                    "verify-candidate.yml": "Verify candidate"}.get(path, path),
                 "path": ".github/workflows/" + path, "head_branch": "main", "head_sha": self.ref("main"),
                 "head_repository": {"full_name": self.repository}, "event": event, "status": "completed",
                 "conclusion": conclusion, "display_title": f"Verify PR #{pr} @ {candidate}" if candidate else "CI"}
        self.run_items[run_id] = value
        self.job_items[(run_id, attempt)] = [{"name": "Test candidate" if candidate else "Regression tests",
                                            "status": "completed", "conclusion": test_result or conclusion,
                                            "steps": [{"name": "Run fixed tests with a clean child environment",
                                                       "conclusion": test_result or conclusion}] if candidate else []}]
        self.log_items[(run_id, attempt)] = logs
        return value

    def run(self, number):
        return copy.deepcopy(self.run_items[number])

    def recent_runs(self, count=30):
        return [self.run(n) for n in sorted(self.run_items, reverse=True)[:count]]

    def run_jobs(self, number, attempt):
        return copy.deepcopy(self.job_items[(number, attempt)])

    def run_logs(self, number, attempt):
        result = self.log_items[(number, attempt)]
        if isinstance(result, Exception):
            raise result
        return result

    def dispatch_ci(self, branch):
        if self.fail_ci_dispatch:
            raise GhError("Synthetic dispatch failure")
        self.operations.append(("dispatch_ci", branch))

    def dispatch_verification(self, number, head, default):
        if self.fail_verification_dispatch:
            raise GhError("Synthetic dispatch failure")
        self.operations.append(("dispatch_verification", number, head, default))


class ScriptedLLM:
    def __init__(self, *, empty=False, fail=False):
        self.calls = []
        self.empty = empty
        self.fail = fail

    def complete(self, purpose, payload):
        self.calls.append((purpose, copy.deepcopy(payload)))
        if self.fail:
            from intuition_github.util import GuardError
            raise GuardError("LLM request failed (SyntheticTimeout)")
        if purpose == "propose_tasks":
            tasks = [] if self.empty else [{"title": "Clarify the fixture value", "profile": "refactor",
                "fact_ids": [payload["untrusted_facts"][-1]["id"]], "target_files": ["demo_app/metrics.py"],
                "acceptance": ["Existing tests still pass; no observable behavior change."],
                "rationale": "The referenced snapshot can benefit from a minimal explanatory comment."}]
            return {"base_sha": payload["base_sha"], "tasks": tasks}, 100
        files = payload["untrusted_files"]
        first = files[0]
        return {"base_sha": payload["base_sha"], "summary": "Add a minimal explanatory comment.", "edits": [{
            "path": first["path"], "old_sha256": first["sha256"],
            "content": first["content"] + "# synthetic verified candidate\n"}]}, 120
