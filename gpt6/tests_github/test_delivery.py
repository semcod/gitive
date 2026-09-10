"""Offline failure injection for the real release reconciler and verifier."""
import copy
import hashlib
import json
import os
from unittest.mock import patch
from pathlib import Path
import tempfile
import unittest
from scripts.publish_release import publish
from intuition_github.util import GuardError
from intuition_github.verification import resolve_candidate, report_candidate
from tests_github import test_integration


class ReleaseHub:
    repository = 'fixture/repo'
    prefix = 'repos/fixture/repo'
    def __init__(self):
        self.target = None
        self.release = None
        self.assets = {}
        self.creations = 0
        self.fail_after = None
    def api(self, path, method='GET', payload=None, missing_ok=False):
        if '/git/ref/tags/' in path:
            return {'object': {'sha': self.target, 'type': 'commit'}} if self.target else None
        if path.endswith('/git/refs'):
            self.target = payload['sha']
            return {}
        if '/releases/tags/' in path:
            return None if self.release is None else {**self.release, 'assets': [{'name': n} for n in self.assets]}
        raise AssertionError(path)
    def command(self, args):
        operation = args[1]
        if operation == 'create':
            assert '--verify-tag' in args and '--draft' in args
            self.creations += 1
            self.release = {'draft': True}
        elif operation == 'download':
            name = args[args.index('--pattern') + 1]
            (Path(args[args.index('--dir') + 1]) / name).write_bytes(self.assets[name])
        elif operation == 'upload':
            p = Path(args[3])
            assert p.name not in self.assets
            self.assets[p.name] = p.read_bytes()
        elif operation == 'edit':
            self.release['draft'] = False
        else:
            raise AssertionError(args)
        if self.fail_after == operation:
            self.fail_after = None
            raise OSError('Response lost after remote mutation')


class ReleaseTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name); self.commit = 'a' * 40
        self.hub = ReleaseHub()
        raw = b'fixture archive bytes'; checksum = hashlib.sha256(raw).hexdigest()
        (self.root / 'intuition-github.zip').write_bytes(raw)
        (self.root / 'SHA256SUMS.txt').write_text(checksum + '  intuition-github.zip\n')
        (self.root / 'release-manifest.json').write_text(json.dumps({'version': 1, 'commit': self.commit,
            'artifacts': {'intuition-github.zip': checksum}}))
    def run_publish(self):
        return publish(self.hub, self.commit, self.root)
    def test_verified_repeat_is_noop(self):
        self.assertEqual(self.run_publish()['status'], 'release_verified')
        before = copy.deepcopy(self.hub.assets)
        self.run_publish()
        self.assertEqual(self.hub.creations, 1); self.assertEqual(self.hub.assets, before)
    def test_wrong_tag_rejected(self):
        self.hub.target = 'b' * 40
        with self.assertRaises(GuardError): self.run_publish()
        self.assertEqual(self.hub.creations, 0)
    def test_wrong_existing_bytes_rejected_without_overwrite(self):
        self.run_publish(); self.hub.assets['intuition-github.zip'] = b'wrong'
        with self.assertRaises(GuardError): self.run_publish()
        self.assertEqual(self.hub.assets['intuition-github.zip'], b'wrong')
    def test_missing_asset_recovered(self):
        self.run_publish(); del self.hub.assets['SHA256SUMS.txt']
        self.run_publish(); self.assertEqual(len(self.hub.assets), 3)
    def test_lost_create_and_upload_responses_resume(self):
        for operation in ('create', 'upload', 'edit'):
            with self.subTest(operation=operation):
                self.hub = ReleaseHub(); self.hub.fail_after = operation
                with self.assertRaises(OSError): self.run_publish()
                self.assertEqual(self.run_publish()['status'], 'release_verified')
                self.assertEqual(self.hub.creations, 1)
    def test_local_manifest_mismatch_rejected_before_remote_changes(self):
        (self.root / 'intuition-github.zip').write_bytes(b'changed')
        with self.assertRaises(GuardError): self.run_publish()
        self.assertIsNone(self.hub.target)


class VerificationReceiptTests(unittest.TestCase):
    def test_stale_base_and_profile_fail_then_current_receipt_recovers(self):
        fixture = test_integration.GitHubIntegrationTests(); fixture.setUp(); self.addCleanup(fixture.doCleanups)
        task = fixture.first_candidate(); hub = fixture.hub; config = fixture.config
        head = task['attempts'][-1]['head_sha']; number = task['pr_number']
        before = resolve_candidate(hub, config, number, head)
        base = hub.ref('main')
        changed = hub.create_commit(base, {'demo_app/metrics.py': b'# concurrent\n'}, 'advance')
        hub.advance_ref('main', changed, base)
        with self.assertRaises(GuardError):
            report_candidate(hub, config, number, head, 'success', 'https://example.invalid/run', tested=before)
        self.assertEqual(hub.status_items[head][0]['state'], 'failure')
        current = resolve_candidate(hub, config, number, head)
        wrong = {**current, 'test_profile_digest': '0' * 64}
        with self.assertRaises(GuardError):
            report_candidate(hub, config, number, head, 'success', 'https://example.invalid/run', tested=wrong)
        report_candidate(hub, config, number, head, 'success', 'https://example.invalid/run', tested=current)
        self.assertEqual(hub.status_items[head][0]['state'], 'success')
        self.assertEqual(len(hub.issue_items), 1)

    def test_merge_request_rejects_stale_status_and_recovers_on_same_issue(self):
        fixture = test_integration.GitHubIntegrationTests(); fixture.setUp(); self.addCleanup(fixture.doCleanups)
        task = fixture.first_candidate(); hub = fixture.hub; config = fixture.config
        head = task['attempts'][-1]['head_sha']; number = task['pr_number']
        before = resolve_candidate(hub, config, number, head)
        report_candidate(hub, config, number, head, 'success', 'https://example.invalid/run', tested=before)
        hub.protection = {'required_status_checks': {'strict': True, 'contexts': ['Intuition / verified']},
                          'enforce_admins': {'enabled': True}, 'allow_force_pushes': {'enabled': False}}
        base = hub.ref('main')
        changed = hub.create_commit(base, {'demo_app/metrics.py': b'# concurrent base\n'}, 'advance')
        hub.advance_ref('main', changed, base)
        controller = fixture.controller()
        with patch.dict(os.environ, {'INTUITION_AUTOMERGE': 'true'}):
            controller.maybe_auto_merge(task)
            self.assertTrue(task['automerge_blocked'])
            self.assertFalse(any(op[0] == 'gh' and op[1][:2] == ['pr', 'merge'] for op in hub.operations))
            current = resolve_candidate(hub, config, number, head)
            report_candidate(hub, config, number, head, 'success', 'https://example.invalid/run2', tested=current)
            controller.maybe_auto_merge(task)
        self.assertTrue(task['automerge_requested'])
        self.assertEqual(len(hub.issue_items), 1)
