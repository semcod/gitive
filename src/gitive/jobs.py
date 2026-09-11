"""Serialized benchmark and registered-project jobs."""
import json
import os
from pathlib import Path
import re
import sys
import threading
import time
import uuid
import subprocess
from .engine import write
from .projects import Projects, winner
from .planfile_bridge import PlanfileBridge


def _repository_from_source(project):
    source=str(project.get('source_path',''))
    match=re.fullmatch(r'/source/github/([^/]+)/([^/]+)',source.rstrip('/'))
    return '/'.join(match.groups()) if match else None


def validate_ticket_target(project, ticket):
    """Reject a diagnostic ticket whose cited source belongs to another repo."""
    repository=_repository_from_source(project)
    if not repository:
        return
    text=(ticket.name+'\n'+ticket.description)
    targets=[]
    for match in re.finditer(r'(?im)^\s*(?:source|target_repository|repository)\s*:\s*(?:https://github\.com/|source://)?([A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+)',text):
        targets.append(match.group(1).lower())
    for match in re.finditer(r'(?m)[—-]\s*([A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+)\b',ticket.name):
        targets.append(match.group(1).lower())
    mismatched=sorted({target for target in targets if target!=repository.lower() and not repository.lower().endswith('/'+target)})
    if mismatched:
        raise ValueError('Ticket wskazuje '+', '.join(mismatched)+'; projekt ma checkout '+repository+'. Zarejestruj właściwy projekt przed wykonaniem.')


def ticket_requires_human_review(ticket):
    """Return true for findings that explicitly withhold repair authorization.

    Doctor/code-search findings are evidence for a human decision. They must not
    be sent to an executor merely because a project has a green baseline.
    """
    text = ((getattr(ticket, 'name', '') or '') + '\n' +
            (getattr(ticket, 'description', '') or '')).lower()
    return bool(re.search(r'\bassessment\s*:\s*review_required\b', text) or
                'not repair authorization' in text or
                'not an authorization for repair' in text)

def start(engine, **kwargs):
    from filelock import FileLock
    with FileLock(str(engine.data/'workspace-provision.lock'),timeout=0):
        return _start(engine,**kwargs)


def start_assessment(engine, project, ticket_id):
    """Run a read-only implementation assessment and leave a user decision."""
    registry = Projects(engine.root, engine.data)
    projects = registry.all()
    if project not in projects:
        raise ValueError('Nieznany projekt')
    bridge = PlanfileBridge(projects[project]['path'])
    ticket = bridge.store.get_ticket(ticket_id)
    if ticket is None:
        raise ValueError('Nieznany ticket Gitive')
    with engine.lock:
        if engine.thread and engine.thread.is_alive():
            raise ValueError('Pętla już działa')
        run = time.strftime('%Y%m%dT%H%M%SZ', time.gmtime())+'-'+uuid.uuid4().hex[:6]
        engine.state.update(status='running', phase='assessment', project=project,
            requested_ticket=ticket_id, ticket_id=ticket_id, ticket_title=ticket.name,
            ticket_desc=getattr(ticket, 'description', '') or '', run=run, cycle=0,
            assessment={'status':'running','ticket_id':ticket_id,'project':project})
        engine.save()
        engine.thread = threading.Thread(target=_run_assessment, args=(engine, project, ticket_id), daemon=True)
        engine.thread.start()
        return engine.state


