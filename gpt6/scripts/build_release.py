"""Build a source ZIP and checksum using tracked files, excluding local secrets/state."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import subprocess
import zipfile


def include(path: str) -> bool:
    p = PurePosixPath(path)
    forbidden = {".git", ".venv", ".local", "__pycache__", "node_modules", "dist", "build"}
    if any(part in forbidden or part.endswith(".egg-info") for part in p.parts):
        return False
    if p.name.startswith(".env") and p.name != ".env.example":
        return False
    return p.suffix not in {".pyc", ".pyo"} and not p.is_absolute() and ".." not in p.parts


def build(root: Path, destination: Path) -> Path:
    tracked = subprocess.check_output(["git", "-C", str(root), "ls-files", "-z"]).decode().split("\0")
    destination.mkdir(parents=True, exist_ok=True)
    result = destination / "intuition-github.zip"
    with zipfile.ZipFile(result, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for path in sorted(p for p in tracked if p and include(p)):
            source = root / path
            if source.is_symlink() or not source.is_file():
                raise ValueError("Only ordinary tracked files are allowed in releases")
            entry = zipfile.ZipInfo("intuition-github/" + path, date_time=(1980, 1, 1, 0, 0, 0))
            entry.compress_type = zipfile.ZIP_DEFLATED
            entry.external_attr = 0o100644 << 16
            archive.writestr(entry, source.read_bytes())
    checksum = hashlib.sha256(result.read_bytes()).hexdigest()
    (destination / "SHA256SUMS.txt").write_text(checksum + "  intuition-github.zip\n")
    revision = subprocess.run(["git", "-C", str(root), "rev-parse", "--verify", "HEAD"], capture_output=True, text=True)
    commit = revision.stdout.strip() if revision.returncode == 0 else None
    (destination / "release-manifest.json").write_text(json.dumps({"version": 1, "commit": commit,
        "artifacts": {"intuition-github.zip": checksum}}, sort_keys=True) + "\n")
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, default=Path("dist"))
    args = parser.parse_args()
    print(build(Path.cwd(), args.out.resolve()))
