from __future__ import annotations
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[1]


def utc():
    return datetime.now(timezone.utc).isoformat()


def dump(path, value):
    path=Path(path); path.parent.mkdir(parents=True,exist_ok=True)
    temp=path.with_suffix(path.suffix+'.tmp')
    temp.write_text(json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False)+'\n')
    temp.replace(path)


def git(root, *args):
    r=subprocess.run(['git',*args],cwd=root,capture_output=True,text=True,timeout=30)
    if r.returncode: raise RuntimeError(f'git {args[0]} failed: '+r.stderr[-500:])
    return r.stdout.strip()


def sha(data):
    return hashlib.sha256(data if isinstance(data,bytes) else data.encode()).hexdigest()


def test(root, project, stage):
    env={k:v for k,v in os.environ.items() if k in ('PATH','LANG','SYSTEMROOT')}
    env['PYTHONDONTWRITEBYTECODE']='1'
    with tempfile.TemporaryDirectory(prefix='benchmark-test-home-') as home:
        env['HOME']=home
        try:
            r=subprocess.run([sys.executable,'-B',str(ROOT/'benchmark/evaluate.py'),str(root),project,str(stage)],
                             env=env,capture_output=True,text=True,timeout=20)
            if r.returncode: raise RuntimeError('Oracle process failed')
            return json.loads(r.stdout)
        except (subprocess.TimeoutExpired, ValueError, RuntimeError):
            return dict(passed=0,total=stage*3,green=False,failures=[{'id':'oracle','error':'Oracle failed or timed out'}])


def validate_edits(edits, originals):
    if not isinstance(edits,dict) or not edits or not set(edits)<=set(originals):
        raise ValueError('Empty edits or files outside allowlist')
    for name,content in edits.items():
        if not isinstance(content,str) or len(content.encode())>16000 or '\x00' in content:
            raise ValueError('Invalid or oversized source')
        compile(content,name,'exec')
    return {p:c for p,c in edits.items() if c!=originals[p]}


def source_snapshot():
    result={}
    for solution,folder in [('glm53','glm53/intuition'),('gpt6','gpt6/intuition_github'),('opus5','opus5/src/intuition'),('benchmark','benchmark')]:
        files=sorted((ROOT/folder).glob('*.py'))
        result[solution]={str(p.relative_to(ROOT)):sha(p.read_bytes()) for p in files}
    return result
