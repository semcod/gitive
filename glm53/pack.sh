#!/usr/bin/env bash
set -euo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")"
python3 - <<'PY'
from pathlib import Path
import tarfile

root = Path.cwd()
out = root / 'dist' / 'glm53-intuition.tar.gz'
out.parent.mkdir(exist_ok=True)
# Explicit allowlist: no .env, facts, logs, git metadata or credentials.
items = ['intuition', 'tests', 'docs', 'examples', '.github', '.gitignore',
         '.env.example', 'pyproject.toml', 'requirements.txt', 'README.md', 'pack.sh', 'Makefile']
with tarfile.open(out, 'w:gz') as archive:
    for item in items:
        p = root / item
        files = sorted(p.rglob('*')) if p.is_dir() else [p]
        for f in files:
            if f.is_file() and not f.is_symlink() and '__pycache__' not in f.parts and f.suffix != '.pyc':
                archive.add(f, arcname='glm53/' + str(f.relative_to(root)), recursive=False)
print(out)
PY
