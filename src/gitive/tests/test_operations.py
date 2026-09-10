import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
from gitive.operations import Operations, current


class OperationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.run = '20260910T170000Z-abcdef'
        self.ops = Operations(self.root/self.run/'develop-1', 'demo', 'PLF-001', 'glm53', self.run, self.root)
        self.state = dict(project='demo',ticket_id='PLF-001',selection={'solution':'glm53'},run=self.run,
                          cycle=1,status='running',process=dict(pid=os.getpid(),status='running'))

    def read(self, project='demo', ticket='PLF-001'):
        return current(self.root, self.state, project, ticket)

    def test_bound_live_process_and_foreign_ticket(self):
        self.ops.emit('coding','glm53.llm.__call__')
        self.assertEqual(self.read()['operation'],'coding')
        self.assertEqual(self.read('other')['operation'],'idle')
        self.assertEqual(self.read(ticket='PLF-002')['events'],[])
        self.state['selection']['solution']='gpt6'
        self.assertEqual(self.read()['operation'],'unknown')

    def test_stale_pid_restart_and_finish_do_not_show_running_operation(self):
        self.ops.emit('commit','benchmark.common.git')
        with patch('gitive.operations.os.kill',side_effect=ProcessLookupError):
            self.assertEqual(self.read()['operation'],'unknown')
        self.state['status']='interrupted'
        self.assertEqual(self.read()['operation'],'interrupted')
        self.state['status']='complete'
        self.assertEqual(self.read()['operation'],'idle')
        self.assertEqual(self.read()['events'][-1]['operation'],'commit')

    def test_nested_native_call_failure_restores_parent_and_profiler(self):
        original=sys.getprofile()
        # A small real Python frame at an exact recognized native source path.
        namespace={}
        exec(compile('def choose():\n raise ValueError("private-token")',self.ops.native+'core.py','exec'),namespace)
        with self.ops.observe(), self.ops.stage('repair','gitive.develop'):
            with self.assertRaises(ValueError): namespace['choose']()
            self.assertEqual(self.read()['operation'],'repair')
        self.assertIs(sys.getprofile(),original)
        self.assertEqual(self.read()['operation'],'idle')
        raw=(self.ops.folder/'operations.jsonl').read_text()
        self.assertNotIn('private-token',raw)
        self.assertIn('glm53.core.choose',raw)
        self.assertEqual((self.ops.folder/'operation.json').stat().st_mode & 0o777,0o600)

    def test_bad_or_partial_event_and_run_path_fail_closed(self):
        self.ops.emit('coding','glm53.llm.__call__')
        (self.ops.folder/'operation.json').write_text('{')
        self.assertEqual(self.read()['operation'],'unknown')
        self.state['run']='../../somewhere'
        self.assertEqual(self.read()['operation'],'unknown')
