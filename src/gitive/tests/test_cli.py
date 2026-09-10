import contextlib
import io
import unittest
from unittest.mock import patch
from gitive.cli import main

class ResyncCliTests(unittest.TestCase):
    def invoke(self,args,clones,tty=False,answer='1'):
        calls=[]
        def request(path,body=None):
            calls.append((path,body))
            return {'clones':clones} if body is None else {'status':'running'}
        with patch('gitive.cli.request',side_effect=request),patch('gitive.cli.sys.stdin.isatty',return_value=tty),patch('builtins.input',return_value=answer),contextlib.redirect_stdout(io.StringIO()),contextlib.redirect_stderr(io.StringIO()):
            main(['workspace','resync',*args])
        return calls
    def test_single_clone_defaults_to_preview(self):
        calls=self.invoke([], [{'id':'a','source':'org/repo','target':'copies/repo'}])
        self.assertEqual(calls[-1][1],{'operation':'resync','clone':'a','include_sessions':False,'dry_run':True})
    def test_explicit_id_skips_discovery(self):
        calls=self.invoke(['abc','--apply','--include-sessions'],[])
        self.assertEqual(len(calls),1)
        self.assertEqual(calls[0][1],{'operation':'resync','clone':'abc','include_sessions':True,'dry_run':False})
    def test_multiple_clones_require_choice(self):
        clones=[{'id':n,'source':'org/'+n,'target':'copies/'+n} for n in ('a','b')]
        with self.assertRaisesRegex(ValueError,'CLONE_ID'):self.invoke([],clones)
        self.assertEqual(self.invoke([],clones,True,'2')[-1][1]['clone'],'b')
        with self.assertRaises(ValueError):self.invoke([],clones,True,'0')
    def test_no_clone_does_not_start_operation(self):
        with self.assertRaisesRegex(ValueError,'Brak kopii'):self.invoke([],[])
    def test_status_is_short_and_json_is_explicit(self):
        import json
        state={'status':'complete','operation':'snapshot','result':{'id':'example','sessions':[],'archive_sha256':'hidden-digest'}}
        for flags in ([],['--json']):
            output=io.StringIO()
            with patch('gitive.cli.request',return_value=state),contextlib.redirect_stdout(output):main(['workspace','status',*flags])
            if flags:self.assertEqual(json.loads(output.getvalue()),state)
            else:
                self.assertNotIn('hidden-digest',output.getvalue())
                self.assertIn('przeglądarki nie skopiowano',output.getvalue())
                self.assertLessEqual(len(output.getvalue().splitlines()),5)
    def test_clone_selection_uses_date_without_displaying_id(self):
        row={'id':'opaque-id','project':'org/project','created':'20260910T120000Z','sessions':[]}
        calls=[];out=io.StringIO()
        def request(path,body=None):
            calls.append(body)
            return {'snapshots':[row]} if body is None else {'status':'running'}
        with patch('gitive.cli.request',side_effect=request),patch('gitive.cli.sys.stdin.isatty',return_value=True),patch('builtins.input',return_value='copies/project'),contextlib.redirect_stdout(io.StringIO()),contextlib.redirect_stderr(out):
            main(['workspace','clone'])
        self.assertIn('2026-09-10 14:00:00',out.getvalue())
        self.assertNotIn('opaque-id',out.getvalue())
        self.assertEqual(calls[-1],{'operation':'clone','snapshot':'opaque-id','target':'copies/project'})
