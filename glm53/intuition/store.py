"""Git is the transaction boundary; a journal allows recovery after interruption."""
from __future__ import annotations
import contextlib
import json
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from .facts import validate_fact
from .model import default_state, validate_state


def now():
    return datetime.now(timezone.utc).isoformat()


def dumps(value):
    return json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n"


def atomic_write(path, content):
    import tempfile
    fd, name = tempfile.mkstemp(prefix=".intuition-write-", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(name, path)
    finally:
        Path(name).unlink(missing_ok=True)


def command(args, cwd, timeout=180, env=None):
    result = subprocess.run(args, cwd=cwd, text=True, capture_output=True, timeout=timeout, env=env)
    if result.returncode:
        raise RuntimeError(f"{args[0]} {args[1]}: kod {result.returncode}: {result.stderr[-1500:]}")
    return result.stdout.strip()


class Store:
    def __init__(self, root):
        self.root = Path(root).resolve()

    def git(self, *args):
        return command(["git", *args], self.root)

    def check_root(self):
        if Path(self.git("rev-parse", "--show-toplevel")).resolve() != self.root:
            raise ValueError("--root musi wskazywać główny katalog repozytorium git")

    def clean(self):
        self.check_root()
        if self.git("status", "--porcelain"):
            raise ValueError("Repozytorium ma niezapisane zmiany; zapisz je przed uruchomieniem")

    @contextlib.contextmanager
    def lock(self):
        self.root.mkdir(parents=True, exist_ok=True)
        path = self.root / ".intuition.lock"
        try:
            fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        except FileExistsError:
            raise RuntimeError("Aktywna blokada .intuition.lock; po awarii sprawdź proces i użyj recover") from None
        try:
            os.write(fd, str(os.getpid()).encode())
            os.close(fd)
            yield
        finally:
            path.unlink(missing_ok=True)

    def facts(self):
        out = []
        for path in sorted((self.root / "facts").glob("*.json")):
            if path.is_symlink() or self.root not in path.resolve().parents:
                raise ValueError("Fakt nie może być dowiązaniem poza pamięć")
            f = validate_fact(json.loads(path.read_text(encoding="utf-8")))
            if path.stem != f["id"]:
                raise ValueError(f"Id nie odpowiada nazwie pliku: {path.name}")
            out.append(f)
        return out

    def state(self):
        return validate_state(json.loads((self.root / "state.json").read_text(encoding="utf-8")))

    def rows(self):
        p = self.root / "log/tasks.jsonl"
        return [json.loads(line) for line in p.read_text(encoding="utf-8").splitlines()] if p.exists() else []

    def transaction(self, files, message):
        self.clean()
        if (self.root / ".intuition-pending.json").exists():
            raise RuntimeError("Przerwana transakcja; użyj recover")
        for name in files:
            if name != "state.json" and name != "log/tasks.jsonl" and not (name.startswith("facts/") and name.endswith(".json")):
                raise ValueError("Niedozwolona ścieżka pamięci")
            p = self.root / name
            if ".." in Path(name).parts or p.is_symlink() or self.root not in p.resolve().parents:
                raise ValueError("Niebezpieczna ścieżka pamięci")
            if name.startswith("facts/") and p.exists():
                raise ValueError("Fakty są append-only")
        journal = self.root / ".intuition-pending.json"
        old = {name: (self.root / name).read_text(encoding="utf-8") if (self.root / name).exists() else None for name in files}
        atomic_write(journal, dumps({"head": self.git("rev-parse", "HEAD"), "old": old, "new": files}))
        try:
            for name, content in files.items():
                p = self.root / name
                p.parent.mkdir(parents=True, exist_ok=True)
                atomic_write(p, content)
            self.git("add", "--", *files)
            self.git("commit", "-m", message, "--", *files)
        except BaseException:
            self.recover()
            raise
        journal.unlink()

    def recover(self):
        journal = self.root / ".intuition-pending.json"
        if not journal.exists():
            return
        record = json.loads(journal.read_text(encoding="utf-8"))
        head = self.git("rev-parse", "HEAD")
        if head != record["head"]:
            # Commit may have succeeded just before the process stopped.
            if all(self.git("show", f"HEAD:{p}") == v.strip() for p, v in record["new"].items()):
                journal.unlink()
                return
            raise RuntimeError("HEAD zmienił się po awarii; wymagana ręczna inspekcja dziennika")
        for name, value in record["old"].items():
            p = self.root / name
            if p.exists() and p.read_text(encoding="utf-8") not in (record["new"][name], value):
                raise RuntimeError("Plik zmieniono po awarii; odmowa nadpisania")
        self.git("reset", "--quiet", "HEAD", "--", *record["old"])
        for name, value in record["old"].items():
            p = self.root / name
            if value is None:
                p.unlink(missing_ok=True)
            else:
                atomic_write(p, value)
        journal.unlink()

    def init(self, seed, tau=.35, m=5, eta=0):
        if not seed.strip():
            raise ValueError("Pusty fakt startowy")
        state = validate_state(default_state(tau, m, eta))
        self.root.mkdir(parents=True, exist_ok=True)
        if not (self.root / ".git").exists():
            self.git("init", "-b", "main")
        self.check_root()
        # Bootstrap only an empty repository. Existing project files are committed by the operator.
        try:
            self.git("rev-parse", "HEAD")
        except RuntimeError:
            if self.git("ls-files"):
                raise ValueError("Najpierw utwórz commit projektu")
            ignore = self.root / ".gitignore"
            if not ignore.exists():
                ignore.write_text(".env\n.intuition.lock\n.intuition-pending.json\n", encoding="utf-8")
            self.git("add", "--", ".gitignore")
            self.git("commit", "-m", "Initialize intuition repository", "--", ".gitignore")
        self.clean()
        if (self.root / "state.json").exists() or self.facts():
            raise ValueError("Pamięć już zainicjalizowana")
        fact = dict(id="f_0001", content=seed, tags=["seed", "open"], references=[], source="seed", created=now())
        self.transaction({"facts/f_0001.json": dumps(fact), "state.json": dumps(state)}, "intuition: seed")

    def fact_files(self, items, source):
        facts = self.facts()
        used = {f["id"] for f in facts}
        counter = max([int(i[2:]) for i in used if i.startswith("f_") and i[2:].isdigit()] or [0])
        files, ids = {}, []
        for item in items:
            counter += 1
            fid = item.get("id", f"f_{counter:04d}")
            if fid in used:
                raise ValueError(f"Istniejący fakt {fid}")
            used.add(fid)
            fact = validate_fact({**item, "id": fid, "source": source, "created": item.get("created", now())})
            files[f"facts/{fid}.json"] = dumps(fact)
            ids.append(fid)
        return files, ids
