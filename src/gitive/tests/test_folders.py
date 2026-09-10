from pathlib import Path
import subprocess
import tempfile
import unittest
from gitive.folders import browse
class FolderTests(unittest.TestCase):
    def test_nested_navigation_and_git_root(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);repo=root/'owner'/'my project';repo.mkdir(parents=True)
            subprocess.run(['git','init','-q',str(repo)],check=True)
            (repo/'src').mkdir()
            self.assertEqual(browse('',root)['folders'],[{'name':'owner','path':'owner'}])
            self.assertFalse(browse('owner',root)['is_repo'])
            self.assertTrue(browse('owner/my project',root)['is_repo'])
            self.assertFalse(browse('owner/my project/src',root)['is_repo'])
            self.assertEqual(browse('owner/my project',root)['parent'],'owner')
    def test_cannot_escape_workspace(self):
        with tempfile.TemporaryDirectory() as tmp,tempfile.TemporaryDirectory() as outside:
            root=Path(tmp);(root/'escape').symlink_to(outside,target_is_directory=True)
            (root/'.hidden').mkdir()
            self.assertEqual(browse('',root)['folders'],[])
            for path in ('../','escape',outside):
                with self.subTest(path=path),self.assertRaises(ValueError):browse(path,root)
