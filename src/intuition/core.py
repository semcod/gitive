"""Loop orchestration."""
from __future__ import annotations

import time
from pathlib import Path
from typing import Any, Callable

import numpy as np

from . import gh, model, propose
from .config import Config
from .embed import Embedder
from .facts import collect, dedupe
from .llm import complete, complete_json_list
from .store import append_jsonl, content_id, known_ids, read_json, read_jsonl, write_json


def _theta(cfg: Config) -> np.ndarray:
    w = read_json(cfg.weights_path, None)
    if not w or "theta" not in w:
        return np.array(model.THETA0, dtype=np.float64)
    return np.array(w["theta"], dtype=np.float64)


def _save_theta(cfg: Config, theta: np.ndarray, extra: dict[str, Any] | None = None) -> None:
    payload = {
        "theta": [round(float(x), 6) for x in theta],
        "features": list(model.FEATURES),
        "updated_at": time.time(),
    }
    payload.update(extra or {})
    write_json(cfg.weights_path, payload)


def _readme(cwd: str | None) -> str:
    base = Path(cwd or ".")
    for name in ("GOAL.md", "README.md", "readme.md", "docs/README.md"):
        p = base / name
        if p.exists():
            return p.read_text(encoding="utf-8", errors="replace")
    return "No README found."


def ingest(cfg: Config, cwd: str | None = None) -> list[dict[str, Any]]:
    """Pull new facts from git + Actions, append the unseen ones, return all facts."""
    fresh = collect(cfg, cwd)
    new = dedupe(fresh, known_ids(cfg.facts_path))
    if new:
        append_jsonl(cfg.facts_path, new)
        print(f"[intuition] +{len(new)} new facts")
    return list(read_jsonl(cfg.facts_path))


def ensure_goal(cfg: Config, facts: list[dict[str, Any]], cwd: str | None = None,
                force: bool = False, llm: Callable[..., str] = complete) -> str:
    goal = read_json(cfg.goal_path, None)
    if goal and not force:
        return goal["text"]
    text = llm(
        propose.build_goal_prompt(_readme(cwd), facts),
        propose.GOAL_SYSTEM,
        model=cfg.model, temperature=0.3, max_tokens=600, api_base=cfg.api_base,
    ).strip()
    write_json(cfg.goal_path, {"text": text, "created_at": time.time(),
                               "generation": (goal or {}).get("generation", 0) + 1})
    return text


