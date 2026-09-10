#!/usr/bin/env python3
"""Offline probe: change the base after candidate resolution, then report old tests."""
import json
from pathlib import Path
import sys
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'gpt6'))
from tests_github.test_integration import GitHubIntegrationTests
from intuition_github.verification import resolve_candidate, report_candidate


def probe():
    fixture = GitHubIntegrationTests()
    fixture.setUp()
    try:
        task = fixture.first_candidate()
        hub, config = fixture.hub, fixture.config
        number, head = task['pr_number'], task['attempts'][-1]['head_sha']
        before = resolve_candidate(hub, config, number, head)
        changed_base = hub.create_commit(hub.ref('main'), {'demo_app/metrics.py': b'# Concurrent change\n'}, 'advance base')
        hub.advance_ref('main', changed_base, hub.ref('main'))
        hub.pull_items[number]['base']['sha'] = changed_base
        report_candidate(hub, config, number, head, 'success', 'https://example.invalid/offline-test')
        return {'mode': 'offline-fake-github-real-git', 'tested_base': before['base_sha'],
                'current_base': changed_base, 'head': head,
                'reported_status': hub.status_items[head][0]['state'],
                'finding': 'Reporter accepts prior success after base changes; receipt must bind head, base and tested merge result. No remote merge was attempted.'}
    finally:
        fixture.doCleanups()


if __name__ == '__main__':
    print(json.dumps(probe(), indent=2))
