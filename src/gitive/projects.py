"""Persistent project registry and reproducible benchmark winner selection."""
import hashlib
import os
import uuid
import json
from pathlib import Path
import re
import subprocess
from .engine import write

SOLUTIONS=('glm53','gpt6','opus5')
def winner(root):
    root=Path(root)
    for folder in sorted((root/'benchmark/runs').glob('*'),reverse=True):
        try:
            m=json.loads((folder/'manifest.json').read_text());s=json.loads((folder/'summary.json').read_text())
            if m.get('mode')!='live' or m.get('methodology_status')=='pilot' or m.get('execution_version')!=3:continue
            if set(m['solutions'])!=set(SOLUTIONS) or set(m['projects'])!={'invoice_math','url_router','job_queue'} or m['iterations']!=3:continue
            if s['completed_iterations']!=27 or any(x not in s['solutions'] for x in SOLUTIONS):continue
            hashes=m['source_hashes']
            folders={'glm53':'glm53/intuition','gpt6':'gpt6/intuition_github','opus5':'opus5/src/intuition','benchmark':'benchmark'}
            if any(set(hashes[n])!={str(p.relative_to(root)) for p in (root/folder).glob('*.py')} for n,folder in folders.items()):continue
            if any(hashlib.sha256((root/p).read_bytes()).hexdigest()!=h for name in (*SOLUTIONS,'benchmark') for p,h in hashes[name].items()):continue
            metrics=s['solutions']
            if any(metrics[x]['final_tests_total']!=37 for x in SOLUTIONS):continue
            def rank(x):
                v=metrics[x]
                return (-v['final_tests_passed'],-v['final_green_projects'],-v['green_stages'],
                        v['errors'],v['regressions'],v['cost_usd'] if v.get('cost_usd') is not None else float('inf'),x)
            order=sorted(SOLUTIONS,key=rank)
            return {'solution':order[0],'ranking':order,'report':str(folder.relative_to(root)),
                    'metrics':metrics,'criterion':'tests, green projects, green stages, errors, regressions, cost'}
        except (KeyError,ValueError,OSError,TypeError):continue
    raise RuntimeError('Brak aktualnego wspólnego benchmarku live v3. Uruchom: gitive benchmark')

class Projects:
    def __init__(self, root, data):
        self.root=Path(root);self.path=Path(data)/'projects.json'
    def all(self):return json.loads(self.path.read_text()) if self.path.exists() else {}
    def add(self,name,path,goal,test_argv,allow='src'):
        if not re.fullmatch(r'[a-z][a-z0-9-]{1,40}',name):raise ValueError('Nazwa: 2–41 małych liter/cyfr/myślników')
        path=Path(path).resolve()
        sources=Path(os.getenv('GITIVE_SOURCE_ROOT','/source/github')).resolve()
        workspace=Path(os.getenv('GITIVE_COPY_ROOT','/workspace/github')).resolve()
        if not path.is_relative_to(sources) or path==sources:raise ValueError('Wybierz źródłowy projekt PC')
        check=subprocess.run(['git','rev-parse','--show-toplevel'],cwd=path,text=True,capture_output=True)
        if check.returncode or Path(check.stdout.strip())!=path:raise ValueError('Wymagany główny katalog repo Git')
        if not isinstance(goal,str) or not goal.strip() or len(goal)>4000:raise ValueError('Podaj cel projektu')
        if not isinstance(test_argv,list) or not test_argv or any(not isinstance(x,str) or not x for x in test_argv):raise ValueError('Test musi być listą argumentów')
        if not re.fullmatch(r'[A-Za-z0-9_/-]+',allow) or '..' in allow.split('/') or allow.startswith('/'):raise ValueError('Niepoprawny zakres źródeł')
        records=self.all()
        if name in records:raise ValueError('Projekt jest już zarejestrowany')
        from .workspace import files,copy
        if not (path/'.git').is_dir():raise ValueError('Import wymaga lokalnego katalogu .git')
        if (path/'.git/objects/info/alternates').exists():raise ValueError('Repo korzysta z zewnętrznych obiektów Git')
        destination=workspace/'projects'/name
        if destination.exists():raise ValueError('Kopia już istnieje; nie nadpisano jej')
        destination.parent.mkdir(parents=True,exist_ok=True)
        import tempfile
        with tempfile.TemporaryDirectory(dir=destination.parent,prefix='.import-') as tmp:
            stage=Path(tmp)/'project';before=files(path);copy(path,stage)
            if before!=files(path) or before!=files(stage):raise RuntimeError('Źródło zmieniło się podczas kopiowania')
            stage.rename(destination)
        records[name]={'name':name,'path':str(destination),'source_path':str(path),'copy_only':True,'goal':goal.strip(),'test_argv':test_argv,'allow':allow,'status':'registered'}
        write(self.path,records);return records[name]
    def result(self,name,value):
        rows=self.all();rows[name].update(value);write(self.path,rows)
