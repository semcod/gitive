"""Strict schemas, knowledge frontier, schema/novelty validation."""
from __future__ import annotations
import re
from .model import cos, embed

ID = re.compile(r"[a-zA-Z0-9][a-zA-Z0-9_.-]{0,159}\Z")


def strings(value):
    return isinstance(value, list) and all(isinstance(x, str) and x.strip() for x in value)


def validate_fact(f):
    if not isinstance(f, dict):
        raise ValueError("Fakt musi być obiektem")
    for key in ("id", "content", "source", "created"):
        if not isinstance(f.get(key), str) or not f[key].strip():
            raise ValueError(f"Fakt: brak {key}")
    if not ID.fullmatch(f["id"]) or not strings(f.get("tags")) or not strings(f.get("references")):
        raise ValueError("Fakt: błędne id, tags lub references")
    if "supersedes" in f and (not isinstance(f["supersedes"], str) or not ID.fullmatch(f["supersedes"])):
        raise ValueError("Fakt: błędne supersedes")
    return f


def frontier(facts):
    ids = {f["id"] for f in facts}
    retired = {f["supersedes"] for f in facts if f.get("supersedes")}
    return {"open": [f["id"] for f in facts if "open" in f["tags"] and f["id"] not in retired],
            "dangling": sorted({r for f in facts for r in f["references"]} - ids)}


def digest(facts, limit=40):
    retired = {f["supersedes"] for f in facts if f.get("supersedes")}
    return {"facts": [f for f in facts if f["id"] not in retired][-limit:], "frontier": frontier(facts)}


def validate_new(items, facts, limit=5):
    if not isinstance(items, list):
        raise ValueError("Wykonanie musi zwrócić tablicę JSON")
    vectors = [embed(f["content"]) for f in facts]
    contents = {f["content"].strip().casefold() for f in facts}
    ids = {f["id"] for f in facts}
    out = []
    for item in items:
        if not isinstance(item, dict) or not isinstance(item.get("content"), str) or not item["content"].strip():
            continue
        if not strings(item.get("tags")) or not strings(item.get("references", [])):
            continue
        if item.get("supersedes") is not None and (not isinstance(item["supersedes"], str) or item["supersedes"] not in ids):
            continue
        text = item["content"].strip()
        v = embed(text)
        if text.casefold() in contents or any(cos(v, old) >= 0.95 for old in vectors):
            continue
        fact = dict(content=text, tags=list(dict.fromkeys(item["tags"]))[:10],
                    references=list(dict.fromkeys(item.get("references", []))))
        if item.get("supersedes"):
            fact["supersedes"] = item["supersedes"]
        out.append(fact)
        contents.add(text.casefold())
        vectors.append(v)
        if len(out) >= limit:
            break
    return out
