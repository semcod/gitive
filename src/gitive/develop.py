"""One selected native strategy in a disposable clone; apply only a tested fast-forward."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
ROOT=Path(__file__).resolve().parents[2]
# In the image, repository modules are on the mounted workspace.
ROOT=Path(os.getenv('PROJECT_ROOT',str(ROOT)))
sys.path.insert(0,str(ROOT))
from benchmark.common import git, validate_edits
from benchmark.adapters import ADAPTERS
from dotenv import load_dotenv


def tests(root,argv):
    env={k:v for k,v in os.environ.items() if k in ('PATH','LANG','SYSTEMROOT')}
    env.update(PYTHONDONTWRITEBYTECODE='1',GIT_CONFIG_GLOBAL=os.devnull,GIT_CONFIG_NOSYSTEM='1')
    with tempfile.TemporaryDirectory() as home:
        env['HOME']=home
        try:
            p=subprocess.run(argv,cwd=root,env=env,capture_output=True,text=True,timeout=120)
            return {'passed':p.returncode==0,'exit_code':p.returncode,'output':(p.stdout+p.stderr)[-14000:]}
        except subprocess.TimeoutExpired:return {'passed':False,'exit_code':124,'output':'Trusted test command timed out'}

def run(project,solution,destination):
    if __package__:from .operations import Operations
    else:from operations import Operations
    ops=Operations(destination,project['name'],project.get('planfile_ticket'),solution,project.get('gitive_run'),ROOT)
    with ops.observe(), ops.stage('preparing','gitive.develop.run'):
        return _run(project,solution,destination,ops)


def _run(project,solution,destination,ops):
    load_dotenv(ROOT/'.env',override=False,interpolate=False)
    os.environ['LLM_MAX_CALLS']='4'
    root=Path(project['path']);start=git(root,'rev-parse','HEAD')
    if git(root,'status','--porcelain'):raise ValueError('Projekt wymaga czystego checkoutu; zapisz istniejącą pracę')
    if not git(root,'branch','--show-current'):raise ValueError('Projekt wymaga aktywnej gałęzi')
    import fcntl
    lock=Path(git(root,'rev-parse','--absolute-git-dir'))/'gitive-development.lock'
    with lock.open('a') as locked:
        fcntl.flock(locked,fcntl.LOCK_EX|fcntl.LOCK_NB)
        with tempfile.TemporaryDirectory(prefix='gitive-development-') as tmp:
            work=Path(tmp)/'repo';git(root,'clone','--quiet','--no-hardlinks',str(root),str(work))
            git(work,'config','user.name','Gitive');git(work,'config','user.email','gitive@localhost')
            exclude=work/'.git/info/exclude';exclude.write_text(exclude.read_text()+'\n.bench/\n__pycache__/\n')
            with ops.stage('tests','gitive.develop.tests'):
                before=tests(work,project['test_argv'])
            if git(work,'status','--porcelain'):
                raise ValueError('Testy bazowe zmieniły checkout')
            if before['passed']:
                return {'status':'already_green','solution':solution,'base':start,'head':start,'tests':before}
            names=git(work,'ls-files','-z').split('\0')
            allow_prefix = project['allow'].rstrip('/') + '/'
            text_exts = ('.py', '.md', '.txt', '.json', '.yaml', '.yml', '.toml', '.sh', '.js', '.ts', '.html', '.css')
            candidates = [n for n in names if n.startswith(allow_prefix) and not (work/n).is_symlink() and any(n.endswith(ext) for ext in text_exts)]
            if any(n.endswith('.py') for n in candidates) and not allow_prefix.startswith('docs/'):
                py_candidates = [n for n in candidates if n.endswith('.py')]
                selected = py_candidates if len(py_candidates) <= 15 else candidates[:15]
            else:
                selected = candidates[:15]
            code = {}
            for n in selected:
                try:
                    code[n] = (work/n).read_text()
                except Exception:
                    pass
            if not 1<=len(code)<=25 or sum(len(v) for v in code.values())>300000:
                raise ValueError('Wybierz zakres 1–25 plików projektu (kod / dokumentacja), do 300k znaków')
            # Capture each actual SDK call using the same recorder as the benchmark.
            import litellm
            from benchmark.transcripts import Recorder
            original=litellm.completion;recorder=Recorder(Path(destination)/'transcripts',Path(destination))
            calls=[]
            def capture(**kwargs):
                if len(calls)>=4:raise RuntimeError('Development LLM call budget exhausted')
                call_id=f'{solution}--{project["name"]}--{len(calls)+1:03d}'
                request=recorder.request(call_id,kwargs,{"solution":solution,"project":project["name"],"phase":"development"})
                calls.append({'id':call_id,'request_receipt':request})
                try:
                    response=original(**kwargs);calls[-1]['response_receipt']=recorder.response(call_id,response);return response
                except Exception as exc:
                    calls[-1]['error']=type(exc).__name__
                    calls[-1]['error_receipt']=recorder.write(call_id,'error',{'error_type':type(exc).__name__})
                    raise
            litellm.completion=capture
            try:
                adapter=ADAPTERS[solution](work,project['goal'],7)
                if solution=='opus5':adapter.native_test_argv=project['test_argv']
                if solution=='gpt6':adapter.config['allowed_paths']=[n for n in code]
                with ops.stage('log-reading','gitive.develop._run'):
                    evidence=json.dumps({'goal':project['goal'],'failing_tests':before['output'],'allowed_files':list(code)})
                with ops.stage('repair',solution+'.propose_patch'):
                    task,edits=adapter.propose_patch(evidence,code,1)
                with ops.stage('validation','benchmark.common.validate_edits'):
                    edits=validate_edits(edits,code)
                if not edits:raise ValueError('No source changes')
                # Native planners may commit their memory. Keep it in the private clone only.
                adapter.feedback('Patch proposed; external gate pending',False)
                git(work,'reset','--hard',start)
                with ops.stage('coding','gitive.develop._run'):
                    for n,c in edits.items():(work/n).write_text(c)
                with ops.stage('tests','gitive.develop.tests'):
                    result=tests(work,project['test_argv'])
                changed=set(git(work,'diff','HEAD','--name-only').splitlines())
                if git(work,'rev-parse','HEAD')!=start or any((work/n).is_symlink() or (work/n).read_text()!=c for n,c in edits.items()):raise ValueError('Testy zmieniły poprawkę lub HEAD')
                if changed-set(edits) or git(work,'ls-files','--others','--exclude-standard'):raise ValueError('Testy zmieniły pliki poza poprawką')
                if not result['passed']:return {'status':'rejected','solution':solution,'base':start,'tests':result,'calls':calls}
                git(work,'add','--',*edits);git(work,'commit','-m',f'gitive({solution}): validated repair')
                if git(root,'rev-parse','HEAD')!=start or git(root,'status','--porcelain'):raise ValueError('Projekt zmienił się w trakcie pracy')
                git(root,'fetch',str(work),'HEAD');git(root,'merge','--ff-only','FETCH_HEAD')
                return {'status':'repaired','solution':solution,'base':start,'head':git(root,'rev-parse','HEAD'),'tests':result,'calls':calls,'changed':sorted(edits)}
            finally:
                litellm.completion=original
                (Path(destination)/'calls.json').write_text(json.dumps(calls,indent=2))

if __name__=='__main__':
    os.umask(0o077)
    p=argparse.ArgumentParser();p.add_argument('project_json');p.add_argument('solution',choices=list(ADAPTERS));p.add_argument('destination');a=p.parse_args()
    destination=Path(a.destination);destination.mkdir(parents=True,exist_ok=True,mode=0o700)
    try:result=run(json.loads(Path(a.project_json).read_text()),a.solution,destination)
    except Exception as exc:result={'status':'error','error':type(exc).__name__,'message':str(exc)[:600]}
    (destination/'result.json').write_text(json.dumps(result,indent=2))
    print('GITIVE_RESULT '+result['status'],flush=True)
