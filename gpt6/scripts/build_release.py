"""Build a source ZIP and checksum using tracked files, excluding local secrets/state."""
from __future__ import annotations
import argparse
import hashlib
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
            archive.write(source, "intuition-github/" + path)
    checksum = hashlib.sha256(result.read_bytes()).hexdigest()
    (destination / "SHA256SUMS.txt").write_text(checksum + "  intuition-github.zip\n")
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, default=Path("dist"))
    args = parser.parse_args()
    print(build(Path.cwd(), args.out.resolve()))