def _run_assessment(engine, project, ticket_id):
    registry = Projects(engine.root, engine.data)
    info = registry.all()[project]
    bridge = PlanfileBridge(info['path'])
    ticket = bridge.store.get_ticket(ticket_id)
    root = Path(info['path'])
    text = f'{ticket.name}\n{getattr(ticket, "description", "") or ""}'
    words = [w.lower() for w in re.findall(r'[A-Za-z][A-Za-z0-9_]{3,}', ticket.name)][:8]
    evidence = []
    for word in words:
        try:
            proc = subprocess.run(['git','grep','-n','-i','-e',word,'--','*.py','*.js','*.ts','*.md'], cwd=root,
                text=True, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=20)
            if proc.stdout:
                evidence.extend(proc.stdout.splitlines()[:5])
        except (OSError, subprocess.TimeoutExpired):
            pass
    tools = []
    for tool in ('code2dsl','data2dsl','todo2code'):
        found = subprocess.run(['sh','-lc',f'command -v {tool}'], text=True, stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL).stdout.strip()
        tools.append({'tool':tool,'available':bool(found),'path':found or None,
                      'status':'skipped' if not found else 'available'})
    recommendation = 'already_implemented' if evidence else 'implement'
    if len(evidence) >= 8:
        recommendation = 'review_or_split'
    result = {'schema':'wellmanifest.dsl/action/v1','action':'ticket.implementation_assessment',
        'status':'complete','ticket_id':ticket_id,'project':project,
        'recommendation':recommendation,'evidence':evidence[:20],'tools':tools,
        'next_actions':['close','create_repair','realize'],
        'summary':('Znaleziono istniejące punkty implementacji; wymaga decyzji użytkownika.' if evidence
                   else 'Nie znaleziono oczywistych punktów implementacji; zadanie wygląda na nowe.')}
    folder = engine.data/engine.state['run']
    write(folder/'assessment.json', result)
    with engine.lock:
        engine.state['assessment'] = result
        engine.state['status'] = 'idle'
        engine.event('assessment-complete', status='idle', assessment=result)


def assessment_decision(engine, project, ticket_id, decision):
    if decision not in ('close','create_repair','realize'):
        raise ValueError('Nieznana decyzja oceny')
    registry = Projects(engine.root, engine.data)
    info = registry.all().get(project)
    if not info: raise ValueError('Nieznany projekt')
    bridge = PlanfileBridge(info['path']); ticket = bridge.store.get_ticket(ticket_id)
    if ticket is None: raise ValueError('Nieznany ticket Gitive')
    if decision == 'close':
        bridge.outcome(ticket.id, 'already_green')
        bridge.store.update_ticket(ticket.id, status='done', actor='gitive-assessment', reason='Assessment: already implemented')
        return {'ok':True,'decision':decision,'ticket_id':ticket.id}
    if decision == 'create_repair':
        child = bridge.ensure('repair:'+ticket.id, '[Naprawa] '+ticket.name, ticket.executor.handler if ticket.executor else 'glm53',
            'Zadanie utworzone po ocenie implementacji. Zweryfikuj zakres i dodaj test regresyjny.')
        child = bridge.store.update_ticket(child.id, parent=ticket.id, actor='gitive-assessment', reason='Powiązanie z oceną implementacji')
        return {'ok':True,'decision':decision,'ticket':child.id}
    return start(engine, kind='develop', name=project, ticket_id=ticket.id, cycles=1)

