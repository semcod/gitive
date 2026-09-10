"""Exercise native adapter contracts with a fake SDK response, never a provider call."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from benchmark.common import ROOT

SCRIPT=r'''
import json,sys,os
os.environ["OPENROUTER_API_KEY"]="benchmark-test-only"
os.environ["LLM_MODEL"]="openrouter/z-ai/glm-5.3"
import litellm
from pathlib import Path
fixed="""from decimal import Decimal, ROUND_HALF_UP

def discounted(amount, percent):
    return amount * (1 - percent / 100)

def taxed(amount, percent):
    return amount * (1 + percent / 100)

def money(value):
    return str(Decimal(str(value)).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP))
"""
def fake(*args,**kwargs):
    system=kwargs['messages'][0]['content']; user=kwargs['messages'][1]['content']
    if 'You propose evidence-backed' in system:
        data=json.loads(user)
        if data['purpose']=='propose_tasks':
            assert set(data)=={'purpose','goal','base_sha','output_contract','profiles','untrusted_facts','untrusted_source_files','existing_tasks'}
            body={'base_sha':data['base_sha'],'tasks':[{'title':'Fix billing functions','profile':'repair','fact_ids':[data['untrusted_facts'][-1]['id']],
                  'target_files':['src/core.py'],'acceptance':['Pass failing tests'],'rationale':'Observed failures'}]}
        else:
            assert data['purpose']=='propose_patch'
            assert set(data)=={'purpose','base_sha','output_contract','task','untrusted_facts','untrusted_files','max_changed_lines'}
            body={'base_sha':data['base_sha'],'summary':'Fix billing','edits':[{'path':'src/core.py','old_sha256':data['untrusted_files'][0]['sha256'],'content':fixed}]}
    elif 'PROPOSE.' in system:
        data=json.loads(user)
        body=[{'archetype':'verify','prompt':'Fix src/core.py billing tests','references':[data['knowledge']['facts'][-1]['id']],'rationale':'Failing tests'}]
    elif 'proposing concrete refactoring' in system:
        body=[{'title':'Fix billing functions','body':'Repair src/core.py to pass billing tests','cost':1,'files':['src/core.py'],'rationale':'Observed failures'}]
    else:
        body={'files':[{'path':'src/core.py','content':fixed}]}
    return litellm.ModelResponse(choices=[{'finish_reason':'stop','message':{'role':'assistant','content':json.dumps(body)}}],usage={'prompt_tokens':0,'completion_tokens':0,'total_tokens':0})
litellm.completion=fake
from benchmark.worker import main
sys.argv=['worker','--solution',sys.argv[1],'--project','invoice_math','--iterations','3','--run-dir',sys.argv[2],'--work-dir',sys.argv[3]]
main()
'''


class AdapterTests(unittest.TestCase):
    def test_native_contracts_and_feedback(self):
        for solution in ('glm53','gpt6','opus5'):
            with self.subTest(solution=solution),tempfile.TemporaryDirectory() as tmp:
                root=Path(tmp); run=root/'run'; run.mkdir()
                result=subprocess.run([sys.executable,'-c',SCRIPT,solution,str(run),str(root/'work')],cwd=ROOT,capture_output=True,text=True,timeout=60)
                self.assertEqual(result.returncode,0,result.stderr[-1500:])
                rows=[json.loads(p.read_text()) for p in sorted((run/'iterations').glob('*.json'))]
                self.assertEqual(len(rows),3)
                self.assertEqual(rows[0]['status'],'repaired',rows[0])
                self.assertNotIn('feedback_error',rows[0])
                self.assertTrue(rows[-1]['full_after']['green'])
                self.assertEqual(rows[1]['status'],'already_green')

    def test_real_worker_rejects_a_regressing_patch(self):
        broken_script=SCRIPT.replace('return amount * (1 + percent / 100)', 'return amount + 1')
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); run=root/'run'; run.mkdir()
            result=subprocess.run([sys.executable,'-c',broken_script,'glm53',str(run),str(root/'work')],cwd=ROOT,capture_output=True,text=True,timeout=60)
            self.assertEqual(result.returncode,0,result.stderr[-1500:])
            first=json.loads((run/'iterations/glm53--invoice_math--1.json').read_text())
            self.assertEqual(first['status'],'rejected')
            self.assertFalse(first['accepted'])
            self.assertTrue(first['regressions'])
            self.assertEqual(first['source_before'],first['source_after'])
