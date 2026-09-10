"""Small CAS-based Git event store. Only use a dedicated, trusted bare repository."""
from __future__ import annotations
import json
import os
import re
import subprocess
import tempfile
from pathlib import Path
from typing import Any

REF = "refs/heads/memory"

def git(repo: Path, *args: str, data: bytes | None = None, env: dict | None = None) -> bytes:
    environment = dict(os.environ)
    # Do not let inherited Git routing variables redirect this dedicated store.
    for k in list(environment):
        if k.startswith("GIT_"):
            del environment[k]
    environment.update({"GIT_AUTHOR_NAME":"Intuition planner", "GIT_AUTHOR_EMAIL":"planner@example.invalid",
                        "GIT_COMMITTER_NAME":"Intuition planner", "GIT_COMMITTER_EMAIL":"planner@example.invalid",
                        "GIT_CONFIG_NOSYSTEM":"1", "GIT_CONFIG_GLOBAL":os.devnull})
    if env:
        environment.update(env)
    completed = subprocess.run(["git", "-C", str(repo), "-c", "commit.gpgSign=false", *args],
                               input=data, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                               check=False, timeout=20, env=environment, shell=False)
    if completed.returncode:
        raise RuntimeError(completed.stderr.decode(errors="replace").strip())
    return completed.stdout


def read(repo: Path) -> tuple[str, dict]:
    commit = git(repo, "rev-parse", "--verify", REF).decode().strip()
    state = json.loads(git(repo, "show", commit + ":state.json"))
    return commit, state


def commit(repo: Path, base: str | None, state: dict, record: dict,
           extra: dict[str, bytes] | None = None) -> str:
    if base is not None and not re.fullmatch(r"[0-9a-f]{40}|[0-9a-f]{64}", base):
        raise ValueError("Invalid base commit")
    files = {"state.json": (json.dumps(state, ensure_ascii=False, sort_keys=True, indent=2)+"\n").encode(),
             "last-event.json": (json.dumps(record, ensure_ascii=False, sort_keys=True, indent=2)+"\n").encode()}
    files.update(extra or {})
    with tempfile.TemporaryDirectory(prefix="intuition-index-") as tmp:
        env = {"GIT_INDEX_FILE": str(Path(tmp) / "index")}
        git(repo, "read-tree", base if base else "--empty", env=env)
        for path, content in files.items():
            if path not in ("state.json", "last-event.json") and not re.fullmatch(r"evidence/[0-9a-f]{64}\.bin", path):
                raise ValueError("Unapproved Git path")
            blob = git(repo, "hash-object", "-w", "--stdin", data=content).decode().strip()
            git(repo, "update-index", "--add", "--cacheinfo", "100644", blob, path, env=env)
        tree = git(repo, "write-tree", env=env).decode().strip()
        args = ["commit-tree", tree] + (["-p", base] if base else [])
        new = git(repo, *args, data=b"Record planner event\n").decode().strip()
        # Compare-and-swap: a concurrent/stale writer must fail, never overwrite.
        git(repo, "update-ref", REF, new, base if base else "0"*len(new))
        return new


def initialize(repo: Path, state: dict) -> str:
    if repo.exists():
        raise ValueError("Init requires a new path; existing repositories are not overwritten")
    repo.mkdir(parents=True)
    git(repo, "init", "--bare", "--quiet")
    return commit(repo, None, state, {"kind":"init"})
