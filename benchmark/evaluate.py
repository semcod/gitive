"""Run an immutable oracle outside the editable project. Invoked in a clean child environment."""
import argparse
import contextlib
import importlib.util
import io
import json
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from benchmark.fixtures import PROJECTS


def evaluate(root, project, stage):
    spec = importlib.util.spec_from_file_location("candidate", Path(root) / "src/core.py")
    module = importlib.util.module_from_spec(spec)
    result = {"passed": 0, "total": 0, "failures": []}
    try:
        with contextlib.redirect_stdout(io.StringIO()):
            spec.loader.exec_module(module)
    except BaseException as exc:
        result['import_error'] = type(exc).__name__ + ': ' + str(exc)[:300]
        module = None
    for index, (level, function, args, expected) in enumerate(PROJECTS[project]["cases"]):
        if level > stage:
            continue
        result['total'] += 1
        error = None
        try:
            if module is None:
                raise RuntimeError(result['import_error'])
            with contextlib.redirect_stdout(io.StringIO()):
                actual = getattr(module, function)(*args)
            passed = actual == expected
            if not passed:
                error = f"{function}{args!r}: expected {expected!r}, got {actual!r}"
        except BaseException as exc:
            passed, error = False, f"{function}{args!r}: {type(exc).__name__}: {str(exc)[:300]}"
        if passed:
            result['passed'] += 1
        else:
            result['failures'].append({'id': f'{project}:{index + 1}', 'stage': level, 'error': error})
    result['green'] = result['passed'] == result['total'] and result['total'] > 0
    return result


if __name__ == '__main__':
    p=argparse.ArgumentParser(); p.add_argument('root'); p.add_argument('project'); p.add_argument('stage',type=int)
    a=p.parse_args(); print(json.dumps(evaluate(a.root,a.project,a.stage),ensure_ascii=False))
