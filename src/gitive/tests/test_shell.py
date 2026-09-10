import contextlib
import io
import unittest
from unittest.mock import Mock
from gitive.shell import ContextShell


class ShellTests(unittest.TestCase):
    def setUp(self):
        self.output = io.StringIO()
        self.redirect = contextlib.redirect_stdout(self.output)
        self.redirect.__enter__(); self.addCleanup(self.redirect.__exit__, None, None, None)
        self.row = dict(id='PLF-001', title='Integration', status='done', executor='glm53',
                        created='2026-09-10 17:15:00 CEST', github=dict(id=407, url='https://github.com/subactor/doctor-agent/issues/407', repository='subactor/doctor-agent'))
        self.operation = dict(operation='idle', events=[])
        def api(path, **kwargs):
            if path == '/api/projects': return {'doctor-agent': {'status': 'registered'}}
            if path == '/api/state': return {'project': 'other'}
            return self.operation
        self.dispatch = Mock()
        self.shell = ContextShell(Mock(side_effect=api), self.dispatch, lambda _: [self.row],
                           lambda: [{'label':'Projects', 'argv':['project','open']}], lambda s,*_:s, Mock())
        self.shell.username = 'tom'

    def select(self):
        for command in ('menu', '1', '1', '1', '1'): self.shell.onecmd(command)

    def test_numbered_path_persists_project_and_ticket(self):
        self.select()
        self.assertEqual(self.shell.prompt, 'tom/doctor-agent/PLF-001/idle> ')
        self.assertIn('GitHub #407', self.output.getvalue())
        self.assertIn('2026-09-10 17:15:00 CEST', self.output.getvalue())
        self.assertIn('nie import wszystkich', self.output.getvalue())
        self.shell.onecmd('back')
        self.assertEqual(self.shell.prompt, 'tom/doctor-agent/-/idle> ')
        self.shell.onecmd('back')
        self.assertEqual(self.shell.prompt, 'tom/-/-/idle> ')

    def test_live_operation_refresh_offline_and_run_binding(self):
        self.select()
        self.operation = dict(operation='coding', function='glm53.llm.__call__', pid=123)
        self.shell.refresh()
        self.assertTrue(self.shell.prompt.endswith('/coding> '))
        self.shell.onecmd('run')
        self.dispatch.assert_called_with(['tickets','run','doctor-agent','--ticket','PLF-001'])
        self.shell.api.side_effect = OSError('offline')
        self.shell.refresh()
        self.assertTrue(self.shell.prompt.endswith('/offline> '))

    def test_sync_uses_selected_binding_without_id_input(self):
        self.select(); self.shell.onecmd('sync pull')
        self.dispatch.assert_called_with(['tickets','sync','doctor-agent','--ticket','PLF-001',
                                         '--direction','pull','--repo','subactor/doctor-agent'])

    def test_other_project_stop_and_bad_menu_never_dispatch(self):
        self.select(); self.shell.onecmd('stop'); self.shell.onecmd('99')
        self.dispatch.assert_not_called()
        self.assertIn('nie dotyczy tego projektu', self.output.getvalue())

    def test_prompt_and_ticket_labels_cannot_inject_terminal_controls(self):
        self.row['title'] = 'bad\x1b[2J\ncontent'
        self.shell.username = '\x1b[2J/user'
        self.select()
        self.assertNotIn('\x1b', self.output.getvalue())
        self.assertNotIn('\x1b', self.shell.prompt)
        self.assertEqual(self.shell.prompt.count('/'), 3)



class LivePromptTests(unittest.TestCase):
    def test_operation_redraw_preserves_partially_typed_command(self):
        import importlib.util
        import os
        import pty
        import select
        import subprocess
        import sys
        import tempfile
        import time
        if importlib.util.find_spec('prompt_toolkit') is None:
            self.skipTest('prompt-toolkit required for live TTY')
        with tempfile.TemporaryDirectory() as temp:
            flag=os.path.join(temp,'coding')
            code="""
import os,sys
from gitive.shell import ContextShell
row=dict(id='PLF-001',title='Live fixture',status='in_progress',executor='glm53',created='test',github={})
def api(path,**kwargs):
    return dict(operation='coding' if os.path.exists(sys.argv[1]) else 'idle',events=[])
shell=ContextShell(api,lambda args:None,lambda project:[row],lambda:[],lambda value,*args:value,lambda:None)
shell.username='tester';shell.project='demo';shell.ticket=row
shell.cmdloop()
"""
            master,slave=pty.openpty()
            process=subprocess.Popen([sys.executable,'-u','-c',code,flag],stdin=slave,stdout=slave,stderr=slave,
                                     env={**os.environ,'TERM':'xterm-256color','PROMPT_TOOLKIT_NO_CPR':'1'})
            os.close(slave)
            def until(needle):
                output=b'';deadline=time.monotonic()+10
                while needle not in output and time.monotonic()<deadline:
                    if select.select([master],[],[],.1)[0]: output+=os.read(master,65536)
                self.assertIn(needle,output)
            try:
                until(b'/idle>')
                os.write(master,b'sta')
                open(flag,'w').close()
                until(b'coding>')
                os.write(master,b'tus\n')
                until(b'Planfile: PLF-001')
                os.write(master,b'exit\n')
                process.wait(timeout=10)
                self.assertEqual(process.returncode,0)
            finally:
                if process.poll() is None:process.kill();process.wait()
                os.close(master)
