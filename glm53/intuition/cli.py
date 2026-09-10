"""CLI: explicit local, preview, and publication operations."""
import argparse
import json
import os
from pathlib import Path
import sys
from .core import replay, run_step
from .facts import frontier
from .llm import Client
from .store import Store


def parser():
    p = argparse.ArgumentParser(description="Intuicja: LLM + git + krytyk")
    p.add_argument("--root", default=".", help="Główny katalog repozytorium pamięci/kodu")
    p.add_argument("--backend", choices=["compatible", "litellm", "mock"])
    sub = p.add_subparsers(dest="command", required=True)
    init = sub.add_parser("init")
    init.add_argument("seed")
    init.add_argument("--tau", type=float, default=.35)
    init.add_argument("--m", type=int, default=5)
    init.add_argument("--eta", type=float, default=0)
    run = sub.add_parser("run")
    run.add_argument("--steps", type=int, default=1)
    run.add_argument("--seed", type=int, default=7)
    run.add_argument("--dry-run", action="store_true")
    sub.add_parser("status")
    sub.add_parser("replay")
    sub.add_parser("recover")
    sync = sub.add_parser("sync-ci")
    sync.add_argument("--repo", default=os.getenv("GITHUB_REPOSITORY"))
    sync.add_argument("--limit", type=int, default=20)
    ref = sub.add_parser("refactor")
    ref.add_argument("--repo", default=os.getenv("GITHUB_REPOSITORY"))
    ref.add_argument("--seed", type=int, default=7)
    ref.add_argument("--allow", nargs="+", default=["intuition"])
    ref.add_argument("--test", default='["python3","-m","unittest","discover","-s","tests","-v"]', help="Tablica JSON argumentów, bez shell")
    ref.add_argument("--base", default="main")
    ref.add_argument("--publish", action="store_true", help="Utwórz issue, push i PR")
    repair = sub.add_parser("repair")
    repair.add_argument("pr", type=int)
    repair.add_argument("--repo", default=os.getenv("GITHUB_REPOSITORY"))
    repair.add_argument("--seed", type=int, default=7)
    repair.add_argument("--allow", nargs="+", default=["intuition"])
    repair.add_argument("--test", default='["python3","-m","unittest","discover","-s","tests","-v"]')
    merge = sub.add_parser("auto-merge")
    merge.add_argument("pr", type=int)
    merge.add_argument("--repo", default=os.getenv("GITHUB_REPOSITORY"))
    return p


def main(argv=None):
    # Read only this project's .env; never search parent directories for credentials.
    prelim = argparse.ArgumentParser(add_help=False)
    prelim.add_argument("--root", default=".")
    root_args, _ = prelim.parse_known_args(argv)
    env_path = Path(root_args.root).resolve() / ".env"
    if env_path.exists():
        try:
            from dotenv import load_dotenv
        except ImportError:
            print("Plik .env wymaga python-dotenv; można też eksportować zmienne shell.", file=sys.stderr)
        else:
            load_dotenv(env_path, override=False)
    args = parser().parse_args(argv)
    store = Store(args.root)
    try:
        if args.command == "recover":
            # A stale lock must be inspected and removed by the operator first.
            with store.lock():
                store.recover()
            print("Odzyskiwanie zakończone")
            return
        if args.command in ("status", "replay"):
            store.clean()
            result = replay(store) if args.command == "replay" else dict(state=store.state(), facts=len(store.facts()), frontier=frontier(store.facts()))
        else:
            with store.lock():
                if args.command == "init":
                    store.init(args.seed, args.tau, args.m, args.eta)
                    result = {"status": "initialized", "root": str(store.root)}
                elif args.command == "run":
                    if not 1 <= args.steps <= 100:
                        raise ValueError("steps musi należeć do 1..100")
                    result = []
                    for _ in range(args.steps):
                        row = run_step(store, Client(args.backend), args.seed, args.dry_run)
                        result.append(row)
                else:
                    from .ci_facts import GitHub, sync_ci_facts
                    from .refactor import refactor_step, request_auto_merge, repair_pr
                    gh = GitHub(args.repo, store.root)
                    if args.command == "sync-ci":
                        result = {"new_ci_facts": sync_ci_facts(store, gh, args.limit)}
                    elif args.command == "auto-merge":
                        result = request_auto_merge(gh, args.pr)
                    else:
                        test = json.loads(args.test)
                        if not isinstance(test, list) or not test or not all(isinstance(x, str) for x in test):
                            raise ValueError("--test musi być niepustą tablicą stringów JSON")
                        if args.command == "repair":
                            result = repair_pr(store, Client(args.backend), gh, args.pr, args.seed, args.allow, test)
                        else:
                            result = refactor_step(store, Client(args.backend), gh, args.seed, args.allow,
                                                   test, args.base, args.publish)
        print(json.dumps(result, ensure_ascii=False, indent=2))
    except (ValueError, RuntimeError, OSError) as exc:
        print(f"Błąd: {exc}", file=sys.stderr)
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
