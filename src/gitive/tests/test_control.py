import json
import os
from pathlib import Path
import tempfile
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from gitive.control import action,dashboard
from gitive.engine import write
from gitive.host import consume,perform
from gitive.planfile_bridge import PlanfileBridge

class ControlTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);self.data=self.root/'data';self.data.mkdir()
        self.engine=SimpleNamespace(data=self.data,root=self.root,state={})
        self.env=patch.dict(os.environ,{'GITIVE_COPY_ROOT':str(self.root/'copies')});self.env.start();self.addCleanup(self.env.stop)
        projects={}
        for name in ('alpha','beta'):
            path=self.root/'copies'/name;path.mkdir(parents=True)
            projects[name]={'path':str(path),'copy_only':True,'workspace_ref':name,'test_argv':['python3','-m','unittest'],'source_path':f'/source/github/semcod/{name}'}
            PlanfileBridge(path).ensure('demo','Ticket '+name,'gpt6')
        write(self.data/'projects.json',projects)
        write(self.data/'runtime-host.json',{'at':time.time(),'workspaces':{'alpha':{'status':'running'}}})
        write(self.data/'digitaltwins.json',{'workspaces':{'alpha':{'id':'alpha','python':{'version':'3.12'},'verification':{'project_tests':{'status':'passed','log':'PRIVATE LOG PATH','exit_code':0}}}}})
    def test_dashboard_scopes_tickets_and_redacts_private_log_path(self):
        with patch('gitive.control.winner',side_effect=RuntimeError('no ranking')):value=dashboard(self.engine)
        self.assertEqual({(t['project'],t['id']) for t in value['tickets']},{('alpha','PLF-001'),('beta','PLF-001')})
        self.assertEqual(value['projects'][0]['repository'],'semcod/alpha')
        self.assertNotIn('PRIVATE LOG PATH',str(value));self.assertEqual(value['projects'][0]['workspace']['status'],'running')
        write(self.data/'runtime-host.json',{'at':time.time()-30})
        with patch('gitive.control.winner',side_effect=RuntimeError('no ranking')):value=dashboard(self.engine)
        self.assertFalse(value['host_online']);self.assertEqual(value['projects'][0]['workspace']['status'],'unknown')
    def test_mutations_only_change_selected_project_and_preserve_markup_as_text(self):
        action(self.engine,{'action':'update-ticket','project':'alpha','ticket':'PLF-001','status':'done'})
        self.assertEqual(PlanfileBridge(self.root/'copies/beta').store.get_ticket('PLF-001').status.value,'open')
        with self.assertRaisesRegex(ValueError,'Zakończony'):action(self.engine,{'action':'run-ticket','project':'alpha','ticket':'PLF-001'})
        result=action(self.engine,{'action':'create-ticket','project':'beta','title':'<script>alert(1)</script>','engine':'opus5','parent':'PLF-001'})
        self.assertEqual(result['parent'],'PLF-001');self.assertEqual(result['title'],'<script>alert(1)</script>')
        self.assertIsNone(PlanfileBridge(self.root/'copies/alpha').store.get_ticket(result['id']))
    def test_queue_rejects_duplicates_unknown_actions_and_offline_host(self):
        body={'action':'runtime-test','project':'alpha'}
        job=action(self.engine,body);self.assertEqual(job['status'],'queued')
        with self.assertRaisesRegex(ValueError,'kolejce'):action(self.engine,body)
        self.assertEqual(action(self.engine,{**body,'project':'beta'})['status'],'queued')
        with self.assertRaises(ValueError):action(self.engine,{**body,'action':'shell'})
        write(self.data/'runtime-host.json',{'at':0})
        with self.assertRaisesRegex(ValueError,'offline'):action(self.engine,body)
    def test_worker_does_not_replay_finished_job_and_records_test_failure(self):
        path=self.data/'job.json';write(path,{'action':'runtime-test','project':'alpha','status':'queued'})
        twin=SimpleNamespace()
        with patch('gitive.host.perform',return_value={'status':'failed','exit_code':1}) as perform_call:
            consume(twin,path);consume(twin,path)
        perform_call.assert_called_once();self.assertEqual(json.loads(path.read_text())['status'],'failed')
    def test_worker_ignores_request_argv_uses_registered_test_and_rejects_arbitrary_effect(self):
        from unittest.mock import Mock
        twin=Mock();twin.data=self.data;twin.record.return_value={'test_argv':['python3','-m','unittest']};twin.execute.return_value={'status':'passed','exit_code':0,'created':'now','log':'private'}
        result=perform(twin,{'project':'alpha','action':'runtime-test','argv':['sh','-c','bad']})
        twin.execute.assert_called_once_with('alpha',['python3','-m','unittest'],test=True);self.assertNotIn('log',result)
        with self.assertRaisesRegex(ValueError,'Niedozwolona'):perform(twin,{'project':'alpha','action':'arbitrary'})
    def test_private_copy_escape_is_rejected(self):
        rows=json.loads((self.data/'projects.json').read_text());rows['alpha']['path']=str(self.root);write(self.data/'projects.json',rows)
        with self.assertRaisesRegex(ValueError,'prywatnej'):action(self.engine,{'action':'runtime-test','project':'alpha'})

    def test_remote_ticket_routes_to_matching_project_repository(self):
        res=action(self.engine,{
            'action':'import-remote-ticket',
            'project':'alpha',
            'repository':'semcod/beta',
            'number':42,
            'title':'Feature for beta',
            'description':'Target beta'
        })
        self.assertEqual(res['project'],'beta')
        self.assertIsNotNone(PlanfileBridge(self.root/'copies/beta').store.get_ticket(res['id']))
        self.assertIsNone(PlanfileBridge(self.root/'copies/alpha').store.get_ticket(res['id']))

    def test_remote_ticket_rejects_unregistered_repository(self):
        with self.assertRaisesRegex(ValueError,'Ticket wskazuje unknown/repo'):
            action(self.engine,{
                'action':'import-remote-ticket',
                'project':'alpha',
                'repository':'unknown/repo',
                'number':99,
                'title':'Feature for unknown',
                'description':'Target unknown'
            })

    def test_http_token_required_and_status_persists_through_api(self):
        import threading
        import urllib.request
        import urllib.error
        from http.server import ThreadingHTTPServer
        from gitive import server
        self.engine.lock=threading.RLock()
        with patch.object(server,'engine',self.engine),patch.object(server,'workspace',SimpleNamespace(state={})),patch('gitive.control.winner',side_effect=RuntimeError('no ranking')):
            http=ThreadingHTTPServer(('127.0.0.1',0),server.Handler)
            thread=threading.Thread(target=http.serve_forever,daemon=True);thread.start()
            try:
                url='http://127.0.0.1:'+str(http.server_port)
                value=json.load(urllib.request.urlopen(url+'/api/control'))
                self.assertEqual(len(value['tickets']),2)
                body=json.dumps({'action':'update-ticket','project':'beta','ticket':'PLF-001','status':'review'}).encode()
                with self.assertRaises(urllib.error.HTTPError) as caught:urllib.request.urlopen(urllib.request.Request(url+'/api/control/action',data=body))
                self.assertEqual(caught.exception.code,403)
                result=json.load(urllib.request.urlopen(urllib.request.Request(url+'/api/control/action',data=body,headers={'X-Loop-Token':server.TOKEN})))
                self.assertEqual((result['project'],result['status']),('beta','review'))
                self.assertEqual(PlanfileBridge(self.root/'copies/alpha').store.get_ticket('PLF-001').status.value,'open')
            finally:http.shutdown();http.server_close();thread.join()
    def test_run_ticket_routes_to_matching_project_repository(self):
        alpha_bridge=PlanfileBridge(self.root/'copies/alpha')
        t=alpha_bridge.ensure('target-beta','Fix for Beta — semcod/beta','gpt6','Source: https://github.com/semcod/beta/blob/main/mod.py')
        with patch('gitive.jobs.start',return_value={'ok':True,'routed':'beta'}) as mock_start:
            action(self.engine,{
                'action':'run-ticket',
                'project':'alpha',
                'ticket':t.id
            })
            mock_start.assert_called_once()
            args,kwargs=mock_start.call_args
            self.assertEqual(kwargs.get('name'),'beta')
            self.assertEqual(kwargs.get('kind'),'develop')

    def test_run_ticket_locates_ticket_in_correct_project_if_wrong_project_selected(self):
        beta_bridge=PlanfileBridge(self.root/'copies/beta')
        t=beta_bridge.ensure('beta-only','Specific to Beta','gpt6')
        with patch('gitive.jobs.start',return_value={'ok':True}) as mock_start:
            action(self.engine,{
                'action':'run-ticket',
                'project':'alpha',
                'ticket':t.id
            })
            mock_start.assert_called_once()
            args,kwargs=mock_start.call_args
            self.assertEqual(kwargs.get('name'),'beta')
            self.assertEqual(kwargs.get('ticket_id'),t.id)

    def test_run_ticket_rejects_unregistered_repository(self):
        alpha_bridge=PlanfileBridge(self.root/'copies/alpha')
        t=alpha_bridge.ensure('target-unknown','Fix for Unknown — external/unknown','gpt6','Source: https://github.com/external/unknown/blob/main/mod.py')
        with self.assertRaisesRegex(ValueError,'Ticket wskazuje external/unknown'):
            action(self.engine,{
                'action':'run-ticket',
                'project':'alpha',
                'ticket':t.id
            })
    def test_run_ticket_does_not_hijack_unrelated_ticket_with_same_id(self):
        alpha_bridge=PlanfileBridge(self.root/'copies/alpha')
        beta_bridge=PlanfileBridge(self.root/'copies/beta')
        t_beta_unrelated=beta_bridge.ensure('unrelated','Unrelated beta task','gpt6')
        # In alpha, create a ticket that targets beta, having distinct source line
        t_alpha=alpha_bridge.ensure('target-beta','Doctor fix — semcod/beta','gpt6',
            "<!-- planfile:deduplication-key=k1 -->\n"
            "Source: https://github.com/semcod/beta/blob/main/mod.py#L10")
        # Even if t_beta_unrelated.id happens to be the same string as t_alpha.id in another test scenario:
        with patch('gitive.jobs.start',return_value={'ok':True}) as mock_start:
            action(self.engine,{
                'action':'run-ticket',
                'project':'alpha',
                'ticket':t_alpha.id
            })
            mock_start.assert_called_once()
            args,kwargs=mock_start.call_args
            self.assertEqual(kwargs.get('name'),'beta')
            routed_id=kwargs.get('ticket_id')
            routed_t=beta_bridge.store.get_ticket(routed_id)
            self.assertIn('Doctor fix',routed_t.name)
            self.assertNotEqual(routed_t.name,'Unrelated beta task')

    def test_develop_prioritizes_ticket_target_file(self):
        from gitive.runtime_develop import _files
        import tempfile, subprocess
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            subprocess.run(['git', 'init'], cwd=root, check=True, capture_output=True)
            subprocess.run(['git', 'config', 'user.name', 'test'], cwd=root, check=True)
            subprocess.run(['git', 'config', 'user.email', 'test@example.com'], cwd=root, check=True)
            (root/'src').mkdir()
            for i in range(20):
                (root/'src'/f'file_{i:02d}.py').write_text(f'# {i}')
            (root/'src'/'target_module.py').write_text('# target')
            subprocess.run(['git', 'add', '.'], cwd=root, check=True)
            subprocess.run(['git', 'commit', '-m', 'init'], cwd=root, check=True)
            # When goal mentions target_module.py, it must be the first file in code dict
            code = _files(root, 'src', 'Fix issue in src/target_module.py')
            self.assertIn('src/target_module.py', code)
            self.assertEqual(list(code.keys())[0], 'src/target_module.py')

