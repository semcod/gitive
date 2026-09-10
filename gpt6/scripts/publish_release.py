"""CD = continuous delivery to GitHub Releases; NOT deployment to an unspecified server."""
from __future__ import annotations
import os
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from intuition_github.github import GitHub
from intuition_github.util import sha

hub = GitHub(os.environ["GITHUB_REPOSITORY"])
commit = sha(os.environ["RELEASE_SHA"])
tag = "build-" + commit[:20]
exists = hub.api(f"{hub.prefix}/releases/tags/{tag}", missing_ok=True)
files = ["dist/intuition-github.zip", "dist/SHA256SUMS.txt"]
if not exists:
    hub.command(["release", "create", tag, *files, "--repo", hub.repository, "--target", commit,
                 "--title", f"Verified build {commit[:12]}", "--notes", f"Source package from CI-tested commit {commit}. Not a production deployment.",
                 "--prerelease"])
else:
    existing_names = {a["name"] for a in exists.get("assets", [])}
    missing = [f for f in files if Path(f).name not in existing_names]
    if missing:
        hub.command(["release", "upload", tag, *missing, "--repo", hub.repository])
print(f"Delivered build {commit}; release tag {tag}")
