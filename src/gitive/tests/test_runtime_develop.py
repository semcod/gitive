import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock

from gitive.runtime_develop import _runtime_root, _test


class RuntimeDevelopTests(unittest.TestCase):
    def test_acceptance_command_is_delegated_to_digitaltwin(self):
        twin = Mock()
        twin.execute.return_value = {"status": "failed", "exit_code": 1, "log": "/no/log"}
        result = _test(twin, "doctor-agent", ["python3", "-m", "pytest"])
        twin.execute.assert_called_once_with("doctor-agent", ["python3", "-m", "pytest"], test=True)
        self.assertFalse(result["passed"])
        self.assertTrue(result["runtime"])

    def test_runtime_checkout_must_be_inside_private_workspace(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            checkout = root / "rootfs" / "home" / "tom" / "github" / "project"
            (checkout / ".git").mkdir(parents=True)
            record = {"root": str(root), "source": "/home/tom/github/project"}
            self.assertEqual(_runtime_root(record), checkout)

            escaped = {"root": str(root), "source": "/tmp/project"}
            with self.assertRaises(ValueError):
                _runtime_root(escaped)
