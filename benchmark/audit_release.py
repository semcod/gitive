#!/usr/bin/env python3
"""Offline release acceptance matrix against the actual reconciler."""
import io
import json
from pathlib import Path
import sys
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'gpt6'))
from tests_github.test_delivery import ReleaseTests


def probe():
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(ReleaseTests)
    log = io.StringIO()
    result = unittest.TextTestRunner(stream=log).run(suite)
    return {'mode': 'offline-real-publisher-fake-github', 'tests': result.testsRun,
            'passed': result.wasSuccessful(), 'failures': len(result.failures), 'errors': len(result.errors),
            'coverage': ['wrong tag', 'wrong bytes', 'missing asset', 'lost create/upload/edit response',
                         'idempotent retry', 'local manifest mismatch'], 'remote_writes': False}


if __name__ == '__main__':
    result = probe()
    print(json.dumps(result, indent=2))
    raise SystemExit(0 if result['passed'] else 1)
