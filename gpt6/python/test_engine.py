from __future__ import annotations
import copy
import json
import math
import tempfile
import unittest
from pathlib import Path
from engine import entropy, information_gain, posterior, rank, accept_plan, observe, Task
from gitstore import initialize, read, commit, git, REF

ROOT = Path(__file__).resolve().parents[1]

def fixtures():
    return tuple(json.loads((ROOT/'examples'/name).read_text()) for name in ('state.json','tasks.json','event.json'))

class EngineTests(unittest.TestCase):
    def setUp(self): self.state, self.tasks, self.event = fixtures()
    def pending(self): return accept_plan(self.state,rank(self.state,self.tasks))
    def test_entropy(self):
        self.assertEqual(entropy(0),0);self.assertEqual(entropy(1),0);self.assertEqual(entropy(.5),1)
    def test_perfect_test(self):
        self.assertAlmostEqual(information_gain(.6,1,0),entropy(.6))
    def test_useless_test(self): self.assertAlmostEqual(information_gain(.6,.8,.8),0)
    def test_bayes(self):
        self.assertAlmostEqual(posterior(.6,.9,.1,True),27/29)
        self.assertAlmostEqual(posterior(.6,.9,.1,False),1/7)
    def test_invalid_numbers(self):
        for p in (True,math.nan,math.inf,-.1,1.1):
            with self.assertRaises(ValueError): entropy(p)
    def test_impossible(self):
        with self.assertRaises(ValueError): posterior(0,1,0,True)
    def test_information_bounds(self):
        for p in (0,.1,.5,.9,1):
            for s in (0,.1,.5,.9,1):
                for f in (0,.1,.5,.9,1):
                    ig=information_gain(p,s,f)
                    self.assertGreaterEqual(ig,-1e-12);self.assertLessEqual(ig,entropy(p)+1e-12)
    def test_ranking(self):
        result=rank(self.state,self.tasks)
        self.assertEqual([v['task']['id'] for v in result['ranking']],['T1','T3','T2'])
        self.assertAlmostEqual(result['ranking'][-1]['score'],.102)
    def test_input_not_mutated(self):
        before=copy.deepcopy(self.state); rank(self.state,self.tasks); observe(self.pending(),self.event,b'evidence')
        self.assertEqual(before,self.state)
    def test_positive_observation_changes_decision(self):
        state=observe(self.pending(),self.event,b'evidence')
        self.assertAlmostEqual(state['hypotheses']['H1'],27/29)
        self.assertEqual(state['profiles']['diagnose_cache']['alpha'],10)
        self.assertEqual(rank(state,self.tasks)['selected']['task']['id'],'T2')
        self.assertAlmostEqual(state['budget'],2.88)
    def test_failure_not_false_hypothesis(self):
        event={**self.event,'success':False,'positive':None}
        state=observe(self.pending(),event,b'evidence')
        self.assertEqual(state['hypotheses']['H1'],.6)
        self.assertEqual(state['profiles']['diagnose_cache']['beta'],2)
        task={**self.tasks[1],'depends_on':['T1']}
        self.assertEqual(rank(state,[task])['rejected'][0]['reason'],'blocked')
    def test_unknown_fact(self):
        self.tasks[0]['facts']=['invented']
        with self.assertRaises(ValueError):rank(self.state,self.tasks)
    def test_injected_score_or_command(self):
        for key in ('score','command'):
            t={**self.tasks[0],key:999}
            with self.assertRaises(ValueError):rank(self.state,[t])
    def test_duplicate_ids(self):
        with self.assertRaises(ValueError):rank(self.state,[self.tasks[0],self.tasks[0]])
    def test_cycle(self):
        self.tasks[0]['depends_on']=['T2'];self.tasks[1]['depends_on']=['T1']
        with self.assertRaises(ValueError):rank(self.state,self.tasks)
    def test_unknown_dependency(self):
        self.tasks[0]['depends_on']=['unknown']
        with self.assertRaises(ValueError):rank(self.state,self.tasks)
    def test_policy_budget_stop(self):
        self.state['profiles']['diagnose_cache']['allowed']=False
        self.state['budget']=0
        result=rank(self.state,self.tasks)
        self.assertIsNone(result['selected'])
        self.assertEqual({r['reason'] for r in result['rejected']},{'policy','budget'})
    def test_risk_gate(self):
        self.state['profiles']['diagnose_cache']['risk']=.3
        self.assertEqual(rank(self.state,self.tasks)['rejected'][0]['reason'],'policy')
    def test_threshold(self):
        self.state['min_score']=1
        self.assertIsNone(rank(self.state,self.tasks)['selected'])
    def test_duplicate_paraphrase(self):
        t={**self.tasks[0],'id':'T4','title':'Different wording'}
        result=rank(self.state,[self.tasks[0],t]);self.assertEqual(len(result['ranking']),1)
        self.assertEqual(result['rejected'][0]['reason'],'duplicate')
    def test_reuse_evidence(self):
        state=observe(self.pending(),self.event,b'evidence')
        state=accept_plan(state,rank(state,self.tasks))
        event={**self.event,'event_id':'E2','task_id':'T2','positive':None}
        with self.assertRaises(ValueError):observe(state,event,b'evidence')
    def test_pending_rejects_new_plan(self):
        with self.assertRaises(ValueError):rank(self.pending(),self.tasks)
    def test_empty_candidates(self): self.assertIsNone(rank(self.state,[])['selected'])
    def test_unicode_key(self):
        self.assertEqual(Task.parse(self.tasks[0]).key('Cel: pamięć 🧠'), '691e1e1f11152dbc278a9b4fba9bda502169720afa49b3f8557abacec25b3d51')
    def test_git_roundtrip_and_stale_writer(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo=Path(tmp)/'memory.git';base=initialize(repo,self.state)
            self.assertEqual(read(repo),(base,self.state))
            updated=self.pending();new=commit(repo,base,updated,{'kind':'plan'})
            self.assertEqual(read(repo),(new,updated))
            with self.assertRaises(RuntimeError):commit(repo,base,self.state,{'kind':'stale'})
            self.assertEqual(read(repo)[0],new)
            self.assertEqual(git(repo,'rev-list','--count',REF).decode().strip(),'2')
            git(repo,'fsck','--no-reflogs')

if __name__=='__main__':unittest.main()
