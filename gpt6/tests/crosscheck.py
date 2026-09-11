"""Development comparison; deployment needs only ONE selected language."""
from __future__ import annotations
import json
import math
import random
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
PY=[sys.executable]


def typescript_runtime():
    node_path=shutil.which('node') or ''
    if node_path:
        try:
            out=subprocess.run([node_path,'-v'],capture_output=True,text=True,timeout=5).stdout
            m=re.search(r'v(\d+)',out)
            if m and int(m.group(1))>=22:return ['node','--experimental-strip-types']
        except Exception:
            pass
        versions=re.findall(r'(?:^|[/\\])v(\d+)(?:[./\\]|$)',node_path)
        if versions and int(versions[-1])>=22:return ['node','--experimental-strip-types']
    if shutil.which('tsx'):return ['tsx']
    if shutil.which('npx'):return ['npx','--yes','tsx@4.23.13']
    raise RuntimeError('GPT6 cross-check requires Node 22+ or tsx (npx is also supported)')


NODE=typescript_runtime()

def command(args, data=None):
    result=subprocess.run(args,input=data,stdout=subprocess.PIPE,stderr=subprocess.PIPE,cwd=ROOT,timeout=30)
    if result.returncode:
        raise RuntimeError(f'{args}: {result.stderr.decode()}')
    return json.loads(result.stdout)

def load(name):return json.loads((ROOT/'examples'/name).read_text())

def close(a,b):
    if isinstance(a,(int,float)) and not isinstance(a,bool):
        assert isinstance(b,(int,float)) and math.isclose(a,b,rel_tol=1e-12,abs_tol=1e-12),(a,b)
    elif isinstance(a,dict):
        assert set(a)==set(b)
        for k in a:close(a[k],b[k])
    elif isinstance(a,list):
        assert len(a)==len(b)
        for av,bv in zip(a,b):close(av,bv)
    else:assert a==b,(a,b)

def cli_scenario(runtime,script):
    cli=runtime+[str(ROOT/script)]
    with tempfile.TemporaryDirectory() as tmp:
        repo=str(Path(tmp)/'memory.git')
        command(cli+['init',repo,str(ROOT/'examples/state.json')])
        request=command(cli+['prompt',repo])
        reply=Path(tmp)/'reply.json'
        reply.write_text(json.dumps({'base_commit':request['base_commit'],'tasks':load('tasks.json')}))
        decision=command(cli+['plan',repo,str(reply)])
        assert decision['selected']['task']['id']=='T1'
        # A proposal produced for the old snapshot must be rejected.
        bad=subprocess.run(cli+['plan',repo,str(reply)],capture_output=True,timeout=30)
        assert bad.returncode==2
        event=Path(tmp)/'event.json'
        event.write_text(json.dumps({'base_commit':decision['commit'],'event':load('event.json')}))
        observation=command(cli+['observe',repo,str(event),str(ROOT/'examples/evidence.txt')])
        assert math.isclose(observation['hypotheses']['H1'],27/29)
        request2=command(cli+['prompt',repo])
        reply.write_text(json.dumps({'base_commit':request2['base_commit'],'tasks':load('tasks.json')}))
        decision2=command(cli+['plan',repo,str(reply)])
        assert decision2['selected']['task']['id']=='T2'
        count=subprocess.check_output(['git','-C',repo,'rev-list','--count','refs/heads/memory'],text=True).strip()
        assert count=='4'
        return {'first':decision['selected']['task']['id'],'second':decision2['selected']['task']['id'],
                'posterior':observation['hypotheses']['H1'],'commits':int(count),'stale_reply_rejected':True}

def main():
    rng=random.Random(20260910)
    cases=[[rng.random(),rng.random(),rng.random()] for _ in range(1000)]
    x={'state':load('state.json'),'tasks':load('tasks.json'),'cases':cases}
    data=json.dumps(x).encode()
    a=command(PY+[str(ROOT/'python/probe.py')],data)
    b=command(NODE+[str(ROOT/'typescript/probe.ts')],data)
    close(a,b)
    p=cli_scenario(PY,'python/cli.py')
    t=cli_scenario(NODE,'typescript/cli.ts')
    close(p,t)
    print(json.dumps({'numeric_cases':len(cases),'tolerance':1e-12,'cross_language_equal':True,
                      'max_information_gain_difference':max(abs(x-y) for x,y in zip(a['gains'],b['gains'])),
                      'python_cli':p,'typescript_cli':t,
                      'initial_scores':{v['task']['id']:v['score'] for v in a['ranking']['ranking']}},indent=2))
if __name__=='__main__':main()
