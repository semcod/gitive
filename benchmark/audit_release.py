#!/usr/bin/env python3
"""Read-only offline probe of release reconciliation, with a fake GitHub transport."""
import contextlib
import io
import json
import os
from pathlib import Path
import runpy
import sys
from types import ModuleType
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'gpt6'))


def probe():
    calls = []
    class Hub:
        repository = 'fixture/repo'
        prefix = 'repos/fixture/repo'
        def __init__(self, repository):
            pass
        def api(self, path, **kw):
            calls.append(['api', path])
            return {'target_commitish': 'b' * 40,
                    'assets': [{'name': 'intuition-github.zip'}, {'name': 'SHA256SUMS.txt'}]}
        def command(self, args):
            calls.append(['command', args])
    transport = ModuleType('intuition_github.github')
    transport.GitHub = Hub
    capture = io.StringIO()
    with patch.dict(sys.modules, {'intuition_github.github': transport}), patch.dict(
            os.environ, {'GITHUB_REPOSITORY': 'fixture/repo', 'RELEASE_SHA': 'a' * 40}), contextlib.redirect_stdout(capture):
        runpy.run_path(str(ROOT / 'gpt6/scripts/publish_release.py'), run_name='__main__')
    return {'mode': 'offline-fake-github', 'requested_sha': 'a' * 40,
            'existing_release_target_commitish': 'b' * 40,
            'publisher_reported_delivered': 'Delivered build' in capture.getvalue(),
            'tag_ref_checked': any('/git/' in str(call) for call in calls),
            'asset_contents_checked': False, 'calls': calls,
            'interpretation': 'Publisher reports success based on asset names without resolving tag SHA or verifying existing bytes. target_commitish alone does not prove actual tag mismatch.'}


if __name__ == '__main__':
    print(json.dumps(probe(), indent=2))
