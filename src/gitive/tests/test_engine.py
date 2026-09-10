import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from gitive.engine import Engine, write, permitted
from gitive.hub import Hub

class EngineTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.engine=Engine(Path(self.tmp.name),Path(self.tmp.name)/'data',hub=object())
    def test_restart_does_not_replay_uncertain_execution(self):
        write(self.engine.path,{'status':'running','phase':'codex'})
        e=Engine(self.engine.root,self.engine.data)
        self.assertEqual(e.state['status'],'interrupted')
    def test_cycle_order_and_baseline_reuse(self):
        calls=[]
        e=self.engine
        def bench(prefix):
            calls.append(prefix); e.state['spent_usd']+=.1; e.state['report']='test-report'
            return {'solutions':{'glm53':{'final_tests_passed':37}}}
        with patch.object(e,'benchmark',side_effect=bench),patch.object(e,'codex',return_value={}),patch.object(e,'command'):
            e.start(cycles=2); e.thread.join(5)
        self.assertEqual(e.state['status'],'complete')
        self.assertEqual(calls,['1-before','1-after','2-after'])
    def test_test_failure_stops_before_rebenchmark(self):
        e=self.engine
        with patch.object(e,'benchmark',return_value={'solutions':{}}) as bench,patch.object(e,'codex',return_value={}),patch.object(e,'command',side_effect=RuntimeError('tests failed')):
            e.start(cycles=2);e.thread.join(5)
        self.assertEqual(e.state['status'],'blocked');self.assertEqual(bench.call_count,1)
    def test_regression_blocks_next_cycle(self):
        e=self.engine
        with patch.object(e,'benchmark',side_effect=[{'solutions':{'x':{'final_tests_passed':37}}},{'solutions':{'x':{'final_tests_passed':36}}}]),patch.object(e,'codex',return_value={}),patch.object(e,'command'):
            e.start(cycles=2);e.thread.join(5)
        self.assertEqual(e.state['status'],'blocked')
    def test_scope(self):
        self.assertTrue(permitted('glm53/intuition/core.py'))
        self.assertFalse(permitted('benchmark/fixtures.py'))
        self.assertFalse(permitted('gpt6/tests_github/test_contracts.py'))
    def test_invalid_limits(self):
        for value in (-1,21,True):
            with self.assertRaises(ValueError): self.engine.start(cycles=value)
    def test_hub_plan_is_bound_to_execute_and_authority(self):
        h=Hub(); calls=[]
        request={'execution_id':'e','valid_until':'time','plan_hash':'hash','dsl':{}}
        plan={'authorization':{'issue_grant':{'resource':'r'},'start_intent':{'plan_ref':'sha256:hash'}}}
        with patch.object(h,'call',side_effect=lambda path,body:calls.append((path,body)) or {'result':{'ok':True}}): h.execute(request,plan)
        self.assertEqual([c[0] for c in calls],['/v1/grants/issue','/v1/intents/start','/v1/cli/executions/apply'])
        self.assertEqual(calls[-1][1]['plan_hash'],'hash')
        self.assertEqual(calls[0][1]['grant_id'],calls[-1][1]['grant_id'])
    def test_codex_report_matches_actual_changes(self):
        e=self.engine
        e.state={'run':'fixture','cycle':1,'report':'benchmark/runs/fixture','demo':False}
        report=e.root/'.subactor/recovery/loop-app/fixture/1-analysis.json'
        class FakeHub:
            def plan(self,prompt): return {'execution_id':'fixture'},{}
            def execute(self,request,plan):
                write(report,{'summary':'Fixed source','findings':['Report evidence'],
                    'changed_files':['glm53/intuition/core.py'],'limitations':[]})
                return {'result':{'ok':True}}
        e.hub=FakeHub()
        with patch('gitive.engine.source_snapshot',side_effect=[{'glm53/intuition/core.py':'a'},{'glm53/intuition/core.py':'b'}]),patch('gitive.engine.subprocess.check_output',return_value=b'head'):
            self.assertEqual(e.codex()['changed'],['glm53/intuition/core.py'])
        with patch('gitive.engine.source_snapshot',side_effect=[{'benchmark/fixtures.py':'a'},{'benchmark/fixtures.py':'b'}]),patch('gitive.engine.subprocess.check_output',return_value=b'head'):
            with self.assertRaisesRegex(RuntimeError,'zakresem'):e.codex()