def cycle(cfg: Config, cwd: str | None = None,
          gen: Callable[..., list[dict[str, Any]]] = complete_json_list,
          llm: Callable[..., str] = complete) -> dict[str, Any]:
    """One turn of the loop: observe -> orient (score) -> decide -> act (open issues)."""
    now = time.time()
    facts = ingest(cfg, cwd)
    if not facts:
        return {"status": "no-facts"}

    emb = Embedder(cfg.embed_model, cfg.dim)

    # --- state, friction, tension --------------------------------------
    fact_embs = emb([f.get("text", "") for f in facts])
    s, r = model.state_and_friction(facts, fact_embs, now, cfg.half_life_days)
    goal_text = ensure_goal(cfg, facts, cwd, llm=llm)
    g = emb([goal_text])[0]
    delta, dnorm = model.tension_with_norm(g, s, r, cfg.friction_weight)

    open_issues = gh.list_issues(cfg.label, "open", cwd=cwd)
    slots = max(0, min(cfg.per_cycle, cfg.max_open - len(open_issues)))
    if slots == 0:
        print(f"[intuition] WIP limit reached ({len(open_issues)}/{cfg.max_open}) - no new tasks")
        return {"status": "wip-limit", "open": len(open_issues), "tension": dnorm}

    n_friction = sum(1 for f in facts if f.get("kind") == "ci_failure"
                     and now - f.get("ts", 0) < 3 * 86400)
    note = (f"|tension| = {dnorm:.3f}; friction share = {float(np.linalg.norm(r)):.2f}; "
            f"{n_friction} CI failures in the last 3 days")

    cands = gen(
        propose.build_prompt(goal_text, facts, [i["title"] for i in open_issues],
                             cfg.n_candidates, note),
        propose.SYSTEM,
        model=cfg.model, temperature=cfg.temperature_llm,
        max_tokens=cfg.max_tokens, api_base=cfg.api_base,
    )
    cands = [c for c in cands if c.get("title")][: cfg.n_candidates]
    if not cands:
        return {"status": "no-candidates", "tension": dnorm}

    # --- score ----------------------------------------------------------
    done_texts = [t.get("title", "") + " " + (t.get("body") or "")[:300]
                  for t in read_jsonl(cfg.ledger_path)]
    done = emb(done_texts) if done_texts else np.zeros((0, emb.dim), np.float32)
    cand_embs = emb([f"{c['title']}\n{c.get('body', '')[:800]}" for c in cands])

    theta = _theta(cfg)
    phis = [model.features(cand_embs[i], float(c.get("cost", 3) or 3), delta, s, done,
                           cfg.align_floor) for i, c in enumerate(cands)]
    U = np.array([model.utility(p, theta) for p in phis])
    P = model.softmax(U, cfg.tau)
    order = np.argsort(-U)

    # --- act -------------------------------------------------------------
    created = []
    for idx in order[:slots]:
        c = cands[int(idx)]
        tid = content_id("task", c["title"])
        body = (c.get("body") or "").rstrip()
        body += (f"\n\n---\n*rationale:* {c.get('rationale', '')}\n"
                 f"*score:* U={U[idx]:.3f} p={P[idx]:.3f} "
                 f"(align={phis[idx][0]:.2f} surprise={phis[idx][1]:.2f} "
                 f"cost={phis[idx][2]:.2f} redundancy={phis[idx][3]:.2f})")
        url = gh.create_issue(c["title"], body, [cfg.label], tid,
                              list(phis[int(idx)]), cfg.dry_run, cwd)
        append_jsonl(cfg.ledger_path, [{
            "id": tid, "title": c["title"], "body": (c.get("body") or "")[:1200],
            "files": c.get("files", []), "cost": c.get("cost", 3),
            "phi": [round(float(x), 6) for x in phis[int(idx)]],
            "U": round(float(U[idx]), 6), "p": round(float(P[idx]), 6),
            "url": url, "proposed_at": now, "resolved_at": None, "y": None,
        }])
        created.append(c["title"])

    hist = read_json(cfg.weights_path, {}) or {}
    tail = (hist.get("tension_history") or [])[-19:] + [round(dnorm, 4)]
    _save_theta(cfg, theta, {"tension_history": tail,
                             "converged": model.converged(tail),
                             "embedder": "hashing" if emb.degraded else cfg.embed_model})
    return {"status": "ok", "created": created, "tension": dnorm,
            "converged": model.converged(tail), "facts": len(facts)}


def feedback(cfg: Config, cwd: str | None = None) -> dict[str, Any]:
    """Label past proposals from GitHub state and take one SGD step per label.

    y = 1  issue closed as completed (someone acted on the intuition)
    y = 0  closed as not planned, or still open past the horizon (ignored)
    """
    rows = list(read_jsonl(cfg.ledger_path))
    if not rows:
        return {"status": "empty-ledger"}
    resolved = {r["id"] for r in rows if r.get("resolution")}
    pending = {r["id"]: r for r in rows
               if r.get("y") is None and not r.get("resolution") and r["id"] not in resolved}
    if not pending:
        return {"status": "nothing-to-label"}

    now = time.time()
    labels: dict[str, int] = {}
    for state in ("closed", "open"):
        for issue in gh.list_issues(cfg.label, state, cwd=cwd):
            tid = gh.issue_task_id(issue)
            if not tid or tid not in pending:
                continue
            if state == "closed":
                reason = (issue.get("stateReason") or "").lower()
                labels[tid] = 0 if reason in ("not_planned", "duplicate") else 1
            elif now - pending[tid]["proposed_at"] > cfg.horizon_days * 86400:
                labels[tid] = 0

    if not labels:
        return {"status": "no-resolutions", "pending": len(pending)}

    theta = _theta(cfg)
    for tid, y in labels.items():
        phi = np.array(pending[tid]["phi"], dtype=np.float64)
        theta = model.update_theta(theta, phi, y, cfg.lr)
    _save_theta(cfg, theta, {"last_batch": len(labels)})

    # ledger is append-only: resolutions are appended, not edited in place
    append_jsonl(cfg.ledger_path, [
        {"id": tid, "resolution": True, "y": y, "resolved_at": now,
         "title": pending[tid]["title"], "phi": pending[tid]["phi"]}
        for tid, y in labels.items()
    ])
    return {"status": "ok", "labelled": len(labels),
            "theta": [round(float(x), 4) for x in theta]}
