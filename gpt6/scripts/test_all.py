"""Run the fixed regression suites. No API keys, install hooks or model-supplied commands."""
from __future__ import annotations
import argparse
import os
from pathlib import Path
import subprocess
import sys
import tempfile


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--target", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    root = args.target.resolve()
    commands = [
        [sys.executable, "-m", "unittest", "discover", "-s", "python", "-p", "test_*.py", "-v"],
        ["node", "--experimental-strip-types", "--test", "typescript/test-engine.ts"],
        [sys.executable, "tests/crosscheck.py"],
        [sys.executable, "-m", "unittest", "discover", "-s", "tests_github", "-p", "test_*.py", "-v"],
    ]
    with tempfile.TemporaryDirectory(prefix="intuition-test-home-") as home:
        # Never pass GitHub/LLM credentials or Actions command files to candidate processes.
        env = {"PATH": os.environ.get("PATH", ""), "HOME": home, "LANG": "C.UTF-8",
               "PYTHONPATH": str(root), "PYTHONDONTWRITEBYTECODE": "1", "PYTHONNOUSERSITE": "1",
               "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": os.devnull}
        for command in commands:
            print("Running:", " ".join(command), flush=True)
            result = subprocess.run(command, cwd=root, env=env, timeout=600, check=False)
            if result.returncode:
                return result.returncode
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
