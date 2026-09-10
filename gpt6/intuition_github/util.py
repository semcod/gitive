from __future__ import annotations
import hashlib
import json
import os
import re
from datetime import datetime, timezone
from typing import Any

class GuardError(ValueError):
    """Rejected input, unsafe action, stale state, or exhausted budget."""


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False).encode()


def digest(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha(value: Any) -> str:
    if not isinstance(value, str) or not re.fullmatch(r"[0-9a-f]{40}", value):
        raise GuardError("Expected a GitHub SHA-1 commit/blob identifier")
    return value


def integer(value: Any, minimum: int = 1, maximum: int = 10**18) -> int:
    if isinstance(value, bool) or not str(value).isascii() or not str(value).isdigit():
        raise GuardError("Expected an unsigned integer")
    result = int(value)
    if not minimum <= result <= maximum:
        raise GuardError("Integer outside permitted bounds")
    return result


def text(value: Any, limit: int = 8000) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > limit or "\x00" in value:
        raise GuardError("Invalid or oversized text")
    return value


def fields(value: Any, keys: set[str], path: str = "$") -> dict:
    if not isinstance(value, dict):
        raise GuardError(f"schema_type at {path}: expected object, got {type(value).__name__}")
    if set(value) != keys:
        # Report expected names and counts, not attacker-controlled key contents.
        missing = sorted(keys - set(value))
        raise GuardError(f"schema_fields at {path}: missing={missing}, unexpected_count={len(set(value) - keys)}")
    return value


def strict_json(value: str) -> Any:
    def pairs(entries):
        result = {}
        for key, item in entries:
            if key in result:
                raise GuardError("Duplicate JSON key")
            result[key] = item
        return result
    def constant(_):
        raise GuardError("Non-finite JSON constant")
    try:
        return json.loads(value, object_pairs_hook=pairs, parse_constant=constant)
    except (json.JSONDecodeError, RecursionError) as exc:
        raise GuardError("LLM response is not a single valid JSON object") from exc


class Redactor:
    """Best effort, NOT a guarantee that arbitrary logs contain no sensitive data."""
    def __init__(self, secrets: list[str] | None = None):
        supplied = secrets if secrets is not None else [
            v for k, v in os.environ.items()
            if any(w in k.upper() for w in ("TOKEN", "SECRET", "PASSWORD", "API_KEY"))
        ]
        self.secrets = sorted({v for v in supplied if v and len(v) >= 6}, key=len, reverse=True)

    def clean(self, value: str) -> str:
        value = re.sub(r"\x1b\[[0-?]*[ -/]*[@-~]", "", value)
        value = re.sub(r"-----BEGIN [^-]*PRIVATE KEY-----.*?-----END [^-]*PRIVATE KEY-----",
                       "[REDACTED PRIVATE KEY]", value, flags=re.S)
        for secret in self.secrets:
            value = value.replace(secret, "[REDACTED]")
        value = re.sub(r"\b(?:sk-or-v1-|sk-proj-|sk-|gh[pousr]_|github_pat_)[A-Za-z0-9_-]{8,}",
                       "[REDACTED TOKEN]", value)
        value = re.sub(r"(?im)((?:authorization|api[_-]?key|token|password|secret)\s*[=:]\s*)([^\r\n]+)",
                       r"\1[REDACTED]", value)
        value = re.sub(r"(?i)\bBearer\s+[A-Za-z0-9._~+/-]+=*", "Bearer [REDACTED]", value)
        value = re.sub(r"(https?://)[^/@\s]+:[^/@\s]+@", r"\1[REDACTED]@", value)
        return "".join(c for c in value if c in "\n\t" or ord(c) >= 32)

    def public_text(self, value: str) -> str:
        # Logs/model output must not mint workflow commands, task markers or mass mentions.
        value = self.clean(value)
        value = value.replace("<!--", "&lt;!--").replace("-->", "--&gt;")
        return re.sub(r"(?<![\w])@(?=[A-Za-z])", "＠", value)
