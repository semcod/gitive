"""Deterministic signed hashing and the four-feature critic."""
from __future__ import annotations
import hashlib
import math
import random
import re

ARCH = ("derive", "verify", "connect", "decompose", "ask")
FEATURES = ("nov", "coh", "grn", "val")
D, KNN, BETA = 256, 5, 8.0


def embed(text: str) -> list[float]:
    tokens = re.findall(r"[0-9a-ząćęłńóśźż]{3,}", text.lower())
    grams = tokens + [a + "~" + b for a, b in zip(tokens, tokens[1:])]
    vector = [0.0] * D
    for gram in grams:
        h = hashlib.blake2b(gram.encode(), digest_size=8).digest()
        vector[int.from_bytes(h[:4], "big") % D] += -1 if h[4] & 1 else 1
    norm = math.sqrt(sum(x * x for x in vector)) or 1.0
    return [x / norm for x in vector]


def cos(a: list[float], b: list[float]) -> float:
    return max(-1.0, min(1.0, sum(x * y for x, y in zip(a, b, strict=True))))


def default_state(tau=0.35, m=5, eta=0.0) -> dict:
    return dict(version=1, embedding="blake2b-8-256-v1", step=0, tau=tau, m=m, eta=eta,
                alpha={a: 1.0 for a in ARCH}, beta={a: 1.0 for a in ARCH},
                w={k: 1.0 for k in FEATURES})


def validate_state(s: dict) -> dict:
    if not isinstance(s, dict) or s.get("version") != 1 or s.get("embedding") != "blake2b-8-256-v1":
        raise ValueError("Nieobsługiwany format stanu lub embedding")
    def number(x):
        return type(x) in (int, float) and math.isfinite(x)
    if type(s.get("step")) is not int or s["step"] < 0:
        raise ValueError("Nieprawidłowy step")
    if type(s.get("m")) is not int or not 1 <= s["m"] <= 50:
        raise ValueError("m musi należeć do 1..50")
    for key in ("tau", "eta"):
        if not number(s.get(key)) or s[key] < 0:
            raise ValueError(f"Nieprawidłowe {key}")
    for key, names in (("alpha", ARCH), ("beta", ARCH), ("w", FEATURES)):
        if not isinstance(s.get(key), dict) or set(s[key]) != set(names):
            raise ValueError(f"Nieprawidłowe {key}")
        if any(not number(v) or v < 0 or (key != "w" and v == 0) for v in s[key].values()):
            raise ValueError(f"Nieprawidłowe wartości {key}")
    return s


def score(candidate, facts, vectors, state, rng, theta=None):
    vector = embed(candidate["prompt"] + " " + candidate["rationale"])
    sims = sorted((cos(vector, fv) for fv in vectors), reverse=True)
    nearest = sims[:KNN] or [0.0]
    peak = sims[0] if sims else 0.0
    coh = peak + math.log(sum(math.exp(BETA * (s - peak)) for s in sims) / len(sims)) / BETA if sims else 0.0
    refs = set(candidate["references"])
    ids = {f["id"] for f in facts}
    a = candidate["archetype"]
    val = theta[a] if theta is not None else rng.betavariate(state["alpha"][a], state["beta"][a])
    features = dict(nov=1 - sum(nearest) / len(nearest), coh=coh,
                    grn=len(refs & ids) / max(1, len(refs)), val=val)
    return {**candidate, "feats": features, "U": sum(state["w"][k] * v for k, v in features.items())}


def probabilities(scored, tau):
    if not scored or not math.isfinite(tau) or tau < 0:
        raise ValueError("Wybór wymaga kandydatów i tau >= 0")
    peak = max(c["U"] for c in scored)
    if not math.isfinite(peak) or any(not math.isfinite(c["U"]) for c in scored):
        raise ValueError("Nieskończona użyteczność")
    weights = [float(c["U"] == peak) if tau == 0 else math.exp((c["U"] - peak) / tau) for c in scored]
    total = sum(weights)
    return [w / total for w in weights]


def select(scored, tau, rng):
    x = rng.random()
    for item, p in zip(scored, probabilities(scored, tau)):
        if x < p:
            return item
        x -= p
    return scored[-1]


def update(state, task, reward):
    a = task["archetype"]
    state["alpha"][a] += reward
    state["beta"][a] += int(reward == 0)
    if state["eta"]:
        error = task["U"] - reward
        for k in FEATURES:
            exponent = max(-50.0, min(50.0, -2 * state["eta"] * error * task["feats"][k]))
            state["w"][k] = min(1e6, state["w"][k] * math.exp(exponent))
    state["step"] += 1