def _start(engine, kind='benchmark', name=None, cycles=3, watch=False, interval=60, ticket_id=None, authorize=False):
    if kind not in ('benchmark','develop') or type(cycles) is not int or not 1<=cycles<=20:raise ValueError('Niepoprawne zadanie')
    if type(watch) is not bool or type(interval) is not int or not 10<=interval<=3600:raise ValueError('Interwał: 10–3600 s')
    registry=Projects(engine.root,engine.data)
    if kind=='develop' and name not in registry.all():raise ValueError('Nieznany projekt')
    if kind=='develop' and registry.all()[name].get('workspace_ref'):
        # A provisioned project is executed by the DigitalTwin adapter below.
        # It is deliberately not routed through the host-side develop.py path.
        observer_path = engine.data / 'runtime-host.json'
        ws_status = None
        if observer_path.exists():
            try:
                obs = json.loads(observer_path.read_text())
                if time.time() - obs.get('at', 0) < 30:
                    ws_status = obs.get('workspaces', {}).get(name, {}).get('status')
            except Exception:
                pass
        if ws_status is None:
            try:
                from .digitaltwin import DigitalTwin
                workspace = DigitalTwin(data=engine.data).status(name)
                ws_status = workspace.get('container_status')
            except Exception:
                pass
        if ws_status != 'running':
            raise ValueError('Kontener DigitalTwin nie działa; uruchom twin prepare/start '+name)
    if ticket_id is not None:
        if kind!='develop' or watch:raise ValueError('Ticket wymaga pojedynczego uruchomienia projektu')
        bridge=PlanfileBridge(registry.all()[name]['path'])
        ticket=bridge.store.get_ticket(ticket_id)
        if ticket is None:raise ValueError('Nieznany ticket Gitive')
        if ticket.status.value in ('done','canceled'):raise ValueError('Ticket jest zakończony; utwórz nowe zadanie')
        try:
            validate_ticket_target(registry.all()[name],ticket)
        except ValueError:
            target_repo=None
            text=(ticket.name+'\n'+(getattr(ticket,'description','') or ''))
            for m in re.finditer(r'(?im)^\s*(?:source|target_repository|repository)\s*:\s*(?:https://github\.com/|source://)?([A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+)',text):
                target_repo=m.group(1);break
            if not target_repo:
                for m in re.finditer(r'(?m)[—-][\s]*([A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+)\b',ticket.name):
                    target_repo=m.group(1);break
            matched_name=None
            if target_repo:
                for pname,pinfo in registry.all().items():
                    prep=_repository_from_source(pinfo)
                    if prep and (prep.lower()==target_repo.lower() or prep.lower().endswith('/'+target_repo.lower())):
                        matched_name=pname;break
                    if pname.lower()==target_repo.lower():
                        matched_name=pname;break
            if matched_name and matched_name!=name:
                orig_name=name
                name=matched_name
                bridge=PlanfileBridge(registry.all()[name]['path'])
                from .control import find_matching_ticket
                target_ticket=find_matching_ticket(bridge,ticket,orig_name)
                if not target_ticket:
                    assigned=(ticket.execution.assigned_to if (ticket.execution and ticket.execution.assigned_to) else (ticket.executor.handler if ticket.executor else 'glm53'))
                    target_ticket=bridge.ensure(f'routed:{orig_name}:{ticket.id}',ticket.name,assigned,getattr(ticket,'description','') or '')
                ticket=target_ticket
                ticket_id=target_ticket.id
            else:
                raise
        if ticket_requires_human_review(ticket) and not authorize:
            raise ValueError('Ticket jest diagnostyczny (review_required) i nie autoryzuje naprawy; użyj autoryzacji (--authorize) lub utwórz osobny ticket naprawczy.')
        for dependency in ticket.blocked_by:
            prior=bridge.store.get_ticket(dependency)
            if prior is None or prior.status.value!='done':raise ValueError('Niespełniona zależność ticketu: '+dependency)
        cycles=1
    with engine.lock:
        if engine.thread and engine.thread.is_alive():raise ValueError('Pętla już działa')
        t_title = getattr(ticket, 'name', None) if (ticket_id and 'ticket' in locals() and ticket) else None
        t_desc = getattr(ticket, 'description', None) if (ticket_id and 'ticket' in locals() and ticket) else None
        engine.state=dict(status='running',phase=kind,kind=kind,project=name,requested_ticket=ticket_id,ticket_id=ticket_id,ticket_title=t_title,ticket_desc=t_desc,run=time.strftime('%Y%m%dT%H%M%SZ',time.gmtime())+'-'+uuid.uuid4().hex[:6],cycle=0,cycles=cycles,watch=watch,interval=interval,demo=False,spent_usd=0,max_usd=1,stop=False,history=[])
        engine.save();engine.thread=threading.Thread(target=run,args=(engine,registry),daemon=True);engine.thread.start()
        return engine.state

