import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from gitive.engine import Engine,write
from gitive.projects import Projects
from gitive.jobs import run,validate_ticket_target,ticket_requires_human_review
class JobsTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.e=Engine(self.tmp.name,Path(self.tmp.name)/'data',hub=object())
        self.e.state=dict(kind='develop',project='demo',run='test',cycle=0,cycles=2,stop=False,spent_usd=0,max_usd=1,history=[])
        self.registry=Projects(self.e.root,self.e.data);write(self.registry.path,{'demo':{'name':'demo','path':self.tmp.name,'goal':'Test jobs','copy_only':True}})
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
    def test_requested_ticket_is_executed_without_creating_another(self):
        from gitive.planfile_bridge import PlanfileBridge
        bridge=PlanfileBridge(self.tmp.name);ticket=bridge.ensure('manual','Specific task','opus5','Acceptance condition')
        self.e.state['requested_ticket']=ticket.id
        def command(argv,name,timeout):
            project=json.loads(Path(argv[-3]).read_text())
            self.assertIn('Specific task',project['goal']);self.assertIn('Acceptance condition',project['goal'])
            write(Path(argv[-1])/'result.json',{'status':'repaired'})
        with patch('gitive.jobs.winner',side_effect=AssertionError('Do not replace assigned executor')),patch.object(self.e,'command',side_effect=command):run(self.e,self.registry)
        self.assertEqual(self.e.state['status'],'complete')
        self.assertEqual(self.e.state['ticket_id'],ticket.id)
        self.assertEqual(len(bridge.store.list_tickets(sprint='gitive')),1)
        self.assertEqual(bridge.store.get_ticket(ticket.id).status.value,'in_progress')
        self.assertEqual(bridge.store.get_ticket(ticket.id).execution.state,'done')
        self.assertTrue(bridge.store.get_ticket(ticket.id).source.context['last_execution']['result_path'].endswith('/result.json'))
    def test_ticket_citing_another_repository_is_rejected(self):
        from gitive.planfile_bridge import PlanfileBridge
        bridge=PlanfileBridge(self.tmp.name)
        ticket=bridge.ensure('remote','[Doctor] review — semcod/planfile','glm53',
            'Source: https://github.com/semcod/planfile/blob/main/planfile/sync/github.py')
        project={'source_path':'/source/github/subactor/doctor-agent'}
        with self.assertRaisesRegex(ValueError,'semcod/planfile'):
            validate_ticket_target(project,ticket)

    def test_review_only_ticket_is_rejected_before_execution(self):
        from gitive.jobs import start
        from gitive.planfile_bridge import PlanfileBridge
        bridge=PlanfileBridge(self.tmp.name)
        ticket=bridge.ensure('review-only','Diagnostic finding','glm53',
            'Assessment: review_required. This is a diagnostic review request, not repair authorization.')
        self.assertTrue(ticket_requires_human_review(ticket))
        with self.assertRaisesRegex(ValueError,'nie autoryzuje naprawy'):
            start(self.e,kind='develop',name='demo',ticket_id=ticket.id)
        current=bridge.store.get_ticket(ticket.id)
        self.assertEqual(current.status.value,'open')
        self.assertIsNone(current.execution)

    def test_normal_ticket_is_not_review_only(self):
        from gitive.planfile_bridge import PlanfileBridge
        bridge=PlanfileBridge(self.tmp.name)
        ticket=bridge.ensure('normal','Repair bug','glm53','Add a regression test and fix the bug.')
        self.assertFalse(ticket_requires_human_review(ticket))

    def test_project_runtime_uses_runtime_worker_without_host_fallback(self):
        from gitive.jobs import start
        rows=self.registry.all();rows['demo']['workspace_ref']='private-runtime';write(self.registry.path,rows)
        def command(argv,name,timeout):
            self.assertIn('runtime_develop.py',argv[1])
            write(Path(argv[-1])/'result.json',{'status':'already_green'})
        with patch('gitive.digitaltwin.DigitalTwin.status',return_value={'container_status':'running'}),patch('gitive.jobs.winner',return_value={'solution':'gpt6','report':'r'}),patch.object(self.e,'command',side_effect=command):
            start(self.e,kind='develop',name='demo',cycles=1)
            self.e.thread.join(2)
        self.assertEqual(self.e.state['status'],'complete')
    def test_start_auto_routes_to_matching_registered_project(self):
        from gitive.jobs import start
        from gitive.planfile_bridge import PlanfileBridge
        other_path = Path(self.tmp.name) / 'other'; other_path.mkdir(parents=True)
        rows = self.registry.all()
        rows['demo']['source_path'] = '/source/github/semcod/demo'
        rows['other'] = {'name': 'other', 'path': str(other_path), 'copy_only': True, 'test_argv': ['true'], 'source_path': '/source/github/semcod/other'}
        write(self.registry.path, rows)
        bridge = PlanfileBridge(self.tmp.name)
        ticket = bridge.ensure('target-other', 'Task — semcod/other', 'glm53', 'Source: https://github.com/semcod/other/blob/main/test.py')
        def command(argv, name, timeout):
            write(Path(argv[-1]) / 'result.json', {'status': 'repaired'})
        with patch('gitive.jobs.winner', return_value={'solution': 'glm53', 'report': 'r'}), patch.object(self.e, 'command', side_effect=command):
            start(self.e, kind='develop', name='demo', ticket_id=ticket.id, cycles=1)
            self.e.thread.join(2)
        self.assertEqual(self.e.state['status'], 'complete')
        self.assertEqual(self.e.state['project'], 'other')

    def test_start_workspace_ref_uses_runtime_host_status(self):
        from gitive.jobs import start
        rows=self.registry.all();rows['demo']['workspace_ref']='dt-demo';write(self.registry.path,rows)
        import time
        write(self.e.data/'runtime-host.json',{'at':time.time(),'workspaces':{'demo':{'status':'running'}}})
        def command(argv,name,timeout):
            write(Path(argv[-1])/'result.json',{'status':'already_green'})
        with patch('gitive.jobs.winner',return_value={'solution':'gpt6','report':'r'}),patch.object(self.e,'command',side_effect=command):
            start(self.e,kind='develop',name='demo',cycles=1)
            self.e.thread.join(2)
        self.assertEqual(self.e.state['status'],'complete')
