"""intuition — CLI.

    intuition init          scaffold .intuition/, .env, label
    intuition ingest        pull facts from git + GitHub Actions
    intuition cycle         one loop turn: propose, score, open issues
    intuition feedback      label past proposals from issue state, update theta
    intuition status        current tension, weights, open work
    intuition explain       why the last cycle chose what it chose
"""
from __future__ import annotations

import argparse
import json
import sys
import time

import numpy as np

from . import gh, model
from .config import Config
from .core import cycle, feedback, ingest
from .store import read_json, read_jsonl, write_json

ENV_TEMPLATE = """# --- OpenRouter (via litellm) ---------------------------------
OPENROUTER_API_KEY=sk-or-v1-...
OPENROUTER_API_BASE=https://openrouter.ai/api/v1
OPENROUTER_APP_NAME=intuition-loop

LLM_MODEL=openrouter/z-ai/glm-5.3
LLM_REASONING_EFFORT=low
# leave empty to use the offline hashing embedder
INTUITION_EMBED_MODEL=

# --- model hyperparameters ------------------------------------
INTUITION_HALF_LIFE_DAYS=14
INTUITION_TAU=0.7
INTUITION_FRICTION_WEIGHT=1.0
INTUITION_ALIGN_FLOOR=0.30
INTUITION_LR=0.05

# --- loop safety ----------------------------------------------
INTUITION_MAX_OPEN=5
INTUITION_PER_CYCLE=2
INTUITION_DRY_RUN=false
"""


def _print(obj) -> None:
    print(json.dumps(obj, indent=2, ensure_ascii=False, default=str))


def cmd_init(cfg: Config, args) -> int:
    cfg.root.mkdir(parents=True, exist_ok=True)
    (cfg.root / ".gitignore").write_text("*.log\n", encoding="utf-8")
    if not cfg.weights_path.exists():
        write_json(cfg.weights_path, {"theta": model.THETA0,
                                      "features": list(model.FEATURES),
                                      "updated_at": time.time()})
    from pathlib import Path
    if not Path(".env.example").exists():
        Path(".env.example").write_text(ENV_TEMPLATE, encoding="utf-8")
    if gh.available():
        gh.ensure_label(cfg.label)
    print(f"initialised {cfg.root}/ — copy .env.example to .env and add your key")
    return 0


def cmd_ingest(cfg: Config, args) -> int:
    facts = ingest(cfg)
    kinds: dict[str, int] = {}
    for f in facts:
        kinds[f.get("kind", "?")] = kinds.get(f.get("kind", "?"), 0) + 1
    _print({"total": len(facts), "by_kind": kinds})
    return 0


def cmd_cycle(cfg: Config, args) -> int:
    if args.dry_run:
        cfg.dry_run = True
    res = cycle(cfg)
    _print(res)
    return 0 if res.get("status") in ("ok", "wip-limit") else 1


def cmd_repair(cfg: Config, args) -> int:
    from .repair import repair
    tasks = [row for row in read_jsonl(cfg.ledger_path)
             if row.get("id") == args.task_id and not row.get("resolution")]
    if not tasks:
        raise ValueError("Task not found in local ledger")
    result = repair(cfg, args.repo_root, tasks[-1], json.loads(args.test))
    _print(result)
    return 0 if result["passed"] else 1


def cmd_feedback(cfg: Config, args) -> int:
    _print(feedback(cfg))
    return 0


def cmd_status(cfg: Config, args) -> int:
    w = read_json(cfg.weights_path, {}) or {}
    ledger = list(read_jsonl(cfg.ledger_path))
    proposals = [r for r in ledger if not r.get("resolution")]
    res = [r for r in ledger if r.get("resolution")]
    acted = sum(1 for r in res if r.get("y") == 1)
    _print({
        "facts": sum(1 for _ in read_jsonl(cfg.facts_path)),
        "goal_generation": (read_json(cfg.goal_path, {}) or {}).get("generation"),
        "theta": dict(zip(model.FEATURES, w.get("theta", model.THETA0))),
        "tension_history": w.get("tension_history", [])[-10:],
        "converged": w.get("converged", False),
        "embedder": w.get("embedder"),
        "proposed": len(proposals),
        "resolved": len(res),
        "hit_rate": round(acted / len(res), 3) if res else None,
        "open_issues": len(gh.list_issues(cfg.label)) if gh.available() else "gh-unavailable",
    })
    return 0


def cmd_explain(cfg: Config, args) -> int:
    rows = [r for r in read_jsonl(cfg.ledger_path) if not r.get("resolution")][-args.n:]
    theta = np.array((read_json(cfg.weights_path, {}) or {}).get("theta", model.THETA0))
    for r in rows:
        phi = np.array(r.get("phi", [0, 0, 0, 0]), dtype=float)
        contrib = phi * theta
        print(f"\n{r['title']}   U={r.get('U'):.3f}  p={r.get('p'):.3f}")
        for name, f_, c in zip(model.FEATURES, phi, contrib):
            print(f"   {name:<11} phi={f_:+.3f}  theta*phi={c:+.3f}")
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="intuition", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--env", default=".env")
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("init").set_defaults(fn=cmd_init)
    sub.add_parser("ingest").set_defaults(fn=cmd_ingest)
    c = sub.add_parser("cycle")
    c.add_argument("--dry-run", action="store_true")
    c.set_defaults(fn=cmd_cycle)
    r = sub.add_parser("repair", help="Repair an existing ledger task locally")
    r.add_argument("--repo-root", default=".")
    r.add_argument("--task-id", required=True)
    r.add_argument("--test", required=True, help="Trusted test argv as JSON")
    r.set_defaults(fn=cmd_repair)
    sub.add_parser("feedback").set_defaults(fn=cmd_feedback)
    sub.add_parser("status").set_defaults(fn=cmd_status)
    e = sub.add_parser("explain")
    e.add_argument("-n", type=int, default=5)
    e.set_defaults(fn=cmd_explain)

    args = p.parse_args(argv)
    cfg = Config.load(args.env)
    return args.fn(cfg, args)


if __name__ == "__main__":
    sys.exit(main())
