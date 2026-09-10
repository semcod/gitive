"""Lazy LiteLLM integration and a dependency-free compatible transport."""
import json
import os
import time
import urllib.error
import urllib.request


def extract_json(text):
    text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        decoder = json.JSONDecoder()
        for i, ch in enumerate(text):
            if ch in "[{":
                try:
                    return decoder.raw_decode(text[i:])[0]
                except json.JSONDecodeError:
                    continue
    raise ValueError("LLM nie zwrócił JSON")


class Client:
    def __init__(self, backend=None):
        self.calls = 0
        self.events = []
        self.max_calls = int(os.getenv("LLM_MAX_CALLS", "20"))
        self.backend = backend or os.getenv("LLM_BACKEND", "litellm")
        if self.backend not in ("compatible", "litellm", "mock"):
            raise ValueError("Nieznany backend LLM")

    def __call__(self, system, user, temperature):
        if self.calls >= self.max_calls:
            raise RuntimeError("LLM call budget exhausted")
        self.calls += 1
        event = {"call": self.calls, "phase": system.split(".", 1)[0], "tokens": None,
                 "finish_reason": None, "status": "error"}
        self._event = event
        start = time.monotonic()
        try:
            result = self._complete(system, user, temperature)
            event["status"] = "ok"
            return result
        finally:
            event["seconds"] = time.monotonic() - start
            self.events.append(event)

    def _complete(self, system, user, temperature):
        if self.backend == "mock":
            context = json.loads(user)
            if "PROPOSE" in system:
                refs = [f["id"] for f in context["knowledge"]["facts"][-2:]]
                return [{"archetype": a, "prompt": f"Krok {context['step']}: {a} — zbadaj konsekwencje danych.",
                         "references": refs, "rationale": "Demonstracja offline"}
                        for a in ("derive", "verify", "connect", "decompose", "ask")][:context["m"]]
            if "PATCH" in system:
                return {"files": [{"path": "examples/demo.py", "content": "def add(a, b):\n    return a + b\n"}]}
            n = context["step"]
            return [{"content": f"Obserwacja demonstracyjna {n}: identyfikator próbki demo{n:08d}.",
                     "tags": ["demo"], "references": context["task"]["references"]}]
        model = os.getenv("LLM_MODEL", "openrouter/z-ai/glm-5.3")
        if not model:
            raise ValueError("Ustaw LLM_MODEL")
        timeout = float(os.getenv("LLM_TIMEOUT", "180"))
        payload = dict(model=model, temperature=temperature,
                       max_tokens=int(os.getenv("LLM_MAX_TOKENS", "4096")),
                       messages=[dict(role="system", content=system), dict(role="user", content=user)])
        if self.backend == "litellm":
            try:
                from litellm import completion
            except ImportError:
                raise RuntimeError("Zainstaluj: pip install '.[llm]'") from None
            kwargs = dict(timeout=timeout, num_retries=0)
            if os.getenv("LLM_REASONING_EFFORT"):
                kwargs["reasoning_effort"] = os.environ["LLM_REASONING_EFFORT"]
            if os.getenv("LLM_BASE_URL"):
                kwargs["api_base"] = os.environ["LLM_BASE_URL"]
            key = os.getenv("OPENROUTER_API_KEY") or os.getenv("LLM_API_KEY")
            if key:
                kwargs["api_key"] = key
            try:
                result = completion(**payload, **kwargs)
                usage = getattr(result, "usage", None)
                self._event["tokens"] = getattr(usage, "total_tokens", None)
                self._event["cost_usd"] = getattr(result, "_hidden_params", {}).get("response_cost")
                choice = result.choices[0]
                self._event["finish_reason"] = choice.finish_reason
                text = choice.message.content
                if choice.finish_reason not in (None, "stop"):
                    raise ValueError("LLM: limit tokenów wyczerpany; zwiększ LLM_MAX_TOKENS lub zmniejsz LLM_REASONING_EFFORT")
            except ValueError:
                raise
            except Exception as exc:
                raise RuntimeError(f"LiteLLM: {type(exc).__name__}; sprawdź model i konfigurację") from None
        else:
            base = os.getenv("LLM_BASE_URL")
            if not base:
                raise ValueError("Ustaw LLM_BASE_URL (łącznie z /v1)")
            headers = {"Content-Type": "application/json"}
            key = os.getenv("OPENROUTER_API_KEY") or os.getenv("LLM_API_KEY")
            if key:
                headers["Authorization"] = f"Bearer {key}"
            request = urllib.request.Request(base.rstrip("/") + "/chat/completions",
                data=json.dumps(payload).encode(), headers=headers, method="POST")
            try:
                with urllib.request.urlopen(request, timeout=timeout) as response:
                    data = json.load(response)
                choice = data["choices"][0]
                self._event["tokens"] = (data.get("usage") or {}).get("total_tokens")
                self._event["finish_reason"] = choice.get("finish_reason")
                if choice.get("finish_reason") not in (None, "stop"):
                    raise ValueError("LLM: incomplete response")
                text = choice["message"]["content"]
            except urllib.error.HTTPError as exc:
                raise RuntimeError(f"LLM HTTP {exc.code}") from None
            except (OSError, KeyError, IndexError, TypeError) as exc:
                raise RuntimeError(f"LLM: błędna odpowiedź lub transport ({type(exc).__name__})") from None
        if not isinstance(text, str):
            raise ValueError("LLM: brak treści odpowiedzi")
        return extract_json(text)
