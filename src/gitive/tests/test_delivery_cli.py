import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch, MagicMock
from gitive.cli import main
from gitive.delivery import ReviewHub, config_for, DockerVerifier, summarize
from intuition_github.util import GuardError


class ReviewHubTests(unittest.TestCase):
    def test_create_pull_sets_draft_and_review_notice(self):
        hub = ReviewHub("example/repo")
        command_calls = []

        def fake_command(args, data=None):
            command_calls.append((args, data))
            return "https://github.com/example/repo/pull/42\n"

        fake_pull = {"number": 42, "state": "open", "title": "Test PR"}
        with patch.object(hub, "command", side_effect=fake_command), \
             patch.object(hub, "pull", return_value=fake_pull):
            pr = hub.create_pull("branch", "main", "Test PR", "Summary.\n\nKod wygenerowany przez LLM.")
            self.assertEqual(pr["number"], 42)

        args, data = command_calls[0]
        self.assertIn("--draft", args)
        self.assertIn(b"Gitive / native GPT6", data)
        self.assertIn(b"Independent review and publication remain required", data)


class DeliveryCliTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def test_config_for(self):
        cfg = config_for(["src/gitive/cli.py"])
        self.assertEqual(cfg["allowed_paths"], ["src/gitive/cli.py"])
        self.assertEqual(cfg["memory_branch"], "intuition-memory-gitive-delivery")

    def test_delivery_run_without_apply_raises(self):
        fake_ticket = MagicMock()
        fake_ticket.source.context = {
            "delivery": {
                "repository": "example/repo",
                "issue": 15,
                "paths": ["src/gitive/cli.py"],
                "task": "tid123"
            }
        }
        fake_bridge = MagicMock()
        fake_bridge.root = self.root
        fake_bridge.store.get_ticket.return_value = fake_ticket

        mock_memory = MagicMock()
        mock_memory.state = {"tasks": {"tid123": {"id": "tid123", "status": "ready", "issue_number": 15, "pr_number": None, "attempts": []}}}

        with patch("gitive.cli.ticket_bridge", return_value=fake_bridge), \
             patch("gitive.delivery.Memory", return_value=mock_memory), \
             patch("gitive.delivery.load_env"), \
             patch("gitive.delivery.command", return_value=str(self.root / ".git")):
            with self.assertRaisesRegex(GuardError, "Remote edits require delivery run --apply"):
                main(["delivery", "run", "demo", "--ticket", "PLF-123"])

    def test_summarize_structure(self):
        task = {
            "id": "task-abc",
            "status": "awaiting_review",
            "issue_number": 15,
            "pr_number": 42,
            "attempts": [{"head_sha": "sha1"}],
            "local_verification": {"status": "passed"},
            "human_reason": None
        }
        res = summarize(task, "PLF-100", "example/repo")
        self.assertEqual(res["ticket"], "PLF-100")
        self.assertEqual(res["task"], "task-abc")
        self.assertEqual(res["status"], "awaiting_review")
        self.assertEqual(res["pr"], "https://github.com/example/repo/pull/42")
        self.assertEqual(res["attempts"], 1)
        self.assertEqual(res["tests"], "passed")
    def test_delivery_status_display(self):
        fake_ticket = MagicMock()
        fake_ticket.id = "PLF-123"
        fake_ticket.source.context = {
            "delivery": {
                "repository": "example/repo",
                "issue": 15,
                "paths": ["src/gitive/cli.py"],
                "task": "tid123"
            }
        }
        fake_bridge = MagicMock()
        fake_bridge.root = self.root
        fake_bridge.store.get_ticket.return_value = fake_ticket

        mock_memory = MagicMock()
        mock_memory.state = {
            "tasks": {
                "tid123": {
                    "id": "tid123",
                    "status": "awaiting_review",
                    "issue_number": 15,
                    "pr_number": 42,
                    "attempts": [{"head_sha": "sha1"}],
                    "local_verification": {"status": "passed"},
                    "human_reason": None
                }
            }
        }

        with patch("gitive.cli.ticket_bridge", return_value=fake_bridge), \
             patch("gitive.delivery.Memory", return_value=mock_memory), \
             patch("gitive.delivery.load_env"), \
             patch("gitive.delivery.command", return_value=str(self.root / ".git")):
            summary = main(["delivery", "status", "demo", "--ticket", "PLF-123"])
            self.assertEqual(summary["status"], "awaiting_review")
            self.assertEqual(summary["pr"], "https://github.com/example/repo/pull/42")

    def test_delivery_import_registers_ticket_context(self):
        fake_ticket = MagicMock()
        fake_ticket.id = "PLF-015"
        fake_ticket.name = "Fix bug"
        fake_ticket.description = "Desc"
        fake_ticket.status.value = "open"
        fake_ticket.sync = {}
        fake_ticket.source.context = {}
        fake_bridge = MagicMock()
        fake_bridge.root = self.root
        fake_bridge.ensure.return_value = fake_ticket
        fake_bridge.store.get_ticket.return_value = fake_ticket

        fake_task = {
            "id": "tid-999",
            "title": "Fix bug",
            "issue_number": 15,
            "status": "ready",
            "pr_number": None,
            "attempts": [],
            "evidence": [{"text": "Body", "source": "https://github.com/example/repo/issues/15"}]
        }

        with patch("gitive.cli.ticket_bridge", return_value=fake_bridge), \
             patch("gitive.delivery.load_env"), \
             patch("gitive.delivery.ReviewHub"), \
             patch("gitive.delivery.Memory"), \
             patch("gitive.delivery.SelectedController") as mock_ctrl_cls, \
             patch("gitive.delivery.command") as mock_cmd:
            def cmd_side_effect(args, cwd=None, timeout=180):
                if args[:3] == ["docker", "image", "inspect"]:
                    return "sha256:" + "0" * 64
                if args[:2] == ["git", "rev-parse"]:
                    return str(self.root / ".git")
                return ""
            mock_cmd.side_effect = cmd_side_effect
            mock_ctrl = mock_ctrl_cls.return_value
            mock_ctrl.import_issue.return_value = fake_task

            res = main([
                "delivery", "import", "demo",
                "--repo", "example/repo",
                "--issue", "15",
                "--file", "src/gitive/cli.py",
                "--accept", "Criterion 1",
                "--image", "ubuntu:latest",
                "--test", json.dumps(["pytest", "test.py"])
            ])
            self.assertEqual(res["ticket"], "PLF-015")
            self.assertTrue(fake_bridge.store.update_ticket.called)
