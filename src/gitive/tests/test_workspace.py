import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import Mock
from gitive.workspace import Workspace,files

@unittest.skipUnless(shutil.which('age'),'age required')
class WorkspaceTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.base=Path(self.tmp.name)
        self.root=self.base/'github';self.root.mkdir();self.project=self.root/'source';self.project.mkdir()
        self.home=self.base/'home';self.home.mkdir();(self.home/'.codex').mkdir();(self.home/'.codex/history.jsonl').write_text('test history')
        (self.project/'module.py').write_text('value=1\n');(self.project/'untracked.txt').write_text('unsaved to git')
        subprocess.run(['git','init','-q',str(self.project)],check=True)
        self.hub=Mock();self.w=Workspace(self.root/'controller',self.base/'data',self.hub,self.root,self.home)
    def snapshot(self,**kw):return self.w.snapshot('test-pc','source',**kw)['id']
    def test_encrypted_clone_preserves_untracked_and_offline_history(self):
        (self.project/'module.py').chmod(0o664)
        sid=self.snapshot(include_sessions=True)
        archive=(self.w.data/sid/'payload.tar.age').read_bytes();self.assertTrue(archive.startswith(b'age-encryption.org'));self.assertNotIn(b'test history',archive)
        clone=self.w.clone(sid,'copy');self.assertEqual(files(self.project),files(self.root/'copy'))
        self.assertEqual((self.w.data/('restored-home-'+clone['id'])/'.codex/history.jsonl').read_text(),'test history')
        self.assertEqual((self.home/'.codex/history.jsonl').read_text(),'test history')
        with self.assertRaises(ValueError):self.w.clone(sid,'copy')
    def test_resync_dry_run_apply_and_conflict(self):
        clone=self.w.clone(self.snapshot(),'copy')['id'];(self.project/'module.py').write_text('value=2\n')
        self.assertFalse(self.w.resync(clone)['applied']);self.assertIn('value=1',(self.root/'copy/module.py').read_text())
        result=self.w.resync(clone,False);self.assertTrue(result['applied']);self.assertTrue((self.root/result['backup']).is_dir())
        (self.root/'copy/module.py').write_text('local change');(self.project/'module.py').write_text('value=3\n')
        result=self.w.resync(clone,False);self.assertFalse(result['applied']);self.assertEqual(result['conflict_count'],1)
        self.assertEqual((self.root/'copy/module.py').read_text(),'local change')
    def test_tamper_and_path_escape_rejected(self):
        sid=self.snapshot();(self.w.data/sid/'payload.tar.age').write_bytes(b'bad')
        with self.assertRaises(ValueError):self.w.clone(sid,'copy')
        with self.assertRaises(ValueError):self.w.path('../escape')
        (self.project/'escape').symlink_to('/etc/passwd')
        with self.assertRaises(ValueError):files(self.project)
    def test_resume_uses_hub_not_shell(self):
        clone=self.w.clone(self.snapshot(),'copy')['id'];self.hub.call.return_value={'status':'launched'}
        self.w.resume(clone,'terminal')
        self.assertEqual(self.hub.call.call_args.args[1]['project'],'copy')
        with self.assertRaises(ValueError):self.w.resume(clone,'bash -c anything')
    def test_resume_does_not_open_archive_for_provisioned_project(self):
        from gitive.engine import write
        clone=self.w.clone(self.snapshot(),'copy')['id']
        record=json.loads((self.w.data/'clones'/f'{clone}.json').read_text())
        write(self.w.data.parent/'projects.json',{'demo':{'workspace_ref':'ready','source_path':str(Path('/source/github')/record['source'])}})
        with self.assertRaisesRegex(ValueError,'twin terminal demo'):self.w.resume(clone,'terminal')
        self.hub.call.assert_not_called()
    def test_profile_receipt_binds_restore(self):
        self.hub.call.return_value={'snapshot_path':'/hub/snapshots/one.tar.gz','status':'ok'}
        profile=self.w.profile('snapshot','firefox');self.w.profile('restore',snapshot=profile['id'])
        self.assertEqual(self.hub.call.call_args.args[1]['snapshot_path'],'/hub/snapshots/one.tar.gz')
    def test_pc_browser_profile_restores_offline_only(self):
        p=self.home/'.mozilla/firefox/default';p.mkdir(parents=True);(p/'prefs.js').write_text('// example')
        clone=self.w.clone(self.snapshot(browser='firefox'),'copy')
        self.assertTrue((self.w.data/('restored-home-'+clone['id'])/'.mozilla/firefox/default/prefs.js').is_file())
        self.hub.call.assert_not_called()
    def test_resync_offline_sessions_and_conflicts(self):
        clone=self.w.clone(self.snapshot(include_sessions=True),'copy')['id']
        source=self.home/'.codex/history.jsonl';target=self.w.data/('restored-home-'+clone)/'.codex/history.jsonl'
        source.write_text('new history')
        plan=self.w.resync(clone,True,True);self.assertIn('sessions/.codex/history.jsonl',plan['changes']);self.assertFalse(plan['applied'])
        self.assertTrue(self.w.resync(clone,False,True)['applied']);self.assertEqual(target.read_text(),'new history')
        target.write_text('local conversation');source.write_text('another conversation')
        self.assertEqual(self.w.resync(clone,False,True)['conflict_count'],1)
        self.assertEqual(target.read_text(),'local conversation')
    def test_inventory_adapter_never_exports_token(self):
        (self.home/'.codex/auth.json').write_text('{"OPENAI_API_KEY":"sk-proj-test-do-not-export-123456789"}')
        result=self.w.inventory();content=(self.w.data/result['report']).read_text()
        self.assertNotIn('sk-proj-test-do-not-export-123456789',content)

    def test_snap_firefox_resync_and_active_codex_exclusion(self):
        profile=self.home/'snap/firefox/common/.mozilla/firefox'
        profile.mkdir(parents=True)
        (profile/'profiles.ini').write_text('[Profile0]\nName=default\n')
        w=Workspace(self.root/'controller',self.base/'data2',self.hub,self.root,self.home)
        snapshot=w.snapshot('snap','source',browser='firefox',include_sessions=True,exclude_sessions=['.codex'])
        clone=w.clone(snapshot['id'],'snap-copy')
        self.assertNotIn('.codex',clone['session_paths'])
        self.assertIn('snap/firefox/common/.mozilla/firefox',clone['session_paths'])
        self.assertFalse(w.resync(clone['id'],include_sessions=True)['applied'])
