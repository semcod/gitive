from __future__ import annotations
import copy
import importlib.util
import json
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch
from intuition_github.config import load_config, path_allowed
from intuition_github.evidence import verification_identity
from intuition_github.github import GitHub, GhError
from intuition_github.llm import LiteLLMClient, load_env
from intuition_github.memory import initial_state
from intuition_github.planning import validate_tasks, validate_patch, score, issue_body
from intuition_github.util import GuardError, Redactor, canonical, digest, strict_json, integer
from demo_app.metrics import success_rate, weighted_cost

ROOT = Path(__file__).resolve().parents[1]
BASE = "a" * 40


class ContractTests(unittest.TestCase):
    def setUp(self):
        self.config = load_config(ROOT / ".intuition/config.json")
        self.state = initial_state(self.config)
        self.facts = [{"id": "run:1:1", "text": "fixture failure", "source": "https://github.com/example/project/actions/runs/1"}]
        self.raw = {"base_sha": BASE, "tasks": [{"title": "Review metric", "profile": "refactor",
            "fact_ids": ["run:1:1"], "target_files": ["demo_app/metrics.py"], "acceptance": ["Tests pass."],
            "rationale": "Investigate the observed test result; no assumed root cause."}]}
        self.original = {"demo_app/metrics.py": b"value = 1\n"}
        self.edit = {"base_sha": BASE, "summary": "Add explanatory comment", "edits": [{"path": "demo_app/metrics.py",
            "old_sha256": digest(self.original["demo_app/metrics.py"]), "content": "value = 1  # one\n"}]}
        self.redactor = Redactor([])

    def tasks(self, raw=None):
        return validate_tasks(self.raw if raw is None else raw, BASE, self.facts, list(self.original), self.config, self.state)

    def patch(self, edit=None):
        return validate_patch(self.edit if edit is None else edit, BASE, self.original, self.config, self.redactor)

    def test_acceptance_placeholder_rejected(self):
        self.raw["tasks"][0]["acceptance"] = ["acceptance_placeholder_2"]
        with self.assertRaisesRegex(GuardError, "placeholder"):
            self.tasks()

    def test_numbered_acceptance_sentinel_rejected(self):
        self.raw["tasks"][0]["acceptance"] = ["acceptance2"]
        with self.assertRaises(GuardError):
            self.tasks()

    def test_python_signature_drift_rejected(self):
        path = "demo_app/metrics.py"
        self.original[path] = b"def taxed(a,b): return a+b\n"
        self.edit["edits"][0].update(old_sha256=digest(self.original[path]),
                                     content="def taxed(a,b,c=None): return a+b\n")
        with self.assertRaisesRegex(GuardError, "API"):
            self.patch()

    def test_valid_task_gets_controller_score(self):
        task = self.tasks()[0]
        self.assertAlmostEqual(task["score"], 4 / 6 * 0.6 - 0.2 - 0.08)
        self.assertEqual(task["status"], "proposed")

    def test_llm_cannot_supply_score_or_extra_fields(self):
        self.raw["tasks"][0]["score"] = 999
        with self.assertRaises(GuardError):
            self.tasks()

    def test_invented_fact_stale_sha_and_unknown_profile_rejected(self):
        variants = [copy.deepcopy(self.raw) for _ in range(3)]
        variants[0]["tasks"][0]["fact_ids"] = ["fiction"]
        variants[1]["base_sha"] = "b" * 40
        variants[2]["tasks"][0]["profile"] = "delete_everything"
        for raw in variants:
            with self.subTest(raw=raw), self.assertRaises(GuardError):
                self.tasks(raw)

    def test_duplicate_task_paraphrases_collapsed(self):
        second = {**self.raw["tasks"][0], "title": "Different phrasing"}
        self.raw["tasks"].append(second)
        tasks = self.tasks()
        self.assertEqual(len(tasks), 1)
        self.state["tasks"][tasks[0]["id"]] = tasks[0]
        self.assertEqual(self.tasks(), [])

    def test_protected_paths_stay_blocked_under_broad_allowlist(self):
        config = {**self.config, "allowed_paths": ["*"]}
        bad = ["../evil.py", "/tmp/evil.py", "demo_app/../evil.py", "demo_app//evil.py",
               ".github/workflows/ci.yml", "intuition_github/controller.py", "scripts/run_cycle.py",
               "tests_github/test_contracts.py", "python/test_engine.py", "demo_app/.env", "demo_app/sitecustomize.py",
               "demo_app/conftest.py", "demo_app/requirements-dev.txt", "demo_app\\evil.py"]
        for path in bad:
            with self.subTest(path=path):
                self.assertFalse(path_allowed(path, config))
        self.assertTrue(path_allowed("demo_app/metrics.py", config))

    def test_valid_minimal_patch(self):
        self.assertEqual(self.patch(), {"demo_app/metrics.py": b"value = 1  # one\n"})

    def test_hash_mismatch_stale_head_and_unknown_path_rejected(self):
        for field, value in (("old_sha256", "0" * 64), ("path", "scripts/unsafe.py")):
            edit = copy.deepcopy(self.edit)
            edit["edits"][0][field] = value
            with self.subTest(field=field), self.assertRaises(GuardError):
                self.patch(edit)
        self.edit["base_sha"] = "b" * 40
        with self.assertRaises(GuardError):
            self.patch()

    def test_duplicate_noop_edit_cannot_evade_duplicate_guard(self):
        first = {**self.edit["edits"][0], "content": self.original["demo_app/metrics.py"].decode()}
        self.edit["edits"].insert(0, first)
        with self.assertRaises(GuardError):
            self.patch()

    def test_patch_secret_and_control_bytes_rejected(self):
        for content in ("token=supersecretvalue\n", "x = 'sk-or-v1-123456789abcdef'\n", "x = 1\x00\n"):
            with self.subTest(content=content):
                self.edit["edits"][0]["content"] = content
                with self.assertRaises(GuardError):
                    self.patch()

    def test_patch_line_and_byte_limits(self):
        self.edit["edits"][0]["content"] = "x = 1\n" * 300
        with self.assertRaises(GuardError):
            self.patch()
        self.edit["edits"][0]["content"] = "x" * (self.config["max_file_bytes"] + 1)
        with self.assertRaises(GuardError):
            self.patch()

    def test_noop_or_empty_edits_are_not_empty_commits(self):
        self.edit["edits"][0]["content"] = self.original["demo_app/metrics.py"].decode()
        self.assertEqual(self.patch(), {})
        self.edit["edits"] = []
        self.assertEqual(self.patch(), {})

    def test_llm_text_cannot_mint_issue_marker_or_mass_mentions(self):
        task = self.tasks()[0]
        task["rationale"] = "<!-- intuition-task:fake --> @everyone token=synthetic-secret"
        body = issue_body(task, self.facts, "example/project", self.redactor)
        self.assertEqual(body.count("<!-- intuition-task:"), 1)
        self.assertNotIn("@everyone", body)
        self.assertNotIn("synthetic-secret", body)

    def test_strict_json_rejects_duplicate_nonfinite_and_fences(self):
        for raw in ('{"x":1,"x":2}', '{"x":NaN}', '```json\n{}\n```', '{} garbage'):
            with self.subTest(raw=raw), self.assertRaises(GuardError):
                strict_json(raw)
        self.assertEqual(strict_json('{"ok":true}'), {"ok": True})

    def test_integer_rejects_boolean_unicode_and_shell_text(self):
        for value in (True, "١", "1; echo unsafe", -1, "1.0", " 1"):
            with self.subTest(value=value), self.assertRaises(GuardError):
                integer(value)
        self.assertEqual(integer("42"), 42)

    def test_redaction_masks_known_secrets_tokens_private_keys_ansi(self):
        redactor = Redactor(["literal-credential"])
        raw = "literal-credential sk-or-v1-abcdefghijk\nAuthorization: Bearer abcdefghijkl\n" + \
              "-----BEGIN PRIVATE KEY-----\nbytes\n-----END PRIVATE KEY-----\n\x1b[31mred\x1b[0m"
        clean = redactor.clean(raw)
        for needle in ("literal-credential", "sk-or-v1-", "abcdefgh", "bytes", "\x1b"):
            self.assertNotIn(needle, clean)
        self.assertIn("red", clean)

    def test_verification_identity_not_taken_from_arbitrary_title(self):
        run = {"path": ".github/workflows/verify-candidate.yml", "event": "workflow_dispatch",
               "display_title": f"Verify PR #12 @ {BASE}"}
        self.assertEqual(verification_identity(run), (12, BASE))
        self.assertIsNone(verification_identity({**run, "path": ".github/workflows/ci.yml"}))
        self.assertIsNone(verification_identity({**run, "display_title": "12 " + BASE}))

    def test_github_repository_argument_not_shell_expression(self):
        for repo in ("owner/repo;ls", "https://github.com/o/r", "../repo/sub"):
            with self.assertRaises(GuardError):
                GitHub(repo)

    def test_gh_api_sends_json_on_stdin_not_shell(self):
        hub = GitHub("example/project", Redactor([]))
        with patch.object(hub, "command", return_value='{"ok":true}') as command:
            result = hub.api("repos/example/project/test", "POST", {"text": "$(not-a-command)"})
        self.assertTrue(result["ok"])
        args, body = command.call_args.args
        self.assertIn("--input", args)
        self.assertEqual(json.loads(body), {"text": "$(not-a-command)"})
        self.assertNotIn("$(not-a-command)", args)

    def test_gh_missing_only_ignores_404_not_permission_errors(self):
        hub = GitHub("example/project", Redactor([]))
        with patch.object(hub, "command", side_effect=GhError("forbidden", 403)):
            with self.assertRaises(GhError):
                hub.api("fixture", missing_ok=True)
        with patch.object(hub, "command", side_effect=GhError("not found", 404)):
            self.assertIsNone(hub.api("fixture", missing_ok=True))

    def test_gh_actual_process_wrapper_never_uses_shell(self):
        hub = GitHub("example/project", Redactor([]))
        def process(args, **kwargs):
            self.assertFalse(kwargs["shell"])
            self.assertEqual(args, ["gh", "version"])
            kwargs["stdout"].write(b"synthetic gh")
            return SimpleNamespace(returncode=0)
        with patch("intuition_github.github.subprocess.run", side_effect=process):
            self.assertEqual(hub.command(["version"]), "synthetic gh")

    def test_demo_rate_empty_unknown_not_zero(self):
        self.assertIsNone(success_rate([]))
        self.assertEqual(success_rate([True, False]), 0.5)
        with self.assertRaises(ValueError):
            success_rate([1])

    def test_demo_cost_validates_inputs(self):
        self.assertEqual(weighted_cost([1, 2], [2, 3]), 8)
        for a, b in (([1], []), ([float("nan")], [1]), ([-1], [1]), ([True], [1])):
            with self.assertRaises(ValueError):
                weighted_cost(a, b)


