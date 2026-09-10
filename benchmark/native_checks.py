#!/usr/bin/env python3
"""Replay historical patches through native local executors (no paid LLM calls)."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
import sys
import tempfile
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from benchmark.fixtures import PROJECTS


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--solution', choices=['glm53', 'opus5'], required=True)
    args = parser.parse_args()
    sys.path.insert(0, str(ROOT / args.solution / ('src' if args.solution == 'opus5' else '.')))
    results = []
    for name, fixture in PROJECTS.items():
        code = json.loads((ROOT / 'benchmark/runs/20260910T104959Z-48c133/final' / f'{args.solution}--{name}.json').read_text())['code']
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            def git(*argv):
                return subprocess.run(['git', *argv], cwd=root, check=True, capture_output=True)
            git('init', '-b', 'main'); git('config', 'user.name', 'Test'); git('config', 'user.email', 'test@example.invalid')
            (root / '.gitignore').write_text('.intuition.lock\n.intuition-pending.json\n__pycache__/\n')
            (root / 'src').mkdir(); (root / 'src/core.py').write_text(fixture['source'])
            checks = 'from src import core\n'
            for _, fn, inputs, expected in fixture['cases']:
                expression = f'core.{fn}(*{inputs!r})'
                checks += (f'assert abs({expression} - {expected!r}) < 1e-9\n' if isinstance(expected, (float, int)) and not isinstance(expected, bool)
                           else f'assert {expression} == {expected!r}\n')
            (root / 'check.py').write_text(checks)
            git('add', '.'); git('commit', '-m', 'controlled fixture')
            argv = [sys.executable, '-B', 'check.py']
            if args.solution == 'opus5':
                from intuition.config import Config
                from intuition.repair import repair
                task = dict(id=name, title=fixture['description'], files=['src/core.py'], phi=[1., 0., -.1, 0.])
                result = repair(Config(), root, task, argv,
                                lambda *a, **kw: [{'path': 'src/core.py', 'content': code}])
            else:
                from intuition.store import Store
                from intuition.llm import Client
                from intuition.refactor import refactor_step
                from intuition.core import replay
                store = Store(root)
                with store.lock():
                    store.init(fixture['description'])
                    class Recorded(Client):
                        def __call__(self, system, user, temperature):
                            if 'PATCH' in system:
                                return {'files': [{'path': 'src/core.py', 'content': code}]}
                            return super().__call__(system, user, temperature)
                    result = refactor_step(store, Recorded('mock'), None, 7, ['src'], argv,
                                           repair_base=True, apply_local=True)
                replay(store)
            assert result['passed'], result
            subprocess.run(argv, cwd=root, check=True)
            assert git('status', '--porcelain').stdout == b''
            results.append(dict(project=name, passed=True, cases=len(fixture['cases']), status=result['status']))
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    out = ROOT / 'benchmark/native-runs' / stamp
    out.mkdir(parents=True, exist_ok=True)
    path = out / (args.solution + '.json')
    path.write_text(json.dumps(dict(solution=args.solution, mode='recorded-patch-native-executor', results=results), indent=2))
    print(path)


if __name__ == '__main__':
    main()
