from __future__ import annotations
import json
from pathlib import Path, PurePosixPath
from fnmatch import fnmatchcase
from .util import GuardError, integer
from .core_model import number

# The agent cannot refactor its own privileged control plane, policies, tests or dependencies.
PROTECTED_ROOTS = {".github", ".git", ".intuition", "intuition_github", "scripts", "tests", "tests_github"}
PROTECTED_NAMES = {"pyproject.toml", "package.json", "package-lock.json", "uv.lock", "poetry.lock",
                   "requirements.txt", "requirements-dev.txt", "Dockerfile", "Makefile", "conftest.py",
                   "sitecustomize.py", "usercustomize.py", "CODEOWNERS"}


def path_allowed(path: str, config: dict) -> bool:
    if not isinstance(path, str) or len(path) > 240 or "\\" in path or not path.isascii():
        return False
    p = PurePosixPath(path)
    if p.is_absolute() or str(p) != path or any(x in (".", "..", "") for x in path.split("/")):
        return False
    if any(x.startswith(".") for x in p.parts) or p.parts[0] in PROTECTED_ROOTS:
        return False
    if p.name in PROTECTED_NAMES or p.name.startswith(("test_", "test-", "requirements")):
        return False
    if p.suffix not in {".py", ".ts", ".md"}:
        return False
    return any(fnmatchcase(path, pattern) for pattern in config["allowed_paths"])


def load_config(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if value.get("schema_version") != 2:
        raise GuardError("Unsupported configuration schema")
    for key in ("max_calls_per_day", "max_calls_per_cycle", "max_new_issues_per_cycle",
                "max_open_issues", "max_open_prs", "max_attempts_per_issue", "max_failures_before_pause",
                "max_runs_per_cycle", "max_context_facts", "max_log_chars", "max_input_chars",
                "max_output_tokens", "max_files_per_patch", "max_patch_changed_lines", "max_file_bytes"):
        integer(value[key], 1, 1_000_000)
    if value["max_new_issues_per_cycle"] > 3 or value["max_open_prs"] > 5:
        raise GuardError("Hard limit: at most 3 new issues/cycle and 5 open PRs")
    if not isinstance(value["allowed_paths"], list) or not value["allowed_paths"]:
        raise GuardError("An explicit allowed_paths list is required")
    for profile in value["profiles"].values():
        for key in ("alpha", "beta"):
            number(profile[key], key, 0.01, 1e6)
        for key in ("benefit", "cost", "risk"):
            number(profile[key], key, 0, 100)
    return value
