#!/usr/bin/env python3
"""Post-hoc checks of final code; never alter original benchmark scores."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
CASES={
'invoice_math': [('discounted',[80,25],60),('taxed',[80,25],100),('money',['0.005'],'0.01')],
'url_router': [('matches',['/api/users','/api/'],True),('query_value',['na%6De=abc','name'],'abc'),('query_value',['q=a%2Bb','q'],'a+b')],
'job_queue': [('ordered',[[{'id':'a','priority':-2},{'id':'b','priority':-1}]],['b','a']),
              ('may_retry',[1,2],True),('unique',[[{'tenant':'a','id':1,'value':'first'},{'tenant':'a','id':1,'value':'second'}]],[{'tenant':'a','id':1,'value':'first'}])]
}
CHECKER='''import json
import core
cases=json.load(open('cases.json'))
results=[]
for name,args,expected in cases:
 try:
  actual=getattr(core,name)(*args)
  ok=actual==expected
  try:
   json.dumps(actual)
   serializable=True
  except TypeError:
   serializable=False
  results.append(dict(function=name,args=args,expected=expected,actual=actual,actual_type=type(actual).__name__,json_serializable=serializable,passed=ok))
 except Exception as e:
  results.append(dict(function=name,args=args,expected=expected,passed=False,error=type(e).__name__))
print(json.dumps(results,default=str))
'''

def check(run):
 results=[]
 for solution in ['glm53','gpt6','opus5']:
  for project,cases in CASES.items():
   source=json.loads((run/'final'/f'{solution}--{project}.json').read_text())['code']
   with tempfile.TemporaryDirectory() as temp:
    root=Path(temp); (root/'core.py').write_text(source); (root/'check.py').write_text(CHECKER)
    (root/'cases.json').write_text(json.dumps(cases))
    env={'PATH':os.environ.get('PATH',''),'HOME':str(root),'PYTHONDONTWRITEBYTECODE':'1'}
    p=subprocess.run([sys.executable,'-B','check.py'],cwd=root,env=env,capture_output=True,text=True,timeout=20,check=True)
    rows=json.loads(p.stdout)
    results.append(dict(solution=solution,project=project,passed=sum(x['passed'] for x in rows),total=len(rows),cases=rows))
 output={'kind':'post-hoc supplemental cases','note':'Cases added after inspecting one solution. Not a preregistered independent ranking; original scores unchanged. Encoded query parameter names and trailing-slash prefixes require explicit acceptance coverage.', 'results':results}
 (run/'edge-case-audit.json').write_text(json.dumps(output,indent=2))
 return output

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('run',type=Path);args=p.parse_args()
 print(json.dumps(check(args.run),indent=2))
