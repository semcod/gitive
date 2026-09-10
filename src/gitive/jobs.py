"""Serialized benchmark and registered-project jobs."""
import json
import os
from pathlib import Path
import sys
import threading
import time
import uuid
from .engine import write
from .projects import Projects, winner
from .planfile_bridge import PlanfileBridge

def start(engine, kind='benchmark', name=None, cycles=3, watch=False, interval=60):
    if kind not in ('benchmark','develop') or type(cycles) is not int or not 1<=cycles<=20:raise ValueError('Niepoprawne zadanie')
    if type(watch) is not bool or type(interval) is not int or not 10<=interval<=3600:raise ValueError('Interwał: 10–3600 s')
    registry=Projects(engine.root,engine.data)
    if kind=='develop' and name not in registry.all():raise ValueError('Nieznany projekt')
    with engine.lock:
        if engine.thread and engine.thread.is_alive():raise ValueError('Pętla już działa')
        engine.state=dict(status='running',phase=kind,kind=kind,project=name,run=time.strftime('%Y%m%dT%H%M%SZ',time.gmtime())+'-'+uuid.uuid4().hex[:6],cycle=0,cycles=cycles,watch=watch,interval=interval,demo=False,spent_usd=0,max_usd=1,stop=False,history=[])
        engine.save();engine.thread=threading.Thread(target=run,args=(engine,registry),daemon=True);engine.thread.start()
        return engine.state

def run(e,registry):
    try:
        if e.state['kind']=='benchmark':
            e.benchmark('ranking');e.event('finished',status='complete',selection=winner(e.root));return
        project=registry.all()[e.state['project']]
        if os.getenv('GITIVE_SOURCE_ROOT') and not project.get('copy_only'):raise RuntimeError('Stara rejestracja: zaimportuj projekt ponownie jako kopię')
        iteration=0
        while e.state.get('watch') or iteration<e.state['cycles']:
            iteration+=1
            if e.state['spent_usd']>=e.state['max_usd']:raise RuntimeError('Osiągnięto limit kosztu benchmarku; uruchom ponownie po analizie')
            if e.state['stop']:break
            e.state['cycle']=iteration
            try:selection=winner(e.root)
            except RuntimeError:
                e.event('benchmark');e.benchmark(f'{iteration}-selection');selection=winner(e.root)
            if e.state['stop']:break
            e.event('development',selection=selection)
            destination=e.data/e.state['run']/f'develop-{iteration}'
            bridge=PlanfileBridge(project['path'])
            ticket=bridge.ensure(e.state['run']+':'+str(iteration),project['goal'],selection['solution'],description='Gitive development iteration; independent validation required before publication.')
            e.state['ticket_id']=ticket.id;e.save()
            write(destination/'project.json',{**project,'planfile_ticket':ticket.id})
            e.command([sys.executable,str(Path(__file__).with_name('develop.py')),str(destination/'project.json'),selection['solution'],str(destination)],f'{iteration}-development',1200)
            result=json.loads((destination/'result.json').read_text())
            bridge.outcome(ticket.id,result['status'])
            registry.result(project['name'],{'status':result['status'],'solution':selection['solution'],'report':selection['report'],'result_path':str(destination/'result.json')})
            e.state['history'].append({'iteration':iteration,'solution':selection['solution'],'status':result['status']});e.save()
            if result['status'] in ('already_green','repaired'):
                if not e.state.get('watch'):
                    e.event('finished',status='complete');return
                e.event('watching')
                for _ in range(e.state['interval']):
                    if e.state['stop']:break
                    time.sleep(1)
                continue
            if e.state['stop']:break
            e.event('failure-benchmark');baseline=e.benchmark(f'{iteration}-failure')
            if e.state['stop']:break
            e.event('analysis-and-codex',failure_report=str(destination/'result.json'))
            e.codex()
            e.event('tests');e.command(['make','test'],f'{iteration}-tests',1800)
            e.event('rebenchmark');after=e.benchmark(f'{iteration}-after')
            if any(after['solutions'][s]['final_tests_passed']<baseline['solutions'][s]['final_tests_passed'] for s in baseline['solutions']):raise RuntimeError('Regresja benchmarku; zatrzymano development')
        e.event('finished',status='stopped' if e.state['stop'] else 'blocked',error='Limit prób; projekt wymaga dalszej pracy' if not e.state['stop'] else '')
    except Exception as exc:
        e.event('blocked',status='blocked',error=str(exc)[:500] if type(exc) in (ValueError,RuntimeError) else type(exc).__name__)
