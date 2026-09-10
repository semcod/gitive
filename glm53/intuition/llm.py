"""Lazy LiteLLM integration and a dependency-free compatible transport."""
import json
import os
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
        self.backend = backend or os.getenv("LLM_BACKEND", "litellm")
        if self.backend not in ("compatible", "litellm", "mock"):
            raise ValueError("Nieznany backend LLM")

    def __call__(self, system, user, temperature):
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
        model = os.getenv("LLM_MODEL", "openrouter/zai/glm-5.3")
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
            kwargs = dict(timeout=timeout, num_retries=2)
            if os.getenv("LLM_BASE_URL"):
                kwargs["api_base"] = os.environ["LLM_BASE_URL"]
            key = os.getenv("OPENROUTER_API_KEY") or os.getenv("LLM_API_KEY")
            if key:
                kwargs["api_key"] = key
            try:
                result = completion(**payload, **kwargs)
                text = result.choices[0].message.content
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
                text = data["choices"][0]["message"]["content"]
            except urllib.error.HTTPError as exc:
                raise RuntimeError(f"LLM HTTP {exc.code}") from None
            except (OSError, KeyError, IndexError, TypeError) as exc:
                raise RuntimeError(f"LLM: błędna odpowiedź lub transport ({type(exc).__name__})") from None
        if not isinstance(text, str):
            raise ValueError("LLM: brak treści odpowiedzi")
        return extract_json(text)
