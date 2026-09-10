"""Source-package and fixed-workflow invariants; not a remote Actions execution test."""
from __future__ import annotations
import hashlib
import os
from pathlib import Path
import re
import subprocess
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import zipfile
from scripts.build_release import build, include
from scripts import test_all

ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = ROOT / ".github/workflows"


class ProjectFilesTests(unittest.TestCase):
    def test_release_filter_excludes_environment_and_caches(self):
        for path in (".env", ".env.production", "config/.env", ".venv/lib/x.py", "build/x.py", "../x.py", "a.pyc"):
            self.assertFalse(include(path), path)
        self.assertTrue(include(".env.example"))
        self.assertTrue(include(".github/workflows/ci.yml"))

    def test_release_archive_and_checksum_with_actual_git(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            subprocess.run(["git", "init", "--quiet", str(root)], check=True)
            (root / "main.py").write_text("print('fixture')\n")
            (root / ".env").write_text("API_KEY=synthetic-not-for-release\n")
            (root / ".env.example").write_text("API_KEY=\n")
            subprocess.run(["git", "-C", str(root), "add", "main.py", ".env", ".env.example"], check=True)
            archive = build(root, root / "dist")
            with zipfile.ZipFile(archive) as z:
                self.assertIsNone(z.testzip())
                self.assertIn("intuition-github/.env.example", z.namelist())
                self.assertNotIn("intuition-github/.env", z.namelist())
                self.assertNotIn(b"synthetic-not-for-release", b"".join(z.read(p) for p in z.namelist()))
            self.assertIn(hashlib.sha256(archive.read_bytes()).hexdigest(), (root / "dist/SHA256SUMS.txt").read_text())
            original = archive.read_bytes()
            os.utime(root / "main.py", (1800000000, 1800000000))
            self.assertEqual(build(root, root / "dist").read_bytes(), original)

    def test_release_builder_rejects_symlinks(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            subprocess.run(["git", "init", "--quiet", str(root)], check=True)
            (root / "link.py").symlink_to("/etc/passwd")
            subprocess.run(["git", "-C", str(root), "add", "link.py"], check=True)
            with self.assertRaises(ValueError):
                build(root, root / "dist")

    def test_all_third_party_actions_are_pinned_to_full_commit(self):
        uses = []
        for path in WORKFLOWS.glob("*.yml"):
            uses += re.findall(r"(?m)^\s*-?\s*uses:\s+(\S+)", path.read_text())
        self.assertGreater(len(uses), 10)
        for action in uses:
            self.assertRegex(action, r"^actions/[a-z-]+@[0-9a-f]{40}$")

    def test_workflows_do_not_use_pull_request_target(self):
        for path in WORKFLOWS.glob("*.yml"):
            self.assertNotIn("pull_request_target", path.read_text())

    def test_candidate_job_has_no_llm_or_write_token_environment(self):
        contents = (WORKFLOWS / "verify-candidate.yml").read_text()
        job = contents.split("  test:\n")[1].split("  report:\n")[0]
        self.assertNotIn("secrets.", job)
        self.assertNotIn("GH_TOKEN", job)
        self.assertNotIn(": write", job)
        self.assertIn("needs.resolve.outputs.head_sha", job)
        self.assertIn("controller/scripts/test_all.py --target candidate", job)

    def test_reporter_never_checks_out_candidate(self):
        contents = (WORKFLOWS / "verify-candidate.yml").read_text()
        reporter = contents.split("  report:\n")[1]
        self.assertIn("ref: ${{ github.sha }}", reporter)
        self.assertNotIn("ref: ${{ needs.resolve.outputs.head_sha }}", reporter)
        self.assertNotIn("path: candidate", reporter)
        self.assertIn("statuses: write", reporter)

    def test_persistent_loop_has_dispatch_schedule_and_serialization(self):
        contents = (WORKFLOWS / "intuition-loop.yml").read_text()
        for pattern in ("workflow_dispatch:", "workflow_run:", "cron: '17 */6 * * *'", "cancel-in-progress: false"):
            self.assertIn(pattern, contents)
        self.assertIn("INTUITION_GH_TOKEN || github.token", contents)

    def test_candidate_subprocess_environment_removes_credentials(self):
        observed = []
        def run(command, **kwargs):
            observed.append(kwargs["env"])
            return SimpleNamespace(returncode=0)
        with patch.dict(os.environ, {"GH_TOKEN": "fixture-gh", "OPENROUTER_API_KEY": "fixture-llm",
                                     "GITHUB_ENV": "/tmp/fixture-env", "GITHUB_OUTPUT": "/tmp/fixture-output"}), \
             patch("sys.argv", ["test_all.py", "--target", str(ROOT)]), \
             patch("scripts.test_all.subprocess.run", side_effect=run):
            self.assertEqual(test_all.main(), 0)
        self.assertEqual(len(observed), 4)
        for env in observed:
            for key in ("GH_TOKEN", "OPENROUTER_API_KEY", "GITHUB_ENV", "GITHUB_OUTPUT"):
                self.assertNotIn(key, env)

    def test_default_cd_is_delivery_not_unconfigured_server_deployment(self):
        contents = (WORKFLOWS / "cd.yml").read_text()
        self.assertIn("INTUITION_CD_ENABLED", contents)
        self.assertIn("needs: package", contents)
        self.assertIn("scripts/publish_release.py", contents)
        self.assertNotIn("ssh ", contents)

    def test_checkout_never_persists_credentials(self):
        for path in WORKFLOWS.glob("*.yml"):
            content = path.read_text()
            count = content.count("uses: actions/checkout@")
            self.assertEqual(count, content.count("persist-credentials: false"), path.name)

    def test_example_environment_has_no_credentials_and_is_opt_in(self):
        content = (ROOT / ".env.example").read_text()
        self.assertRegex(content, r"(?m)^OPENROUTER_API_KEY=$")
        self.assertRegex(content, r"(?m)^GH_TOKEN=$")
        self.assertIn("INTUITION_ENABLED=false", content)
        self.assertIn("INTUITION_AUTOMERGE=false", content)


if __name__ == "__main__":
    unittest.main()
