"""Reconcile immutable source releases; conflicts fail closed, retries never clobber."""
from __future__ import annotations
import hashlib
import json
import os
import sys
import tempfile
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from intuition_github.github import GitHub
from intuition_github.util import GuardError, sha


def tag_commit(hub, tag):
    value = hub.api(f"{hub.prefix}/git/ref/tags/{tag}", missing_ok=True)
    if value is None:
        return None
    obj = value["object"]
    for _ in range(10):
        if obj["type"] == "commit":
            return sha(obj["sha"])
        if obj["type"] != "tag":
            break
        obj = hub.api(f"{hub.prefix}/git/tags/{sha(obj['sha'])}")["object"]
    raise GuardError("Release tag does not resolve to a commit")


def validate_local(directory, commit):
    names = ("intuition-github.zip", "SHA256SUMS.txt", "release-manifest.json")
    files = {n: (directory / n).read_bytes() for n in names}
    checksum = hashlib.sha256(files[names[0]]).hexdigest()
    manifest = json.loads(files[names[2]])
    if (manifest != {"version": 1, "commit": commit, "artifacts": {names[0]: checksum}}
            or files[names[1]] != f"{checksum}  {names[0]}\n".encode()):
        raise GuardError("Local release manifest/checksum/source mismatch")
    return files


def check_assets(hub, tag, release, expected):
    assets = release.get("assets", [])
    names = [a["name"] for a in assets]
    if len(names) != len(set(names)) or set(names) - set(expected):
        raise GuardError("Unexpected or duplicate release assets")
    with tempfile.TemporaryDirectory(prefix="verify-release-") as folder:
        for name in names:
            hub.command(["release", "download", tag, "--repo", hub.repository,
                         "--pattern", name, "--dir", folder])
            if (Path(folder) / name).read_bytes() != expected[name]:
                raise GuardError("Existing release asset conflicts: " + name)
    return [n for n in expected if n not in names]


def publish(hub, commit, directory):
    commit = sha(commit)
    expected = validate_local(Path(directory), commit)
    tag = "build-" + commit[:20]
    target = tag_commit(hub, tag)
    if target is None:
        hub.api(f"{hub.prefix}/git/refs", "POST", {"ref": "refs/tags/" + tag, "sha": commit})
    elif target != commit:
        raise GuardError("Existing release tag targets another commit")
    if tag_commit(hub, tag) != commit:
        raise GuardError("Release tag changed during reconciliation")
    endpoint = f"{hub.prefix}/releases/tags/{tag}"
    release = hub.api(endpoint, missing_ok=True)
    if release is None:
        # Create an empty draft first. A restart reconciles each immutable asset.
        hub.command(["release", "create", tag, "--repo", hub.repository, "--verify-tag", "--draft",
                     "--title", f"Verified build {commit[:12]}", "--notes", f"Source commit {commit}.", "--prerelease"])
        release = hub.api(endpoint)
    missing = check_assets(hub, tag, release, expected)
    for name in missing:
        hub.command(["release", "upload", tag, str(Path(directory) / name), "--repo", hub.repository])
    if tag_commit(hub, tag) != commit or check_assets(hub, tag, hub.api(endpoint), expected):
        raise GuardError("Published release is incomplete or tag changed")
    if release.get("draft"):
        hub.command(["release", "edit", tag, "--repo", hub.repository, "--draft=false"])
    final = hub.api(endpoint)
    if final.get("draft") or tag_commit(hub, tag) != commit or check_assets(hub, tag, final, expected):
        raise GuardError("Final release verification failed")
    return {"status": "release_verified", "commit": commit, "tag": tag,
            "sha256": {n: hashlib.sha256(b).hexdigest() for n, b in expected.items()}}


def main():
    result = publish(GitHub(os.environ["GITHUB_REPOSITORY"]), os.environ["RELEASE_SHA"], Path("dist"))
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
