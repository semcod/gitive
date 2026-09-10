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
import time
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
    decoder = json.JSONDecoder()
    start = text.find("[")
    if start < 0:
        return text
    try:
        _, end = decoder.raw_decode(text, start)
    except json.JSONDecodeError:
        return text
    return text[start:end]


def complete(prompt: str, system: str, model: str, temperature: float = 0.7,
             max_tokens: int = 2000, api_base: str | None = None) -> str:
    try:
        import litellm  # lazy import
    except ImportError as exc:  # pragma: no cover
        raise LLMError("litellm is not installed: pip install litellm") from exc

    complete.last_usage = {"tokens": None, "status": "error"}
    started = time.monotonic()
    kwargs: dict[str, Any] = {
        "timeout": float(os.getenv("LLM_TIMEOUT_SECONDS", "120")),
        "num_retries": 0,
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
    try:
        resp = litellm.completion(**kwargs)
    except Exception as exc:
        complete.last_usage["seconds"] = time.monotonic() - started
        raise LLMError(f"transport:{type(exc).__name__}") from None
    choice = resp["choices"][0]
    usage = resp.get("usage") or {}
    complete.last_usage = {"tokens": usage.get("total_tokens", 0),
                           "seconds": time.monotonic() - started,
                           "finish_reason": choice.get("finish_reason"), "status": "error"}
    if choice.get("finish_reason") not in (None, "stop"):
        raise LLMError("incomplete_response")
    content = choice["message"]["content"]
    if not isinstance(content, str) or not content.strip():
        raise LLMError("empty_response")
    complete.last_usage["status"] = "ok"
    return content


def complete_json_list(prompt: str, system: str, **kw: Any) -> list[dict[str, Any]]:
    raw = complete(prompt, system, **kw)
    text = raw.strip()
    try:
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            # Only unwrap prose; never accept an inner fragment of malformed JSON.
            if text.startswith(("[", "{")):
                raise
            text = _strip_fences(text)
            data = json.loads(_first_json_array(text))
    except json.JSONDecodeError as exc:
        raise LLMError("invalid_json") from exc
    if isinstance(data, dict):
        for key in ("tasks", "candidates", "items"):
            if key in data and isinstance(data[key], list):
                data = data[key]
                break
        else:
            data = [data]
    if not isinstance(data, list):
        raise LLMError("expected a JSON array of task objects")
    if any(not isinstance(d, dict) for d in data):
        raise LLMError("expected_task_objects")
    return data
