import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from gitive.engine import Engine,write
from gitive.projects import Projects
from gitive.jobs import run
class JobsTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.e=Engine(self.tmp.name,Path(self.tmp.name)/'data',hub=object())
        self.e.state=dict(kind='develop',project='demo',run='test',cycle=0,cycles=2,stop=False,spent_usd=0,max_usd=1,history=[])
        self.registry=Projects(self.e.root,self.e.data);write(self.registry.path,{'demo':{'name':'demo','copy_only':True}})
    def test_error_rebench_repair_test_reselect_resume(self):
        order=[];results=iter(['rejected','repaired']);choices=iter(['glm53','gpt6'])
        def command(argv,name,timeout):
            order.append(name)
            if name.endswith('development'):write(Path(argv[-1])/'result.json',{'status':next(results)})
        def bench(prefix):order.append(prefix);return {'solutions':{'glm53':{'final_tests_passed':37}}}
        with patch('gitive.jobs.winner',side_effect=lambda _:dict(solution=next(choices),report='benchmark/report')),patch.object(self.e,'command',side_effect=command),patch.object(self.e,'benchmark',side_effect=bench),patch.object(self.e,'codex',side_effect=lambda:order.append('codex')):
            run(self.e,self.registry)
        self.assertEqual(self.e.state['status'],'complete')
        self.assertEqual(order,['1-development','1-failure','codex','1-tests','1-after','2-development'])
        self.assertEqual(self.registry.all()['demo']['solution'],'gpt6')
    def test_codex_block_stops_before_retry(self):
        def command(argv,name,timeout):write(Path(argv[-1])/'result.json',{'status':'error'})
        with patch('gitive.jobs.winner',return_value={'solution':'glm53','report':'r'}),patch.object(self.e,'command',side_effect=command) as cmd,patch.object(self.e,'benchmark'),patch.object(self.e,'codex',side_effect=RuntimeError('Hub requires deployment')):
            run(self.e,self.registry)
        self.assertEqual(self.e.state['status'],'blocked');self.assertEqual(cmd.call_count,1)
