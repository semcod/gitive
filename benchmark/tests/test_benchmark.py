import tempfile
from pathlib import Path
import unittest
from benchmark.fixtures import PROJECTS
from benchmark.common import test as oracle,validate_edits
from benchmark.report import summarize
from benchmark.common import dump


class BenchmarkTests(unittest.TestCase):
    def test_fixtures_have_failures_in_every_stage(self):
        for name,spec in PROJECTS.items():
            with tempfile.TemporaryDirectory() as tmp:
                root=Path(tmp); (root/'src').mkdir(); (root/'src/core.py').write_text(spec['source'])
                for stage in (1,2,3):
                    result=oracle(root,name,stage)
                    self.assertEqual(result['total'],sum(c[0]<=stage for c in spec['cases']))
                    self.assertFalse(result['green'])
                    self.assertTrue(any(x['stage']==stage for x in result['failures']))

    def test_oracle_rejects_syntax_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); (root/'src').mkdir(); (root/'src/core.py').write_text('def broken(')
            result=oracle(root,'invoice_math',3)
            self.assertEqual(result['passed'],0)
            self.assertEqual(result['total'],len(PROJECTS['invoice_math']['cases']))

    def test_oracle_rejects_decimal_even_when_value_matches(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); (root/'src').mkdir()
            source=PROJECTS['invoice_math']['source'].replace('return amount + percent',
                "return Decimal(str(amount)) * (1 + Decimal(str(percent))/100)")
            (root/'src/core.py').write_text(source)
            result=oracle(root,'invoice_math',3)
            self.assertTrue(any('Numeric API' in f['error'] for f in result['failures']))

    def test_scope_and_syntax_gate(self):
        with self.assertRaises(ValueError): validate_edits({'../escape':'pass'},{'src/core.py':'pass'})
        with self.assertRaises(SyntaxError): validate_edits({'src/core.py':'def ('},{'src/core.py':'pass'})
        self.assertEqual(validate_edits({'src/core.py':'pass'},{'src/core.py':'pass'}),{})

    def test_report_does_not_count_mock_as_repair(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); (root/'iterations').mkdir(); (root/'final').mkdir()
            dump(root/'manifest.json',dict(run_id='test',mode='mock',solutions=['glm53'],projects=['invoice_math'],iterations=1,started='2026-09-10',model='mock',git_head='abc'))
            dump(root/'iterations/x.json',dict(solution='glm53',project='invoice_math',iteration=1,status='mock_no_repair',accepted=False,seconds=1,after={'passed':1,'total':3,'green':False},llm_calls=[]))
            summary=summarize(root)
            self.assertEqual(summary['solutions']['glm53']['accepted'],0)
            self.assertEqual(summary['solutions']['glm53']['llm_calls'],0)
            self.assertIsNone(summary['solutions']['glm53']['cost_usd'])


if __name__=='__main__': unittest.main()
