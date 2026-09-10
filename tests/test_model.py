from __future__ import annotations

import json
import subprocess
import time

import numpy as np
import pytest

from intuition import model
from intuition.config import Config
from intuition.core import cycle
from intuition.embed import HashingEmbedder
from intuition.facts import error_signature, git_facts
from intuition.store import read_jsonl

NOW = time.time()
DAY = 86400.0


# --------------------------------------------------------------------- maths

def test_decay_halves_at_half_life():
    ts = np.array([NOW, NOW - 14 * DAY, NOW - 28 * DAY])
    w = model.decay_weights(ts, NOW, 14.0)
    assert w[0] == pytest.approx(1.0, abs=1e-6)
    assert w[1] == pytest.approx(0.5, abs=1e-6)
    assert w[2] == pytest.approx(0.25, abs=1e-6)


def test_ci_failure_outweighs_commit():
    assert model.KIND_WEIGHT["ci_failure"] > model.KIND_WEIGHT["commit"]
    ts = np.array([NOW, NOW])
    w = model.decay_weights(ts, NOW, 14.0, ["commit", "ci_failure"])
    assert w[1] > w[0]


def test_tension_is_orthogonal_to_state_without_friction():
    e = HashingEmbedder(64)
    g = e(["ship the async scheduler with retries"])[0]
    s = e(["scheduler retries implemented and merged"])[0]
    r = np.zeros(64, dtype=np.float32)
    d, n = model.tension_with_norm(g, s, r, mu=1.0)
    assert abs(float(d @ s)) < 1e-5      # nothing left pointing at what is done
    assert n < 1.0                       # partially achieved -> smaller gap


def test_friction_bends_tension_towards_the_failure():
    e = HashingEmbedder(128)
    g = e(["improve documentation coverage"])[0]
    s = np.zeros(128, dtype=np.float32)
    r = e(["CI FAILING pytest AssertionError in scheduler timeout"])[0]
    d_no = model.tension(g, s, np.zeros(128, np.float32), mu=1.0)
    d_yes = model.tension(g, s, r, mu=2.0)
    assert float(d_yes @ r) > float(d_no @ r)


def test_surprise_gate_blocks_off_project_candidates():
    delta = np.zeros(8, dtype=np.float32); delta[0] = 1.0
    s = np.zeros(8, dtype=np.float32); s[1] = 1.0
    off = np.zeros(8, dtype=np.float32); off[7] = 1.0    # orthogonal to everything
    on = np.zeros(8, dtype=np.float32); on[0] = 1.0
    empty = np.zeros((0, 8), dtype=np.float32)
    assert model.features(off, 3, delta, s, empty)[1] == 0.0   # surprise gated off
    assert model.features(on, 3, delta, s, empty)[1] > 0.0


def test_redundancy_penalises_repeats():
    e = HashingEmbedder(256)
    done = e(["refactor the retry backoff in scheduler.py"])
    dup = e(["refactor the retry backoff in scheduler.py"])[0]
    new = e(["add OpenTelemetry spans to the ingest path"])[0]
    delta = np.ones(256, dtype=np.float32) / np.sqrt(256)
    s = np.zeros(256, dtype=np.float32)
    assert model.features(dup, 3, delta, s, done)[3] > model.features(new, 3, delta, s, done)[3]


def test_sgd_moves_utility_in_the_right_direction():
    theta = np.array(model.THETA0, dtype=np.float64)
    phi = np.array([0.6, 0.4, 0.4, 0.1])
    u0 = model.utility(phi, theta)
    for _ in range(20):
        theta = model.update_theta(theta, phi, 1, lr=0.1)
    assert model.utility(phi, theta) > u0
    theta2 = np.array(model.THETA0, dtype=np.float64)
    for _ in range(20):
        theta2 = model.update_theta(theta2, phi, 0, lr=0.1)
    assert model.utility(phi, theta2) < u0


def test_softmax_temperature_controls_exploration():
    u = np.array([1.0, 0.9, 0.2])
    cold, hot = model.softmax(u, 0.1), model.softmax(u, 5.0)
    assert cold.max() > hot.max()
    assert np.isclose(cold.sum(), 1.0) and np.isclose(hot.sum(), 1.0)


def test_convergence_needs_low_and_flat_tension():
    assert not model.converged([0.9, 0.5, 0.3])
    assert not model.converged([0.14, 0.05, 0.13])   # low but still moving
    assert model.converged([0.11, 0.10, 0.10])


