"""The model. Roughly 60 lines of maths; everything else in this package is plumbing.

    w_i     = kind_weight * exp(-ln2 * (t - t_i) / half_life)      memory kernel
    s_t     = normalise( sum_i w_i e_i  over achievement facts )   what the project is
    r_t     = normalise( sum_i w_i e_i  over friction facts )      what hurts
    delta_t = normalise( (g - <g,s>s) + mu * r_t )                 what is missing
    phi(c)  = [ align, surprise*gate, cost, redundancy ]           features
    U(c)    = theta . phi(c)                                       utility
    p(c)    = softmax(U / tau)                                     the "intuition"
    theta  += lr * (y - sigma(U)) * phi(c)                         learn from git

The gate on `surprise` is the guardrail: without it the model happily proposes
work that is orthogonal to everything, i.e. off-project. Surprise only counts
once a candidate already clears `align_floor` alignment with the tension vector.
"""
from __future__ import annotations

import math
from typing import Any, Sequence

import numpy as np

from .facts import ACHIEVEMENT, FRICTION

FEATURES = ("align", "surprise", "cost", "redundancy")
THETA0 = [1.0, 0.30, -0.20, -0.60]

# friction facts decay faster: a failure from a month ago is usually already gone
KIND_WEIGHT = {
    "commit": 1.0,
    "pr_merged": 1.2,
    "issue_closed": 1.0,
    "ci_success": 0.4,
    "ci_failure": 2.5,
    "revert": 1.8,
    "marker": 0.8,
}


def _unit(v: np.ndarray) -> np.ndarray:
    n = float(np.linalg.norm(v))
    return v / n if n > 1e-12 else v


def decay_weights(ts: np.ndarray, now: float, half_life_days: float,
                  kinds: Sequence[str] | None = None) -> np.ndarray:
    dt_days = (now - ts) / 86400.0
    w = np.exp(-math.log(2.0) * np.maximum(dt_days, 0.0) / max(half_life_days, 0.1))
    if kinds is not None:
        w = w * np.array([KIND_WEIGHT.get(k, 1.0) for k in kinds], dtype=np.float64)
    return w


def centroid(embs: np.ndarray, w: np.ndarray) -> np.ndarray:
    if embs.shape[0] == 0:
        return np.zeros(embs.shape[1] if embs.ndim == 2 else 0, dtype=np.float32)
    return _unit((w[:, None] * embs).sum(axis=0))


def state_and_friction(facts: list[dict[str, Any]], embs: np.ndarray, now: float,
                       half_life_days: float) -> tuple[np.ndarray, np.ndarray]:
    kinds = [f.get("kind", "commit") for f in facts]
    ts = np.array([f.get("ts", now) for f in facts], dtype=np.float64)
    ach = np.array([k in ACHIEVEMENT for k in kinds])
    fri = np.array([k in FRICTION for k in kinds])
    dim = embs.shape[1] if embs.ndim == 2 and embs.shape[0] else 0
    s = centroid(embs[ach], decay_weights(ts[ach], now, half_life_days,
                                          [k for k, m in zip(kinds, ach) if m])) if ach.any() \
        else np.zeros(dim, np.float32)
    r = centroid(embs[fri], decay_weights(ts[fri], now, half_life_days * 0.5,
                                          [k for k, m in zip(kinds, fri) if m])) if fri.any() \
        else np.zeros(dim, np.float32)
    return s, r


def tension_with_norm(goal: np.ndarray, s: np.ndarray, r: np.ndarray,
                      mu: float = 1.0) -> tuple[np.ndarray, float]:
    """Component of the goal not yet covered by the state, plus current friction.

    Returns the unit direction *and* its raw magnitude. The direction steers task
    selection; the magnitude is the convergence signal (it is lost by normalising,
    which is why both come back together).
    """
    if goal.size == 0:
        raw = mu * r.astype(np.float32)
    else:
        gap = goal - float(goal @ s) * s if s.size else goal
        raw = (gap + mu * r).astype(np.float32)
    return _unit(raw), float(np.linalg.norm(raw))


def tension(goal: np.ndarray, s: np.ndarray, r: np.ndarray, mu: float = 1.0) -> np.ndarray:
    return tension_with_norm(goal, s, r, mu)[0]


def features(cand_emb: np.ndarray, cost: float, delta: np.ndarray, s: np.ndarray,
             done: np.ndarray, align_floor: float = 0.30) -> np.ndarray:
    align = float(cand_emb @ delta) if delta.size else 0.0
    surprise = (1.0 - float(cand_emb @ s)) if s.size else 1.0
    gate = 1.0 if align > align_floor else 0.0
    redundancy = float(np.max(done @ cand_emb)) if done.size else 0.0
    cost_n = min(max(cost, 1.0), 5.0) / 5.0
    return np.array([align, surprise * gate, cost_n, redundancy], dtype=np.float64)


def utility(phi: np.ndarray, theta: np.ndarray) -> float:
    return float(phi @ theta)


def softmax(u: np.ndarray, tau: float = 0.7) -> np.ndarray:
    if u.size == 0:
        return u
    z = (u - u.max()) / max(tau, 1e-3)
    e = np.exp(z)
    return e / e.sum()


def sigmoid(x: float) -> float:
    return 1.0 / (1.0 + math.exp(-max(-30.0, min(30.0, x))))


def update_theta(theta: np.ndarray, phi: np.ndarray, y: int, lr: float = 0.05) -> np.ndarray:
    """Online logistic regression. y=1 the task was acted on, y=0 it was ignored."""
    pred = sigmoid(float(phi @ theta))
    return theta + lr * (y - pred) * phi


def converged(delta_norm_history: list[float], threshold: float = 0.15,
              window: int = 3) -> bool:
    """Goal reached: tension small and no longer moving. Time for a new goal."""
    if len(delta_norm_history) < window:
        return False
    tail = delta_norm_history[-window:]
    return max(tail) < threshold and (max(tail) - min(tail)) < 0.02
