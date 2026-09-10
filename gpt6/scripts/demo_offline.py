"""Reproducible SYNTHETIC demonstration: actual local Git, fake gh and fake LLM."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from intuition_github.config import load_config
from intuition_github.controller import Controller
from intuition_github.memory import Memory
from intuition_github.util import Redactor
from tests_github.fakes import LocalGitHub, ScriptedLLM


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, help="Optional directory for synthetic issue, PR and state examples")
    args = parser.parse_args()
    config = load_config(Path(__file__).resolve().parents[1] / ".intuition/config.json")
    hub = LocalGitHub()
    model = ScriptedLLM()
    stages = []
    try:
        def cycle(run_id=None):
            memory = Memory(hub, config)
            controller = Controller(hub, memory, config, lambda: model, Redactor([]))
            result = controller.cycle(run_id)
            task = next(iter(memory.state["tasks"].values()))
            stages.append({"stage": len(stages) + 1, "state": task["status"], "llm_calls": result["llm_calls"],
                           "candidate_attempts": len(task["attempts"]), "memory_commit": memory.head})
            return task, memory
        task, _ = cycle()
        hub.add_run(20, path="verify-candidate.yml", event="workflow_dispatch", conclusion="failure",
                    pr=task["pr_number"], candidate=task["attempts"][-1]["head_sha"],
                    logs="SYNTHETIC DEMO: assertion failed; no real Actions job ran.")
        task, _ = cycle(20)
        hub.add_run(21, path="verify-candidate.yml", event="workflow_dispatch", conclusion="success",
                    pr=task["pr_number"], candidate=task["attempts"][-1]["head_sha"],
                    logs="SYNTHETIC DEMO: tests passed; no real Actions job ran.")
        task, memory = cycle(21)
        summary = {"synthetic": True, "external_api_calls": 0, "git_objects_real": True,
                   "stages": stages, "issues_created": len(hub.issue_items), "prs_created": len(hub.pull_items),
                   "profile_counts": memory.state["profile_counts"]}
        if args.out:
            args.out.mkdir(parents=True, exist_ok=True)
            for filename, value in (("demo-summary.json", summary), ("memory-state.json", memory.state)):
                (args.out / filename).write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")
            (args.out / "issue.md").write_text("# SYNTHETIC OFFLINE EXAMPLE — not a real GitHub issue\n\n" + hub.issue(task["issue_number"])["body"])
            (args.out / "pull-request.md").write_text("# SYNTHETIC OFFLINE EXAMPLE — not a real PR\n\n" + hub.pull(task["pr_number"])["body"])
        print(json.dumps(summary, ensure_ascii=False, indent=2))
    finally:
        hub.close()


if __name__ == "__main__":
    main()
