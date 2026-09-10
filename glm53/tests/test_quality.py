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
