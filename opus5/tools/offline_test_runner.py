"""Run the test suite without pytest installed (air-gapped sandbox).

Implements just enough of pytest: approx, tmp_path, monkeypatch.
Use real pytest anywhere it is available: `pip install -e ".[dev]" && pytest -q`.
"""
from __future__ import annotations

import importlib.util
import os
import sys
import tempfile
import traceback
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


class _Approx:
    def __init__(self, v, abs=None, rel=None):
        self.v, self.abs, self.rel = v, abs, rel

    def __eq__(self, other):
        tol = self.abs if self.abs is not None else max(1e-6, abs(self.v) * (self.rel or 1e-6))
        return abs(other - self.v) <= tol

    def __repr__(self):
        return f"approx({self.v})"


class _MonkeyPatch:
    def __init__(self):
        self._undo = []

    def chdir(self, path):
        old = os.getcwd()
        os.chdir(path)
        self._undo.append(lambda: os.chdir(old))

    def setattr(self, target, value, raising=True):
        if isinstance(target, str):
            parts = target.split(".")
            obj, i = None, 0
            for i in range(len(parts) - 1, 0, -1):
                try:
                    obj = importlib.import_module(".".join(parts[:i]))
                    break
                except ImportError:
                    continue
            if obj is None:
                raise ImportError(target)
            for p in parts[i:-1]:
                obj = getattr(obj, p)
            attr = parts[-1]
        else:
            obj, attr = target, value
            raise TypeError("use dotted-string form")
        old = getattr(obj, attr)
        setattr(obj, attr, value)
        self._undo.append(lambda: setattr(obj, attr, old))

    def setenv(self, k, v):
        old = os.environ.get(k)
        os.environ[k] = v
        self._undo.append(lambda: os.environ.pop(k) if old is None else os.environ.__setitem__(k, old))

    def undo(self):
        for fn in reversed(self._undo):
            fn()
        self._undo.clear()


fake = types.ModuleType("pytest")
fake.approx = lambda v, abs=None, rel=None: _Approx(v, abs, rel)
fake.raises = None
sys.modules.setdefault("pytest", fake)


def run(path: Path) -> int:
    spec = importlib.util.spec_from_file_location(path.stem, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    names = [n for n in dir(mod) if n.startswith("test_")]
    failed = 0
    cwd = os.getcwd()
    for name in names:
        fn = getattr(mod, name)
        kwargs, mp, tmp = {}, None, None
        varnames = fn.__code__.co_varnames[: fn.__code__.co_argcount]
        if "tmp_path" in varnames:
            tmp = tempfile.TemporaryDirectory()
            kwargs["tmp_path"] = Path(tmp.name)
        if "monkeypatch" in varnames:
            mp = _MonkeyPatch()
            kwargs["monkeypatch"] = mp
        try:
            fn(**kwargs)
            print(f"  PASS  {name}")
        except Exception:
            failed += 1
            print(f"  FAIL  {name}")
            traceback.print_exc(limit=4)
        finally:
            if mp:
                mp.undo()
            os.chdir(cwd)
            if tmp:
                tmp.cleanup()
    print(f"\n{len(names) - failed}/{len(names)} passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(max(run(path) for path in sorted((ROOT / "tests").glob("test_*.py"))))