# ----------------------------------------------------------------- ingestion

def test_error_signature_keeps_signal_drops_noise():
    log = "\n".join([
        "test\t2026-01-01T10:00:00.1Z Requirement already satisfied: numpy",
        "test\t2026-01-01T10:00:01.1Z ##[group]Run pytest",
        "test\t2026-01-01T10:00:02.1Z E   AssertionError: expected 3 got 4",
        "test\t2026-01-01T10:00:03.1Z   at foo (bar.js:1)",
        "test\t2026-01-01T10:00:04.1Z Process completed with exit code 1",
    ])
    sig = error_signature(log)
    assert "AssertionError" in sig
    assert "Requirement already" not in sig
    assert "##[group]" not in sig
    assert len(sig.splitlines()) == 2


def test_error_signature_deduplicates_by_normalised_form():
    log = "\n".join(["ERROR: timeout at 0x1f2 after 1234 ms",
                     "ERROR: timeout at 0xaa9 after 5678 ms"])
    assert len(error_signature(log).splitlines()) == 1


# ------------------------------------------------------------- offline cycle

def _repo(tmp_path):
    r = tmp_path / "repo"
    r.mkdir()
    (r / "README.md").write_text("# demo\nA scheduler library with retries.\n")
    (r / "app.py").write_text("def run():\n    # FIXME: no retry budget\n    return 1\n")
    env = {"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@e",
           "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@e", "PATH": "/usr/bin:/bin"}
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=r, check=True, env=env)
    subprocess.run(["git", "add", "-A"], cwd=r, check=True, env=env)
    subprocess.run(["git", "commit", "-qm", "feat: scheduler skeleton"], cwd=r, check=True, env=env)
    return r


def test_git_facts_read_history(tmp_path):
    r = _repo(tmp_path)
    facts = git_facts(10, cwd=str(r))
    assert facts and facts[0]["kind"] == "commit"
    assert "scheduler skeleton" in facts[0]["text"]
    assert "app.py" in facts[0]["paths"]


def test_full_cycle_dry_run_without_network(tmp_path, monkeypatch):
    """The whole loop, no gh, no LLM, no embedding provider."""
    r = _repo(tmp_path)
    monkeypatch.chdir(r)
    cfg = Config()
    cfg.dry_run = True
    cfg.per_cycle = 2
    cfg.embed_model = ""            # hashing embedder

    def fake_gen(prompt, system, **kw):
        assert "PROJECT GOAL" in prompt and "RECENT FACTS" in prompt
        return [
            {"title": "Add retry budget to scheduler", "body": "- [ ] cap retries",
             "cost": 2, "files": ["app.py"], "rationale": "FIXME marker in app.py"},
            {"title": "Rewrite the frontend in Elm", "body": "unrelated",
             "cost": 5, "files": [], "rationale": "none"},
        ]

    def fake_llm(prompt, system, **kw):
        return "Ship a reliable scheduler with a bounded retry budget."

    res = cycle(cfg, cwd=str(r), gen=fake_gen, llm=fake_llm)
    assert res["status"] == "ok"
    assert res["facts"] >= 1
    assert len(res["created"]) == 2

    ledger = list(read_jsonl(cfg.ledger_path))
    assert len(ledger) == 2
    assert all(len(row["phi"]) == 4 for row in ledger)
    # the cheap, on-goal task must outrank the expensive off-goal one
    by_title = {row["title"]: row for row in ledger}
    assert by_title["Add retry budget to scheduler"]["U"] > by_title["Rewrite the frontend in Elm"]["U"]

    weights = json.loads(cfg.weights_path.read_text())
    assert weights["embedder"] == "hashing"
    assert len(weights["tension_history"]) == 1


def test_cycle_respects_wip_limit(tmp_path, monkeypatch):
    r = _repo(tmp_path)
    monkeypatch.chdir(r)
    cfg = Config()
    cfg.dry_run = True
    cfg.max_open = 3
    monkeypatch.setattr("intuition.core.gh.list_issues",
                        lambda *a, **k: [{"title": f"t{i}"} for i in range(3)])
    res = cycle(cfg, cwd=str(r), gen=lambda *a, **k: [{"title": "x"}], llm=lambda *a, **k: "goal")
    assert res["status"] == "wip-limit"
