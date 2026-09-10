"""Host-owned, fixed-operation worker for web requests; no Docker socket in GUI."""
import argparse
import fcntl
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import threading
import time
from .digitaltwin import DigitalTwin,local_path,now
from .engine import write
from .isolation import BASE


def observe(twin):
    rows={}
    for name in twin.all()['workspaces']:
        try:rows[name]={'status':twin.status(name).get('container_status','unknown')}
        except (ValueError,RuntimeError,OSError):rows[name]={'status':'unavailable'}
    write(twin.data/'runtime-host.json',{'at':time.time(),'workspaces':rows})


def perform(twin,job):
    name=job['project'];project=twin.record(name);kind=job['action']
    state=twin.data/'state.json'
    if state.exists() and json.loads(state.read_text()).get('status') in ('running','stopping'):
        raise ValueError('Najpierw zatrzymaj pętlę Gitive')
    if kind=='runtime-test':
        result=twin.execute(name,project['test_argv'],test=True)
        return {k:result[k] for k in ('status','exit_code','created')}
    if kind=='runtime-terminal':
        from .project_terminal import open_terminal
        result=open_terminal(twin,name)
        return {'status':result['status'],'user':result['identity']['username'],'path':result['path_in_container']}
    if kind=='sync-ticket':
        import re
        if not re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+',job.get('repository','')) or job.get('direction') not in ('push','pull'):raise ValueError('Niepoprawna synchronizacja')
        from .planfile_bridge import PlanfileBridge
        with twin.lock:
            return PlanfileBridge(local_path(project['path'],twin.base),job['repository']).sync(job['ticket'],job['direction'])
    raise ValueError('Niedozwolona operacja hosta')


def consume(twin,path):
    job=json.loads(path.read_text())
    if job.get('status')!='queued':return
    job.update(status='running',started=now());write(path,job)
    try:
        result=perform(twin,job)
        job.update(status='failed' if result.get('status')=='failed' else 'complete',result=result)
    except Exception as exc:
        # Arbitrary test output and credentials remain in private runtime logs.
        job.update(status='failed',error=str(exc)[:300] if isinstance(exc,(ValueError,RuntimeError)) else type(exc).__name__)
    job['finished']=now();write(path,job)


def serve(base=BASE):
    os.umask(0o077);twin=DigitalTwin(base);twin.data.mkdir(parents=True,exist_ok=True)
    lock=(twin.data/'runtime-host.lock').open('a');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    folder=twin.data/'control-jobs';folder.mkdir(exist_ok=True)
    for path in folder.glob('*.json'):
        job=json.loads(path.read_text())
        if job.get('status')=='running':
            job.update(status='interrupted',finished=now(),error='Restart hosta. Sprawdź procesy projektu przed ponowieniem.');write(path,job)
    def heartbeat():
        while True:
            try:observe(twin)
            except (OSError,ValueError,RuntimeError):pass
            time.sleep(5)
    threading.Thread(target=heartbeat,daemon=True).start()
    while True:
        for path in sorted(folder.glob('*.json')):consume(twin,path)
        time.sleep(1)


def install():
    """Install a private immutable code copy, then restart the per-user service."""
    if any(json.loads(p.read_text()).get('status')=='running' for p in (BASE/'app-data/control-jobs').glob('*.json')):
        raise ValueError('Operacja hosta trwa; zaczekaj przed aktualizacją usługi')
    target=BASE/'host-worker'/('release-'+str(time.time_ns()))
    shutil.copytree(Path(__file__).parent,target/'gitive',ignore=shutil.ignore_patterns('__pycache__','tests','vendor'))
    unit=Path.home()/'.config/systemd/user/gitive-host.service';unit.parent.mkdir(parents=True,exist_ok=True)
    # systemd quoting is not shell interpolation. Escape percent specifiers and quotes.
    def quoted(value):return '"'+str(value).replace('\\','\\\\').replace('"','\\"').replace('%','%%')+'"'
    unit.write_text('[Unit]\nDescription=Gitive project runtime worker\nAfter=docker.service\n\n[Service]\nType=simple\nEnvironment='+quoted('PYTHONPATH='+str(target))+'\nEnvironment='+quoted('GITIVE_ISOLATION_ROOT='+str(BASE))+'\nExecStart='+quoted(sys.executable)+' -m gitive.host serve\nRestart=on-failure\nRestartSec=5\nUMask=0077\n\n[Install]\nWantedBy=default.target\n')
    subprocess.run(['systemctl','--user','daemon-reload'],check=True)
    subprocess.run(['systemctl','--user','enable','gitive-host.service'],check=True,capture_output=True)
    subprocess.run(['systemctl','--user','restart','gitive-host.service'],check=True)
    print('Host Gitive uruchomiony. Panel może zlecać testy, terminal i synchronizację ticketów.')


def main(argv=None):
    parser=argparse.ArgumentParser();parser.add_argument('action',choices=['start','stop','status','serve']);args=parser.parse_args(argv)
    if args.action=='serve':serve()
    elif args.action=='start':install()
    elif args.action=='stop':subprocess.run(['systemctl','--user','stop','gitive-host.service'],check=True)
    else:
        p=BASE/'app-data/runtime-host.json';value=json.loads(p.read_text()) if p.exists() else {}
        print('Host Gitive: '+('aktywny' if time.time()-value.get('at',0)<20 else 'offline'))
if __name__=='__main__':main()
