import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from benchmark.tests.test_adapters import SCRIPT
from benchmark.common import ROOT,git

class DevelopmentTests(unittest.TestCase):
    def test_native_strategies_promote_only_tested_source(self):
        for solution in ('glm53','gpt6','opus5'):
            with self.subTest(solution=solution),tempfile.TemporaryDirectory() as tmp:
                root=Path(tmp)/'repo';root.mkdir();(root/'src').mkdir();(root/'tests').mkdir()
                (root/'src/core.py').write_text('def discounted(amount, percent):\n    return amount\ndef taxed(amount, percent):\n    return amount\ndef money(value):\n    return str(value)\n')
                (root/'tests/test_core.py').write_text('import unittest\nfrom src.core import taxed\nclass Test(unittest.TestCase):\n def test_tax(self): self.assertEqual(taxed(100,20),120)\n')
                git(root,'init','-q');git(root,'config','user.name','Test');git(root,'config','user.email','test@localhost');git(root,'add','.');git(root,'commit','-qm','initial')
                start=git(root,'rev-parse','HEAD');dest=Path(tmp)/'result';dest.mkdir()
                project=dict(planfile_ticket='PLF-001',gitive_run='20260910T170000Z-abcdef',name='billing',path=str(root),goal='Repair billing calculations',test_argv=[sys.executable,'-m','unittest','discover','-s','tests'],allow='src')
                script=SCRIPT[:SCRIPT.index('from benchmark.worker import main')]+'''\nfrom gitive.develop import run\nresult=run(json.loads(sys.argv[2]),sys.argv[1],sys.argv[3])\nprint(json.dumps(result))\n'''
                p=subprocess.run([sys.executable,'-c',script,solution,json.dumps(project),str(dest)],cwd=ROOT,capture_output=True,text=True,timeout=100)
                self.assertEqual(p.returncode,0,p.stderr[-2000:]);result=json.loads(p.stdout.splitlines()[-1]);self.assertEqual(result['status'],'repaired',result)
                self.assertEqual(git(root,'diff',start,'--name-only'),'src/core.py')
                self.assertEqual(git(root,'rev-list','--count',start+'..HEAD'),'1')
                self.assertTrue(list((dest/'transcripts').glob('*.response.json')))

                events=[json.loads(line) for line in (dest/'operations.jsonl').read_text().splitlines()]
                operations={e['operation'] for e in events}
                self.assertTrue({'planning','coding','tests','validation','commit','merge'} <= operations,operations)
                native={'glm53':'glm53.core.choose','gpt6':'gpt6.llm.complete','opus5':'opus5.repair.repair'}[solution]
                self.assertIn(native,{e['function'] for e in events})
                self.assertTrue(all(e['project']=='billing' and e['ticket']=='PLF-001' and e['solution']==solution for e in events))
                self.assertEqual(events[-1]['status'],'finished')
                self.assertEqual(events[-1]['operation'],'idle')
                self.assertNotIn('benchmark-test-only',(dest/'operations.jsonl').read_text())
                self.assertNotIn('return amount',(dest/'operations.jsonl').read_text())



    def test_native_strategies_bind_planfile_ticket_title_to_commit_log(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "repo"; root.mkdir(); (root / "src").mkdir(); (root / "tests").mkdir()
            (root / "src/core.py").write_text("def discounted(amount, percent):\n    return amount\ndef taxed(amount, percent):\n    return amount\ndef money(value):\n    return str(value)\n")
            (root / "tests/test_core.py").write_text("import unittest\nfrom src.core import taxed\nclass Test(unittest.TestCase):\n def test_tax(self): self.assertEqual(taxed(100,20),120)\n")
            git(root, "init", "-q"); git(root, "config", "user.name", "Test"); git(root, "config", "user.email", "test@localhost"); git(root, "add", "."); git(root, "commit", "-qm", "initial")
            start = git(root, "rev-parse", "HEAD"); dest = Path(tmp) / "result"; dest.mkdir()
            project = dict(planfile_ticket="PLF-042", ticket_title="Tax rate computation", ticket_description="Add 20 percent tax", gitive_run="20260910T190000Z-abcdef", name="billing", path=str(root), goal="Repair billing calculations", test_argv=[sys.executable, "-m", "unittest", "discover", "-s", "tests"], allow="src")
            script = SCRIPT[:SCRIPT.index("from benchmark.worker import main")] + "\nfrom gitive.develop import run\nresult=run(json.loads(sys.argv[2]),sys.argv[1],sys.argv[3])\nprint(json.dumps(result))\n" 
            p = subprocess.run([sys.executable, "-c", script, "glm53", json.dumps(project), str(dest)], cwd=ROOT, capture_output=True, text=True, timeout=100)
            self.assertEqual(p.returncode, 0, p.stderr[-2000:])
            result = json.loads(p.stdout.splitlines()[-1])
            self.assertEqual(result["status"], "repaired", result)
            last_commit = git(root, "log", "-n", "1", "--format=%B")
            self.assertIn("PLF-042", last_commit)
            self.assertIn("Tax rate computation", last_commit)
