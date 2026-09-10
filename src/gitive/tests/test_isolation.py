import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import subprocess
from gitive.projects import Projects
from gitive.workspace import Workspace
from gitive.isolation import audit,copied

class IsolationTests(unittest.TestCase):
    def test_mount_audit_rejects_desktop_write_and_desktop_read_for_novnc(self):
        with tempfile.TemporaryDirectory() as tmp:
            private=Path(tmp)/'private';pc=Path(tmp)/'pc'
            container={'HostConfig':{'Privileged':False},'Mounts':[{'Type':'bind','Source':str(pc),'Destination':'/source/github','RW':True}]}
            with patch('gitive.isolation.inspect_container',return_value=container):
                with self.assertRaises(RuntimeError):audit('desktop',private)
                with self.assertRaises(RuntimeError):audit('app',private,True)
                container['Mounts'][0]['RW']=False
                audit('app',private,True)
                with self.assertRaises(RuntimeError):audit('desktop',private)
                container['Mounts'][0]['Source']=str(private/'github');container['Mounts'][0]['RW']=True
                audit('desktop',private)
    def test_project_registration_edits_only_copy(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);pc=root/'pc';pc.mkdir();source=pc/'repo';source.mkdir();(source/'file.py').write_text('original')
            subprocess.run(['git','init','-q',str(source)],check=True)
            private=root/'private';private.mkdir()
            with patch.dict(os.environ,{'GITIVE_SOURCE_ROOT':str(pc),'GITIVE_COPY_ROOT':str(private)}):
                registry=Projects(private/'controller',root/'data')
                row=registry.add('test-project',str(source),'goal',['python','test.py'])
            copy=Path(row['path'])/'file.py';self.assertTrue(row['copy_only'])
            self.assertNotEqual(copy.stat().st_ino,(source/'file.py').stat().st_ino)
            copy.write_text('agent change');self.assertEqual((source/'file.py').read_text(),'original')
    def test_host_copy_is_independent_and_never_overwrites(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);source=root/'original';source.write_text('one');target=root/'copy'
            copied(source,target);self.assertNotEqual(source.stat().st_ino,target.stat().st_ino)
            target.write_text('two');copied(source,target)
            self.assertEqual(source.read_text(),'one');self.assertEqual(target.read_text(),'two')
    def test_source_and_destination_are_separate_trees(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);pc=root/'pc';pc.mkdir();(pc/'repo').mkdir();copies=root/'copies';copies.mkdir()
            w=Workspace(copies/'controller',root/'data',workspace=copies,source_workspace=pc)
            self.assertEqual(w.source_path('repo'),pc/'repo')
            self.assertEqual(w.path('repo',False),copies/'repo')
            (copies/'escape').symlink_to(pc/'repo',target_is_directory=True)
            with self.assertRaises(ValueError):w.path('escape')

    def test_workspace_apply_does_not_write_pc(self):
        if not __import__('shutil').which('age'):self.skipTest('age required')
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);pc=root/'pc';pc.mkdir();source=pc/'repo';source.mkdir();copies=root/'copies';copies.mkdir()
            (source/'file.py').write_text('original');subprocess.run(['git','init','-q',str(source)],check=True)
            w=Workspace(copies/'controller',root/'data',workspace=copies,source_workspace=pc)
            clone=w.clone(w.snapshot('pc-test','repo')['id'],'repo-copy')['id']
            (source/'file.py').write_text('updated on PC')
            self.assertTrue(w.resync(clone,False)['applied'])
            (copies/'repo-copy/file.py').write_text('agent edit')
            self.assertFalse(w.resync(clone,False)['applied'])
            self.assertEqual((source/'file.py').read_text(),'updated on PC')
