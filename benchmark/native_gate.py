"""Trusted external test argv for the native Opus executor; no candidate commands."""
import json
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from benchmark.evaluate import evaluate

if __name__ == '__main__':
    project, stage, allowed = sys.argv[1:]
    current = evaluate(Path.cwd(), project, int(stage))
    full = evaluate(Path.cwd(), project, 3)
    regressions = {f['id'] for f in full['failures']} - set(json.loads(allowed))
    raise SystemExit(0 if current['green'] and not regressions else 1)
