from __future__ import annotations
import argparse
import json
import os
import sys
from pathlib import Path
from .config import load_config
from .controller import Controller
from .evidence import accepted_run
from .github import GitHub, GhError
from .llm import load_env
from .memory import Memory
from .util import GuardError, Redactor, integer
from .verification import resolve_candidate, report_candidate


def output(value: dict) -> None:
    rendered = json.dumps(value, ensure_ascii=False, indent=2)
    print(rendered)
    summary = os.getenv("GITHUB_STEP_SUMMARY")
    if summary:
        # Only controller-generated fields; do not render raw logs or model output as workflow commands.
        with open(summary, "a", encoding="utf-8") as stream:
            stream.write("## Intuition\n\n```json\n" + rendered + "\n```\n")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="GitHub-native Intuition controller (Python 3.11+)")
    parser.add_argument("--repo", default=os.getenv("GITHUB_REPOSITORY"))
    parser.add_argument("--config", default=".intuition/config.json")
    parser.add_argument("--env-file", default=".env")
    sub = parser.add_subparsers(dest="command", required=True)
    cycle = sub.add_parser("cycle", help="Run a bounded cycle; default is read-only, without LLM calls")
    cycle.add_argument("--apply", action="store_true")
    cycle.add_argument("--run-id", type=int)
    cycle.add_argument("--reset-circuit", action="store_true")
    sub.add_parser("status")
    sub.add_parser("doctor", help="Check configuration and GitHub connection without writes")
    resolve = sub.add_parser("resolve-candidate")
    resolve.add_argument("--pr", required=True, type=int)
    resolve.add_argument("--head", required=True)
    report = sub.add_parser("report-candidate")
    report.add_argument("--pr", required=True, type=int)
    report.add_argument("--head", required=True)
    report.add_argument("--test-result", required=True)
    args = parser.parse_args(argv)
    try:
        load_env(Path(args.env_file))
        config = load_config(Path(args.config))
        repository = args.repo or os.getenv("GITHUB_REPOSITORY")
        if not repository:
            raise GuardError("Set --repo OWNER/REPO or GITHUB_REPOSITORY")
        redactor = Redactor()
        hub = GitHub(repository, redactor)
        if args.command == "doctor":
            info = hub.repository_info()
            output({"repository": info["full_name"], "default_branch": info["default_branch"],
                    "openrouter_key_present": bool(os.getenv("OPENROUTER_API_KEY")),
                    "enabled": os.getenv("INTUITION_ENABLED", "false"),
                    "model": os.getenv("LLM_MODEL", os.getenv("OPENROUTER_MODEL", "openrouter/z-ai/glm-5.3")),
                    "writes_performed": False, "llm_request_performed": False})
            return 0
        if args.command == "resolve-candidate":
            value = resolve_candidate(hub, config, args.pr, args.head)
            if os.getenv("GITHUB_OUTPUT"):
                with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as stream:
                    for key in ("head_sha", "base_sha"):
                        stream.write(f"{key}={value[key]}\n")
            output(value)
            return 0
        if args.command == "report-candidate":
            run_id = integer(os.environ["GITHUB_RUN_ID"])
            url = f"https://github.com/{repository}/actions/runs/{run_id}"
            report_candidate(hub, config, args.pr, args.head, args.test_result, url)
            output({"status_published_for": args.head, "result": args.test_result})
            return 0
        memory = Memory(hub, config)
        if args.command == "status":
            output({"memory_commit": memory.head, "budgets": memory.state["budgets"],
                    "paused_reason": memory.state["paused_reason"],
                    "task_counts": {s: sum(t["status"] == s for t in memory.state["tasks"].values())
                                    for s in sorted({t["status"] for t in memory.state["tasks"].values()})}})
            return 0
        if not args.apply:
            default = hub.repository_info()["default_branch"]
            runs = [hub.run(args.run_id)] if args.run_id else hub.recent_runs(100)
            output({"status": "dry_run", "memory_commit": memory.head, "writes_performed": False,
                    "llm_request_performed": False,
                    "eligible_run_ids": [r["id"] for r in runs if accepted_run(r, repository, default, config)],
                    "limits": {k: v for k, v in config.items() if k.startswith("max_")}})
            return 0
        if os.getenv("INTUITION_ENABLED", "false").lower() != "true":
            raise GuardError("Writes require INTUITION_ENABLED=true and cycle --apply")
        controller = Controller(hub, memory, config, redactor=redactor)
        try:
            result = controller.cycle(args.run_id, args.reset_circuit)
        except GuardError as exc:
            if "budget exhausted" in str(exc).lower():
                result = controller.summary("budget_exhausted_wait_for_next_day_or_cycle")
            else:
                raise
        output(result)
        return 0
    except (GuardError, GhError, KeyError, ValueError, ImportError, OSError) as exc:
        # Start with fixed text to prevent an error fragment beginning a workflow command.
        print("Intuition stopped: " + Redactor().clean(str(exc)).replace("\n", " | ")[:1500], file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
