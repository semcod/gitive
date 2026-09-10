"""LLM access through litellm, configured for OpenRouter.

litellm routes `openrouter/<vendor>/<model>` to OpenRouter automatically as long
as OPENROUTER_API_KEY is present in the environment. We keep the wrapper thin so
switching provider is a one-line .env change (e.g. `anthropic/claude-sonnet-4-5`
or `ollama/qwen2.5-coder` for a fully local loop).
"""
from __future__ import annotations

import json
import os
import re
from typing import Any


class LLMError(RuntimeError):
    pass


def _strip_fences(text: str) -> str:
    text = text.strip()
    m = re.search(r"```(?:json)?\s*(.*?)```", text, re.S)
    if m:
        return m.group(1).strip()
    return text


def _first_json_array(text: str) -> str:
    depth, start = 0, -1
    for i, ch in enumerate(text):
        if ch == "[":
            if depth == 0:
                start = i
            depth += 1
        elif ch == "]":
            depth -= 1
            if depth == 0 and start >= 0:
                return text[start : i + 1]
    return text


def complete(prompt: str, system: str, model: str, temperature: float = 0.7,
             max_tokens: int = 2000, api_base: str | None = None) -> str:
    try:
        import litellm  # lazy import
    except ImportError as exc:  # pragma: no cover
        raise LLMError("litellm is not installed: pip install litellm") from exc

    kwargs: dict[str, Any] = {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": prompt},
        ],
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    if os.getenv("LLM_REASONING_EFFORT"):
        kwargs["reasoning_effort"] = os.environ["LLM_REASONING_EFFORT"]
    if model.startswith("openrouter/"):
        if not os.environ.get("OPENROUTER_API_KEY"):
            raise LLMError("OPENROUTER_API_KEY is not set (see .env.example)")
        if api_base:
            kwargs["api_base"] = api_base
        # OpenRouter attribution headers -- optional but good citizenship.
        kwargs["extra_headers"] = {
            "HTTP-Referer": os.environ.get("OPENROUTER_SITE_URL", "https://github.com"),
            "X-Title": os.environ.get("OPENROUTER_APP_NAME", "intuition-loop"),
        }
    resp = litellm.completion(**kwargs)
    return resp["choices"][0]["message"]["content"] or ""


def complete_json_list(prompt: str, system: str, **kw: Any) -> list[dict[str, Any]]:
    raw = complete(prompt, system, **kw)
    text = _first_json_array(_strip_fences(raw))
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise LLMError(f"model did not return valid JSON: {raw[:400]}") from exc
    if isinstance(data, dict):
        for key in ("tasks", "candidates", "items"):
            if key in data and isinstance(data[key], list):
                return data[key]
        return [data]
    if not isinstance(data, list):
        raise LLMError("expected a JSON array of task objects")
    return [d for d in data if isinstance(d, dict)]
