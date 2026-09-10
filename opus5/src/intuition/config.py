"""Configuration. Every knob of the intuition model lives here.

Precedence: environment variable > .env file > default.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


def _load_dotenv(path: str = ".env") -> None:
    """Load .env without hard-depending on python-dotenv."""
    shared = Path(__file__).resolve().parents[3] / ".env"
    if path == ".env" and shared.is_file():
        path = str(shared)
    try:
        from dotenv import load_dotenv  # type: ignore

        load_dotenv(path, override=False, interpolate=False)
        return
    except Exception:
        pass
    p = Path(path)
    if not p.exists():
        return
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def _f(key: str, default: float) -> float:
    try:
        return float(os.environ.get(key, default))
    except ValueError:
        return default


def _i(key: str, default: int) -> int:
    try:
        return int(os.environ.get(key, default))
    except ValueError:
        return default


def _b(key: str, default: bool) -> bool:
    return os.environ.get(key, str(default)).strip().lower() in ("1", "true", "yes", "on")


@dataclass
class Config:
    # --- storage -------------------------------------------------------
    root: Path = field(default_factory=lambda: Path(os.environ.get("INTUITION_ROOT", ".intuition")))

    # --- LLM (litellm -> OpenRouter) -----------------------------------
    model: str = "openrouter/z-ai/glm-5.3"
    embed_model: str = ""  # empty => hashing embedder (no provider needed)
    api_base: str = "https://openrouter.ai/api/v1"
    temperature_llm: float = 0.7
    max_tokens: int = 2000

    # --- intuition model hyperparameters --------------------------------
    dim: int = 512               # embedding dim for the hashing fallback
    half_life_days: float = 14.0  # lambda of the memory kernel
    tau: float = 0.7             # softmax temperature (explore/exploit)
    friction_weight: float = 1.0  # mu: how hard CI failures pull the tension vector
    align_floor: float = 0.30    # gate: surprise only counts above this alignment
    horizon_days: int = 14       # label window for feedback
    lr: float = 0.05             # SGD learning rate for theta

    allowed_paths: tuple[str, ...] = ()

    # --- loop safety -----------------------------------------------------
    max_open: int = 5            # WIP limit: never exceed this many open issues
    per_cycle: int = 2           # issues created per cycle
    n_candidates: int = 8        # candidates the LLM proposes per cycle
    ci_lookback: int = 20        # how many CI runs to ingest
    git_lookback: int = 200      # how many commits to ingest
    dry_run: bool = False
    label: str = "intuition"

    @classmethod
    def load(cls, env_file: str = ".env") -> "Config":
        _load_dotenv(env_file)
        c = cls()
        c.root = Path(os.environ.get("INTUITION_ROOT", str(c.root)))
        c.model = os.environ.get("LLM_MODEL", os.environ.get("INTUITION_MODEL", c.model))
        c.embed_model = os.environ.get("INTUITION_EMBED_MODEL", c.embed_model)
        c.api_base = os.environ.get("OPENROUTER_API_BASE", c.api_base)
        c.temperature_llm = _f("INTUITION_LLM_TEMPERATURE", c.temperature_llm)
        c.max_tokens = _i("INTUITION_MAX_TOKENS", c.max_tokens)
        c.dim = _i("INTUITION_DIM", c.dim)
        c.half_life_days = _f("INTUITION_HALF_LIFE_DAYS", c.half_life_days)
        c.tau = _f("INTUITION_TAU", c.tau)
        c.friction_weight = _f("INTUITION_FRICTION_WEIGHT", c.friction_weight)
        c.align_floor = _f("INTUITION_ALIGN_FLOOR", c.align_floor)
        c.horizon_days = _i("INTUITION_HORIZON_DAYS", c.horizon_days)
        c.lr = _f("INTUITION_LR", c.lr)
        c.max_open = _i("INTUITION_MAX_OPEN", c.max_open)
        c.per_cycle = _i("INTUITION_PER_CYCLE", c.per_cycle)
        c.n_candidates = _i("INTUITION_N_CANDIDATES", c.n_candidates)
        c.ci_lookback = _i("INTUITION_CI_LOOKBACK", c.ci_lookback)
        c.git_lookback = _i("INTUITION_GIT_LOOKBACK", c.git_lookback)
        c.dry_run = _b("INTUITION_DRY_RUN", c.dry_run)
        c.label = os.environ.get("INTUITION_LABEL", c.label)
        c.allowed_paths = tuple(p.strip() for p in os.getenv("INTUITION_ALLOWED_PATHS", "").split(",") if p.strip())
        return c

    # convenience paths
    @property
    def facts_path(self) -> Path:
        return self.root / "facts.jsonl"

    @property
    def goal_path(self) -> Path:
        return self.root / "goal.json"

    @property
    def weights_path(self) -> Path:
        return self.root / "weights.json"

    @property
    def ledger_path(self) -> Path:
        return self.root / "ledger.jsonl"