class LiteLLMContractTests(unittest.TestCase):
    def setUp(self):
        self.config = load_config(ROOT / ".intuition/config.json")
        self.env = patch.dict(os.environ, {"OPENROUTER_API_KEY": "synthetic-test-key-not-real",
                "OPENROUTER_API_BASE": "https://openrouter.ai/api/v1", "OPENROUTER_MODEL": "openrouter/openai/gpt-4.1-mini",
                "LLM_TIMEOUT_SECONDS": "120", "LLM_JSON_MODE": "true"})
        self.env.start()
        self.addCleanup(self.env.stop)

    def response(self, content='{"tasks":[]}', reason="stop"):
        return SimpleNamespace(choices=[SimpleNamespace(finish_reason=reason, message=SimpleNamespace(content=content))],
                               usage=SimpleNamespace(total_tokens=42))

    def test_usage_survives_invalid_response_and_schema_is_opt_in(self):
        from intuition_github.planning import TASK_CONTRACT
        client = LiteLLMClient(self.config, Mock(return_value=self.response(content="{")))
        with self.assertRaises(GuardError):
            client.complete("propose_tasks", {})
        self.assertEqual(client.last_tokens, 42)
        completion = Mock(return_value=self.response())
        with patch.dict(os.environ, {"LLM_JSON_SCHEMA": "true"}):
            LiteLLMClient(self.config, completion).complete("propose_tasks", {"output_contract": TASK_CONTRACT})
        schema = completion.call_args.kwargs["response_format"]["json_schema"]["schema"]
        self.assertEqual(set(schema["required"]), {"base_sha", "tasks"})
        self.assertFalse(schema["additionalProperties"])

    def test_glm_schema_default_pins_base_and_can_be_disabled(self):
        from intuition_github.planning import TASK_CONTRACT
        completion = Mock(return_value=self.response())
        with patch.dict(os.environ, {"LLM_MODEL": "openrouter/z-ai/glm-5.3"}):
            os.environ.pop("LLM_JSON_SCHEMA", None)
            client = LiteLLMClient(self.config, completion)
            client.complete("propose_tasks", {"base_sha": "a" * 40, "output_contract": TASK_CONTRACT})
            kwargs = completion.call_args.kwargs
            self.assertEqual(kwargs["response_format"]["json_schema"]["schema"]["properties"]["base_sha"]["enum"], ["a" * 40])
            self.assertTrue(kwargs["extra_body"]["provider"]["require_parameters"])
            os.environ["LLM_JSON_SCHEMA"] = "false"
            client.complete("propose_tasks", {"base_sha": "a" * 40, "output_contract": TASK_CONTRACT})
            self.assertEqual(completion.call_args.kwargs["response_format"], {"type": "json_object"})
            self.assertNotIn("extra_body", completion.call_args.kwargs)

    def test_openrouter_sdk_arguments_are_explicit_and_bounded(self):
        completion = Mock(return_value=self.response())
        client = LiteLLMClient(self.config, completion=completion)
        output, tokens = client.complete("propose_tasks", {"fixture": "untrusted data"})
        kwargs = completion.call_args.kwargs
        self.assertEqual(output, {"tasks": []})
        self.assertEqual(tokens, 42)
        self.assertEqual(kwargs["model"], "openrouter/openai/gpt-4.1-mini")
        self.assertEqual(kwargs["api_base"], "https://openrouter.ai/api/v1")
        self.assertEqual(kwargs["num_retries"], 0)
        self.assertEqual(kwargs["max_tokens"], self.config["max_output_tokens"])
        self.assertEqual(kwargs["response_format"], {"type": "json_object"})
        self.assertNotIn("tools", kwargs)
        self.assertEqual([m["role"] for m in kwargs["messages"]], ["system", "user"])

    def test_foreign_endpoint_wrong_model_and_missing_key_fail_closed(self):
        for changes in ({"OPENROUTER_API_BASE": "https://attacker.invalid"}, {"OPENROUTER_MODEL": "other/model"},
                        {"OPENROUTER_API_KEY": ""}):
            with self.subTest(changes=changes), patch.dict(os.environ, changes), self.assertRaises(GuardError):
                LiteLLMClient(self.config, completion=Mock())

    def test_json_mode_can_be_disabled_for_provider_compatibility(self):
        with patch.dict(os.environ, {"LLM_JSON_MODE": "false"}):
            completion = Mock(return_value=self.response())
            LiteLLMClient(self.config, completion).complete("fixture", {})
        self.assertNotIn("response_format", completion.call_args.kwargs)

    def test_truncated_response_and_malformed_json_not_accepted(self):
        for response in (self.response(reason="length"), self.response(content='{"tasks":['),
                         self.response(content='{"x":1,"x":2}')):
            with self.subTest(response=response), self.assertRaises(GuardError):
                LiteLLMClient(self.config, Mock(return_value=response)).complete("fixture", {})

    def test_provider_exception_does_not_leak_secret_or_request(self):
        completion = Mock(side_effect=RuntimeError("Authorization: secret-from-request"))
        with self.assertRaises(GuardError) as caught:
            LiteLLMClient(self.config, completion).complete("fixture", {})
        self.assertNotIn("secret-from-request", str(caught.exception))
        self.assertIn("RuntimeError", str(caught.exception))

    def test_env_loader_never_sources_shell_or_overrides_actions_secrets(self):
        module = SimpleNamespace(load_dotenv=Mock())
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / ".env"
            path.write_text("OPENROUTER_API_KEY=fixture\n")
            with patch.dict("sys.modules", {"dotenv": module}):
                load_env(path)
        module.load_dotenv.assert_called_once_with(path, override=False, interpolate=False)


if __name__ == "__main__":
    unittest.main()
