"""Repair one ticket inside a provisioned DigitalTwin project runtime.

The LLM is only an orchestration aid. Source changes are applied to the private
DigitalTwin checkout and the project's acceptance command always runs through
``docker exec``. The PC checkout and the controller checkout are never edited.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
import sys
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if __package__:
    from .digitaltwin import DigitalTwin
    from .operations import Operations
else:
    sys.path.insert(0, str(ROOT / "src"))
    from gitive.digitaltwin import DigitalTwin
    from gitive.operations import Operations

from dotenv import load_dotenv
from benchmark.adapters import ADAPTERS
from benchmark.common import git, validate_edits


def _runtime_root(workspace: dict) -> Path:
    root = Path(workspace["root"]).resolve()
    source = Path(workspace["source"])
    checkout = (root / "rootfs" / source.relative_to("/")).resolve()
    if not checkout.is_relative_to(root) or not (checkout / ".git").is_dir():
        raise ValueError("DigitalTwin nie zawiera prywatnego checkoutu Git")
    return checkout


def _test(twin: DigitalTwin, project: str, argv: list[str]) -> dict:
    result = twin.execute(project, argv, test=True)
    output = ""
    try:
        output = Path(result["log"]).read_text(encoding="utf-8", errors="replace")[-14000:]
    except OSError:
        pass
    return {"passed": result["status"] == "passed", "exit_code": result["exit_code"], "output": output,
            "runtime": True, "log": result["log"]}


def _files(root: Path, allow: str) -> dict[str, str]:
    names = git(root, "ls-files", "-z").split("\0")
    prefix = allow.rstrip("/") + "/"
    extensions = (".py", ".md", ".txt", ".json", ".yaml", ".yml", ".toml", ".sh", ".js", ".ts", ".html", ".css")
    selected = [name for name in names if name.startswith(prefix) and not (root / name).is_symlink()
                and name.endswith(extensions)]
    if any(name.endswith(".py") for name in selected) and not prefix.startswith("docs/"):
        python_files = [name for name in selected if name.endswith(".py")]
        selected = python_files if len(python_files) <= 15 else selected[:15]
    selected = selected[:25]
    code = {}
    for name in selected:
        try:
            code[name] = (root / name).read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
    if not 1 <= len(code) <= 25 or sum(len(value) for value in code.values()) > 300000:
        raise ValueError("Zakres naprawy musi obejmować 1–25 plików i najwyżej 300k znaków")
    return code


def _propose(root: Path, project: dict, solution: str, evidence: str, code: dict[str, str], destination: Path):
    """Run the selected native strategy against a disposable private clone."""
    with tempfile.TemporaryDirectory(prefix="gitive-runtime-repair-") as temp:
        work = Path(temp) / "repo"
        git(root, "clone", "--quiet", "--no-hardlinks", str(root), str(work))
        git(work, "config", "user.name", "Gitive")
        git(work, "config", "user.email", "gitive@localhost")
        load_dotenv(ROOT / ".env", override=False, interpolate=False)
        os.environ["LLM_MAX_CALLS"] = "4"
        import litellm
        from benchmark.transcripts import Recorder

        recorder = Recorder(destination / "transcripts", destination)
        calls = []
        original = litellm.completion

        def capture(**kwargs):
            if len(calls) >= 4:
                raise RuntimeError("Development LLM call budget exhausted")
            call_id = f"runtime-{solution}-{len(calls) + 1:03d}"
            calls.append({"id": call_id,
                          "request_receipt": recorder.request(call_id, kwargs, {"solution": solution, "phase": "runtime-repair"})})
            try:
                response = original(**kwargs)
                calls[-1]["response_receipt"] = recorder.response(call_id, response)
                return response
            except Exception as exc:
                calls[-1]["error"] = type(exc).__name__
                calls[-1]["error_receipt"] = recorder.write(call_id, "error", {"error_type": type(exc).__name__})
                raise

        litellm.completion = capture
        try:
            adapter = ADAPTERS[solution](work, project["goal"], 7)
            if solution == "opus5":
                adapter.native_test_argv = project["test_argv"]
            if solution == "gpt6":
                adapter.config["allowed_paths"] = list(code)
            task, edits = adapter.propose_patch(evidence, code, 1)
            edits = validate_edits(edits, code)
            if not edits:
                raise ValueError("Strategia nie zwróciła zmian źródłowych")
            return task, edits, calls
        finally:
            litellm.completion = original
            (destination / "calls.json").write_text(json.dumps(calls, ensure_ascii=False, indent=2), encoding="utf-8")


def run(project: dict, solution: str, destination: Path) -> dict:
    destination.mkdir(parents=True, exist_ok=True, mode=0o700)
    twin = DigitalTwin()
    workspace = twin.status(project["name"])
    if workspace.get("container_status") != "running":
        raise ValueError("Kontener DigitalTwin nie działa; uruchom twin prepare/start przed ticketem")
    root = _runtime_root(workspace)
    if git(root, "status", "--porcelain"):
        raise ValueError("Prywatny checkout DigitalTwin wymaga czystego stanu")
    ops = Operations(destination, project["name"], project.get("planfile_ticket"), solution,
                     project.get("gitive_run"), ROOT)
    with ops.observe(), ops.stage("tests", "gitive.runtime_develop.tests"):
        before = _test(twin, project["name"], project["test_argv"])
    start = git(root, "rev-parse", "HEAD")
    if before["passed"]:
        return {"status": "already_green", "solution": solution, "base": start, "head": start,
                "tests": before, "runtime": True}
    code = _files(root, project.get("allow", "src"))
    evidence = json.dumps({"goal": project["goal"], "failing_tests": before["output"], "allowed_files": list(code)}, ensure_ascii=False)
    with ops.stage("repair", solution + ".propose_patch"):
        task, edits, calls = _propose(root, project, solution, evidence, code, destination)
    backup = {}
    committed = False
    try:
        with ops.stage("coding", "gitive.runtime_develop.apply"):
            for name, content in edits.items():
                path = root / name
                backup[name] = path.read_text(encoding="utf-8") if path.exists() else None
                path.write_text(content, encoding="utf-8")
        with ops.stage("tests", "gitive.runtime_develop.tests"):
            after = _test(twin, project["name"], project["test_argv"])
        changed = set(git(root, "diff", "HEAD", "--name-only").splitlines())
        if git(root, "rev-parse", "HEAD") != start or changed - set(edits):
            raise ValueError("Testy zmieniły pliki poza zatwierdzonym zakresem")
        if not after["passed"]:
            return {"status": "rejected", "solution": solution, "base": start, "tests": after,
                    "runtime": True, "calls": calls}
        git(root, "add", "--", *edits)
        git(root, "commit", "-m", f"gitive({solution}): validated runtime repair")
        committed = True
        return {"status": "repaired", "solution": solution, "base": start,
                "head": git(root, "rev-parse", "HEAD"), "tests": after, "runtime": True,
                "changed": sorted(edits), "calls": calls, "task": task}
    finally:
        # A rejected or interrupted candidate never remains in the private runtime.
        if not committed:
            for name, content in backup.items():
                path = root / name
                if content is None:
                    path.unlink(missing_ok=True)
                else:
                    path.write_text(content, encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("project_json")
    parser.add_argument("solution", choices=tuple(ADAPTERS))
    parser.add_argument("destination")
    args = parser.parse_args()
    destination = Path(args.destination)
    try:
        result = run(json.loads(Path(args.project_json).read_text(encoding="utf-8")), args.solution, destination)
    except Exception as exc:
        result = {"status": "error", "error": type(exc).__name__, "message": str(exc)[:600], "runtime": True}
    destination.mkdir(parents=True, exist_ok=True, mode=0o700)
    (destination / "result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print("GITIVE_RESULT " + result["status"], flush=True)
    if result["status"] == "error":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