def run(e,registry):
    try:
        if e.state['kind']=='benchmark':
            e.benchmark('ranking');e.event('finished',status='complete',selection=winner(e.root));return
        project=registry.all()[e.state['project']]
        if os.getenv('GITIVE_SOURCE_ROOT') and not project.get('copy_only'):raise RuntimeError('Stara rejestracja: zaimportuj projekt ponownie jako kopię')
        requested=e.state.get('requested_ticket')
        existing=PlanfileBridge(project['path']).store.get_ticket(requested) if requested else None
        if existing:
            project={**project,'goal':existing.name+'\n'+existing.description}
            e.state['ticket_title']=existing.name
            e.state['ticket_desc']=getattr(existing,'description','') or ''
            e.save()
        iteration=0
        while e.state.get('watch') or iteration<e.state['cycles']:
            iteration+=1
            if e.state['spent_usd']>=e.state['max_usd']:raise RuntimeError('Osiągnięto limit kosztu benchmarku; uruchom ponownie po analizie')
            if e.state['stop']:break
            e.state['cycle']=iteration
            try:selection=({'solution':existing.executor.handler,'report':'ticket-assignment'} if existing else winner(e.root))
            except RuntimeError:
                e.event('benchmark');e.benchmark(f'{iteration}-selection');selection=winner(e.root)
            if e.state['stop']:break
            e.event('development',selection=selection)
            destination=e.data/e.state['run']/f'develop-{iteration}'
            bridge=PlanfileBridge(project['path'])
            ticket=existing or bridge.ensure(e.state['run']+':'+str(iteration),project['goal'],selection['solution'],description='Gitive development iteration; independent validation required before publication.')
            bridge.store.update_ticket(ticket.id,status='in_progress',actor='gitive',reason='Execution started')
            e.state['ticket_id']=ticket.id
            e.state['ticket_title']=ticket.name
            e.state['ticket_desc']=getattr(ticket,'description','') or ''
            e.state['executor']=selection.get('solution')
            e.save()
            bridge.execution(ticket.id,'running',e.state['run'])
            t_payload = {'planfile_ticket':ticket.id,'ticket_title':ticket.name,'ticket_description':getattr(ticket,'description','') or '','ticket_acceptance':getattr(ticket,'acceptance_criteria','') or '','gitive_run':e.state['run']}
            if getattr(ticket,'source',None) and getattr(ticket.source,'context',None):
                t_payload['ticket_source'] = ticket.source.context
            write(destination/'project.json',{**project,**t_payload})
            worker='runtime_develop.py' if project.get('workspace_ref') else 'develop.py'
            e.command([sys.executable,str(Path(__file__).with_name(worker)),str(destination/'project.json'),selection['solution'],str(destination)],f'{iteration}-development',1200)
            result=json.loads((destination/'result.json').read_text())
            bridge.outcome(ticket.id,result['status'])
            bridge.execution(ticket.id,'done' if result['status'] in ('already_green','repaired') else 'failed',e.state['run'],str(destination/'result.json'))
            registry.result(project['name'],{'status':result['status'],'solution':selection['solution'],'report':selection['report'],'result_path':str(destination/'result.json')})
            e.state['history'].append({'iteration':iteration,'ticket_id':ticket.id,'solution':selection['solution'],'status':result['status']});e.save()
            if result['status'] in ('already_green','repaired'):
                if not e.state.get('watch'):
                    e.event('finished',status='complete');return
                e.event('watching')
                for _ in range(e.state['interval']):
                    if e.state['stop']:break
                    time.sleep(1)
                continue
            if e.state['stop']:break
            if existing:
                e.event('finished',status='blocked',error='Ticket wymaga analizy wyniku; raport zapisany');return
            e.event('failure-benchmark');baseline=e.benchmark(f'{iteration}-failure')
            if e.state['stop']:break
            e.event('analysis-and-codex',failure_report=str(destination/'result.json'))
            e.codex()
            e.event('tests');e.command(['make','test'],f'{iteration}-tests',1800)
            e.event('rebenchmark');after=e.benchmark(f'{iteration}-after')
            if any(after['solutions'][s]['final_tests_passed']<baseline['solutions'][s]['final_tests_passed'] for s in baseline['solutions']):raise RuntimeError('Regresja benchmarku; zatrzymano development')
        e.event('finished',status='stopped' if e.state['stop'] else 'blocked',error='Limit prób; projekt wymaga dalszej pracy' if not e.state['stop'] else '')
    except Exception as exc:
        if e.state.get('ticket_id'):
            try:
                bridge=PlanfileBridge(registry.all()[e.state['project']]['path'])
                bridge.outcome(e.state['ticket_id'],'error')
                bridge.execution(e.state['ticket_id'],'failed',e.state['run'],error=type(exc).__name__)
            except Exception:pass
        e.event('stopped' if e.state.get('stop') else 'blocked',status='stopped' if e.state.get('stop') else 'blocked',error=str(exc)[:500] if type(exc) in (ValueError,RuntimeError) else type(exc).__name__)
