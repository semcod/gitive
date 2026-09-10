import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from gitive.projects import winner,SOLUTIONS
from gitive.engine import write
class RankingTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name)
        hashes={}
        for name in (*SOLUTIONS,'benchmark'):
            folder={'glm53':'glm53/intuition','gpt6':'gpt6/intuition_github','opus5':'opus5/src/intuition','benchmark':'benchmark'}[name]
            p=self.root/folder/'core.py';p.parent.mkdir(exist_ok=True,parents=True);p.write_text('# source')
            hashes[name]={str(p.relative_to(self.root)):hashlib.sha256(p.read_bytes()).hexdigest()}
        self.folder=self.root/'benchmark/runs/20260101'
        self.m={'mode':'live','execution_version':3,'solutions':list(SOLUTIONS),'projects':['invoice_math','url_router','job_queue'],'iterations':3,'source_hashes':hashes}
        self.s={'completed_iterations':27,'solutions':{n:dict(final_tests_total=37,final_tests_passed=37,final_green_projects=3,green_stages=9,errors=0,regressions=0,cost_usd=i+1) for i,n in enumerate(SOLUTIONS)}}
        self.save()
    def save(self):write(self.folder/'manifest.json',self.m);write(self.folder/'summary.json',self.s)
    def test_tie_uses_cost(self):self.assertEqual(winner(self.root)['solution'],'glm53')
    def test_quality_before_cost(self):
        self.s['solutions']['glm53']['final_tests_passed']=36;self.save();self.assertEqual(winner(self.root)['solution'],'gpt6')
    def test_reject_mock_pilot_partial_stale(self):
        for key,value in [('mode','mock'),('methodology_status','pilot'),('iterations',2)]:
            with self.subTest(key=key):
                old=dict(self.m);self.m[key]=value;self.save()
                with self.assertRaises(RuntimeError):winner(self.root)
                self.m=old
        self.save();(self.root/'gpt6/intuition_github/core.py').write_text('# changed')
        with self.assertRaises(RuntimeError):winner(self.root)
