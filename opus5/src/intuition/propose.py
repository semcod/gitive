"""Candidate generation: the System-2 half of the loop.

The LLM is deliberately *not* asked to prioritise. It proposes; the scoring
function ranks. Keeping generation and selection apart is what makes the
learned weights meaningful -- if the model also picked, theta would have nothing
to learn from.
"""
from __future__ import annotations

from typing import Any

SYSTEM = """You are a senior engineer proposing concrete refactoring and maintenance work
for a software repository. You are given recent facts from git history, CI results and
in-code markers, plus the project's stated goal.

Return ONLY a JSON array. No prose, no markdown fences. Each element:
{
  "title": "imperative, <=72 chars",
  "body": "markdown: context, what to change, acceptance criteria as a checklist",
  "cost": 1-5,          // 1 = under an hour, 5 = multi-day
  "files": ["likely/paths.py"],
  "rationale": "one sentence tying this to a specific fact above"
}

Rules:
- Every task must be traceable to at least one fact you were given. Do not invent problems.
- A red pipeline outranks everything: if CI is failing, at least one task must address it.
- Tasks must be independently mergeable and small enough to review in one sitting.
- No duplicates of the OPEN TASKS list.
- No vague tasks ("improve code quality", "add more tests"). Name the module and the change.
"""


def digest(facts: list[dict[str, Any]], limit: int = 40, chars: int = 700) -> str:
    """Most recent friction first, then recent achievements."""
    from .facts import FRICTION

    fr = sorted([f for f in facts if f.get("kind") in FRICTION],
                key=lambda f: -f.get("ts", 0))
    ac = sorted([f for f in facts if f.get("kind") not in FRICTION],
                key=lambda f: -f.get("ts", 0))
    picked = fr[: limit // 2] + ac[: limit - len(fr[: limit // 2])]
    lines = []
    for f in picked:
        text = (f.get("text") or "").strip().replace("\r", "")
        if len(text) > chars:
            text = text[:chars] + " ..."
        lines.append(f"- [{f.get('kind')}] ({f.get('ref', '')}) {text}")
    return "\n".join(lines)


def build_prompt(goal_text: str, facts: list[dict[str, Any]], open_titles: list[str],
                 n: int, tension_note: str = "") -> str:
    open_block = "\n".join(f"- {t}" for t in open_titles) or "(none)"
    return f"""## PROJECT GOAL
{goal_text.strip()[:4000]}

## CURRENT TENSION
{tension_note or "(not computed)"}

## OPEN TASKS (do not duplicate)
{open_block}

## RECENT FACTS
{digest(facts)}

Propose exactly {n} candidate tasks as a JSON array."""


GOAL_SYSTEM = """You restate a software project's current objective in 4-8 sentences,
concrete and technical, based on its README and recent activity. Mention subsystems by
name. Output plain prose only, no headings, no lists."""


def build_goal_prompt(readme: str, facts: list[dict[str, Any]]) -> str:
    return f"""## README
{readme[:6000]}

## RECENT ACTIVITY
{digest(facts, limit=20, chars=300)}

Restate the project's current objective."""
