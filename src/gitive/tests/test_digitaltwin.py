from pathlib import Path
import tempfile
import unittest
from gitive.digitaltwin import inventory,normalize_roots,local_path,DigitalTwin
from gitive.engine import write

class DigitalTwinTests(unittest.TestCase):
    def test_full_inventory_includes_env_venv_and_node_modules_without_values(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            for name in ['.env','.venv/lib/test.py','node_modules/package/index.js']:
                target=root/name;target.parent.mkdir(parents=True,exist_ok=True);target.write_text('opaque-value')
            (root/'external').symlink_to('/unmounted/runtime')
            result=inventory(root)
            self.assertIn('.env',result['files']);self.assertIn('.venv/lib/test.py',result['files'])
            self.assertNotIn('opaque-value',str(result));self.assertEqual(result['files']['external']['link'],'/unmounted/runtime')
    def test_overlapping_roots_are_copied_once(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);(root/'sub').mkdir()
            self.assertEqual(normalize_roots([root,root/'sub']),[root])
            with self.assertRaises(ValueError):normalize_roots(['/'])
    def test_private_project_mapping_rejects_escape(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ValueError):local_path('/home/tom/github/project',Path(tmp))
            with self.assertRaises(ValueError):local_path('/workspace/github/../../etc',Path(tmp))
    def test_catalog_has_no_runtime_until_provisioned(self):
        with tempfile.TemporaryDirectory() as tmp:
            twin=DigitalTwin(tmp);write(twin.projects,{'demo':{'name':'demo','copy_only':True}})
            self.assertEqual(twin.status('demo')['status'],'not-provisioned')
    def test_incomplete_catalog_is_not_ready_and_can_recover_without_deleting_copy(self):
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as tmp:
            twin=DigitalTwin(tmp);root=Path(tmp)/'github/.digitaltwin/demo-123';root.mkdir(parents=True)
            old={'name':'demo','copy_only':True,'path':'/workspace/github/projects/demo'}
            workspace={'id':'demo-123','project':'demo','root':str(root),'container':'owned','path_in_app':'/workspace/github/.digitaltwin/new'}
            write(twin.projects,{'demo':{**old,'path':workspace['path_in_app']}})
            write(twin.catalog,{'twins':{'pc':{'projects':['demo']}},'workspaces':{'demo':workspace}})
            write(twin.data/'catalog-backups/demo-123/projects.json',{'demo':old})
            write(root/'operation.json',{'status':'verified-awaiting-registry'})
            with self.assertRaisesRegex(ValueError,'Incomplete'):twin.status('demo')
            with patch.object(twin,'audit_container'),patch('gitive.digitaltwin.command'):
                self.assertEqual(twin.recover('demo')['status'],'recovered')
            self.assertEqual(twin.record('demo')['path'],old['path']);self.assertTrue(root.exists())
    def test_extension_never_removes_a_container_when_launch_did_not_succeed(self):
        from unittest.mock import patch
        import shutil
        with tempfile.TemporaryDirectory() as tmp:
            base=Path(tmp)/'base';base.mkdir();source=Path(tmp)/'dependency';source.mkdir();(source/'file').write_text('data')
            twin=DigitalTwin(base);root=base/'github/.digitaltwin/demo';root.mkdir(parents=True)
            workspace={'project':'demo','container':'owned','container_status':'running','root':str(root),'source_inventories':{'/project':{}},'image_id':'image'}
            calls=[]
            def command(argv,**kwargs):
                calls.append(argv)
                if argv[0]=='cp':shutil.copytree(argv[-2],argv[-1])
                return ''
            with patch.object(twin,'status',return_value=workspace),patch.object(twin,'launch',side_effect=RuntimeError('name collision')),patch('gitive.digitaltwin.command',side_effect=command),patch('gitive.digitaltwin.subprocess.run') as raw:
                with self.assertRaises(RuntimeError):twin.extend('demo',[source])
            raw.assert_not_called()
            self.assertTrue((root/'rootfs'/source.relative_to('/')/'file').exists())
