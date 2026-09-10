import unittest
from intuition.refactor import validate_edits
from intuition.facts import digest


class QualityTests(unittest.TestCase):
    def test_signature_change_rejected_body_change_allowed(self):
        source={'src/core.py':'def taxed(amount, percent):\n    return amount + percent\n'}
        for changed in ['def taxed(amount, percent, tax_rate=None): return amount', 'def other(amount, percent): return amount']:
            with self.assertRaises(ValueError):
                validate_edits({'files':[{'path':'src/core.py','content':changed}]},source)
        self.assertTrue(validate_edits({'files':[{'path':'src/core.py','content':'def taxed(amount, percent): return amount * (1+percent/100)'}]},source))

    def test_superseded_fact_excluded_from_prompt_not_history(self):
        facts=[dict(id='old',content='failure',tags=['open'],references=[]),
               dict(id='new',content='current',tags=['open'],references=[],supersedes='old')]
        self.assertEqual([f['id'] for f in digest(facts)['facts']],['new'])
        self.assertEqual(len(facts),2)

    def test_truncation_retries_only_same_phase_and_preserves_source(self):
        import json
        from unittest.mock import patch
        from intuition.llm import Client, TruncatedResponse
        client = Client(backend="mock"); client.max_calls = 2
        payload = json.dumps({"knowledge":{"facts":list(range(30))}, "files":{"a.py":"source"}})
        with patch.object(client, "_complete", side_effect=[TruncatedResponse(), {"ok":True}]) as request:
            self.assertEqual(client("PATCH.",payload,.2), {"ok":True})
            retried=json.loads(request.call_args.args[1])
            self.assertEqual(retried["files"], {"a.py":"source"})
            self.assertEqual(len(retried["knowledge"]["facts"]), 10)
            self.assertEqual(client.calls, 2)
        with patch.object(client, "_complete", side_effect=TruncatedResponse()) as request:
            client.calls=0
            with self.assertRaises(TruncatedResponse): client("PATCH.",payload,.2)
            self.assertEqual(request.call_count, 2)
            client.calls=1
            with self.assertRaises(TruncatedResponse): client("PATCH.",payload,.2)
            self.assertEqual(client.calls, 2)
