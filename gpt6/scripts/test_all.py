"""Run the fixed regression suites. No API keys, install hooks or model-supplied commands."""
from __future__ import annotations
import argparse
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile


def typescript_runner() -> list[str]:
    """Return a local TypeScript runner compatible with the installed Node.

    Node 22+ can strip the supported TypeScript syntax itself.  Older Node
    versions use the already supported ``tsx`` runner when it is available;
    ``npx --yes`` is the last-resort bootstrap for a clean developer machine.
    """
    node_path = shutil.which("node") or ""
    versions = re.findall(r"(?:^|[/\\])v(\d+)(?:[./\\]|$)", node_path)
    if versions and int(versions[-1]) >= 22:
        return ["node", "--experimental-strip-types"]
    if shutil.which("tsx"):
        return ["tsx"]
    if shutil.which("npx"):
        return ["npx", "--yes", "tsx@4.23.13"]
    raise RuntimeError(
        "GPT6 TypeScript tests require Node 22+ or the tsx command (npx is also supported)"
    )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--target", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    root = args.target.resolve()
    node = typescript_runner()
    commands = [
        [sys.executable, "-m", "unittest", "discover", "-s", "python", "-p", "test_*.py", "-v"],
        [*node, "--test", "typescript/test-engine.ts"],
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
