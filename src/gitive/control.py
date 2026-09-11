"""Project-scoped web view and commands; runtime effects go through the host queue."""
import json
import os
from pathlib import Path
import re
import time
import uuid
from datetime import datetime,timezone
from .engine import write
from .projects import Projects,winner
from .planfile_bridge import PlanfileBridge,ENGINES
from .jobs import _repository_from_source


def read(path, default):
    return json.loads(path.read_text()) if path.exists() else default


def project_root(project):
    root=Path(project['path']).resolve()
    allowed=Path(os.getenv('GITIVE_COPY_ROOT','/workspace/github')).resolve()
    if not project.get('copy_only') or root==allowed or not root.is_relative_to(allowed) or not root.is_dir():
        raise ValueError('Projekt nie ma dostępnej prywatnej kopii')
    return root




def extract_ticket_target(title, description=''):
    text = (title or '') + '\n' + (description or '')
    for m in re.finditer(r'(?im)^\s*(?:source|target_repository|repository)\s*:\s*(?:https://github\.com/|source://)?([A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+)', text):
        return m.group(1)
    for m in re.finditer(r'(?m)[—-][\s]*([A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+)\b', title or ''):
        return m.group(1)
    return None


def resolve_project_for_repo(projects, target_repo):
    if not target_repo:
        return None
    for pname, pinfo in projects.items():
        prep = _repository_from_source(pinfo)
        if prep and prep.lower() == target_repo.lower():
            return pname
    return None


def extract_deduplication_key(text):
    if not text: return None
    m = re.search(r'<!--\s*planfile:deduplication-key=([^\s>]+)\s*-->', text)
    if m: return m.group(1)
    m = re.search(r'(?i)fingerprint:\s*([A-Fa-f0-9]+)', text)
    if m: return m.group(1)
    return None


def extract_source_line(text):
    if not text: return None
    m = re.search(r'(?i)source:\s*(https://github\.com/[^\s]+)', text)
    if m: return m.group(1)
    return None


def find_matching_ticket(bridge, source_ticket):
    s_desc = getattr(source_ticket, 'description', '') or ''
    s_dedup = extract_deduplication_key(s_desc)
    s_src = extract_source_line(s_desc)
    tickets = bridge.store.list_tickets(sprint='gitive')
    if s_dedup:
        for cand in tickets:
            c_dedup = extract_deduplication_key(getattr(cand, 'description', '') or '')
            if c_dedup == s_dedup:
                return cand
    if s_src:
        for cand in tickets:
            c_src = extract_source_line(getattr(cand, 'description', '') or '')
            if c_src == s_src:
                return cand
    for cand in tickets:
        if cand.name == source_ticket.name:
            c_dedup = extract_deduplication_key(getattr(cand, 'description', '') or '')
            if not c_dedup and not s_dedup:
                return cand
    return None

def ticket_view(ticket,project):
    binding=ticket.sync.get('github',{})
    target_repo=extract_ticket_target(ticket.name,ticket.description or '')
    return dict(id=ticket.id,project=project,title=ticket.name,description=ticket.description,
        status=ticket.status.value,engine=ticket.executor.handler if ticket.executor else 'unassigned',priority=ticket.priority,
        parent=ticket.parent,blocked_by=ticket.blocked_by,execution_state=ticket.execution.state if ticket.execution else None,created=ticket.created_at.isoformat(),
        updated=ticket.updated_at.isoformat(),github={k:binding[k] for k in ('url','repository','status') if k in binding},
        target_repository=target_repo)


def dashboard(engine):
    catalog=read(engine.data/'digitaltwins.json',{'workspaces':{}})
    observer=read(engine.data/'runtime-host.json',{})
    host_online=time.time()-observer.get('at',0)<20
    jobs=[read(p,{}) for p in sorted((engine.data/'control-jobs').glob('*.json'),reverse=True)[:80]]
    projects=[];tickets=[]
    for name,p in Projects(engine.root,engine.data).all().items():
        rows=[];error=None
        try:
            root=project_root(p)
            if (root/'.planfile').is_dir():
                rows=[ticket_view(t,name) for t in PlanfileBridge(root).store.list_tickets(sprint='gitive') if t.source and t.source.tool=='gitive']
        except (ValueError,OSError) as exc:error=str(exc)
        workspace=catalog['workspaces'].get(name)
        observed=observer.get('workspaces',{}).get(name,{}) if host_online else {}
        runtime=None
        if workspace:
            runtime=dict(id=workspace['id'],status=observed.get('status','unknown'),observed=observer.get('at') if host_online else None,
                path=workspace.get('path_in_container'),user=workspace.get('identity',{}).get('username'),
                python=workspace.get('python',{}).get('version'),node=(workspace.get('node') or {}).get('version'),
                tests=workspace.get('verification',{}).get('project_tests'),created=workspace.get('created'))
            if isinstance(runtime['tests'],dict):runtime['tests']={k:v for k,v in runtime['tests'].items() if k in ('status','exit_code','created')}
        active=[j for j in jobs if j.get('project')==name and j.get('status') in ('queued','running')]
        reason=None
        if workspace and runtime.get('status')!='running':
            reason='Kontener DigitalTwin nie działa; uruchom runtime projektu przed ticketem.'
        projects.append(dict(name=name,title=p.get('display_name',name),goal=p.get('goal',''),demo=p.get('demo',False),
            workspace=runtime,tickets=len(rows),open=sum(t['status'] not in ('done','canceled') for t in rows),
            error=error,repair_block=reason,active_jobs=active,source=p.get('source_path'),
            repository=_repository_from_source(p),
            solution=p.get('solution'),test_command=' '.join(p.get('test_argv',[]))))
        tickets.extend(rows)
    try:ranking=winner(engine.root)
    except RuntimeError:ranking=None
    return dict(at=datetime.now(timezone.utc).isoformat(),server='online',host_online=host_online,
        loop={k:engine.state.get(k) for k in ('status','phase','project','ticket_id','requested_ticket','ticket_title','ticket_desc','executor','cycle','goal','spent_usd','max_usd')},
        projects=projects,tickets=tickets,jobs=jobs,ranking=ranking)


def action(engine, body):
    if not isinstance(body,dict):raise ValueError('Niepoprawne polecenie')
    kind=body.get('action');name=body.get('project')
    projects=Projects(engine.root,engine.data).all()
    if not isinstance(name,str) or name not in projects:raise ValueError('Wybierz istniejący projekt')
    root=project_root(projects[name]);bridge=PlanfileBridge(root)
    if kind=='import-remote-ticket' or kind=='realize-remote-ticket':
        title=body.get('title','');description=body.get('description','')
        repo=body.get('repository','');num=body.get('number',uuid.uuid4().hex[:6])
        url=body.get('url','');executor=body.get('engine','auto')
        target_repo=repo
        if not target_repo:
            text=(title+'\n'+description)
            for m in re.finditer(r'(?im)^\s*(?:source|target_repository|repository)\s*:\s*(?:https://github\.com/|source://)?([A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+)',text):
                target_repo=m.group(1);break
            if not target_repo:
                for m in re.finditer(r'(?m)[—-]\s*([A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+)\b',title):
                    target_repo=m.group(1);break
        if target_repo:
            matched_name=None
            for pname,pinfo in projects.items():
                prep=_repository_from_source(pinfo)
                if prep and prep.lower()==target_repo.lower():
                    matched_name=pname;break
            if matched_name:
                name=matched_name
                root=project_root(projects[name])
                bridge=PlanfileBridge(root)
            else:
                current_repo=_repository_from_source(projects[name])
                if current_repo and current_repo.lower()!=target_repo.lower():
                    raise ValueError('Ticket wskazuje '+target_repo+'; projekt '+name+' ma checkout '+current_repo+'. Zarejestruj właściwy projekt przed wykonaniem.')
        if executor=='auto':
            try:executor=winner(engine.root)['solution']
            except RuntimeError:executor='glm53'
        if executor not in ENGINES:executor='glm53'
        key=f"remote:{repo}:{num}" if repo else f"remote:{uuid.uuid4().hex}"
        ticket=bridge.import_external(key,title,description,repo,str(num),engine=executor,url=url)
        if kind=='realize-remote-ticket':
            from .jobs import start
            run_res=start(engine,kind='develop',name=name,ticket_id=ticket.id,cycles=1)
            return dict(ok=True,ticket=ticket_view(ticket,name),engine_state=run_res)
        return ticket_view(ticket,name)
    if kind=='create-ticket':
        title=body.get('title','');description=body.get('description','');executor=body.get('engine','auto')
        if not isinstance(title,str) or not 1<=len(title.strip())<=180 or not isinstance(description,str) or len(description)>5000:raise ValueError('Podaj tytuł (do 180 znaków) i opis (do 5000)')
        if executor=='auto':executor=winner(engine.root)['solution']
        if executor not in ENGINES:raise ValueError('Wybierz wykonawcę')
        parent=body.get('parent') or None
        if parent:
            previous=bridge.store.get_ticket(parent)
            if previous is None:raise ValueError('Nieznany ticket nadrzędny w tym projekcie')
        ticket=bridge.ensure('web:'+uuid.uuid4().hex,title.strip(),executor,description.strip())
        if parent:ticket=bridge.store.update_ticket(ticket.id,parent=parent,actor='gitive.web',reason='Parent selected in web form')
        return ticket_view(ticket,name)
    selected=body.get('ticket')
    if kind in ('update-ticket','sync-ticket','run-ticket'):
        if not isinstance(selected,str):raise ValueError('Wybierz ticket')
        ticket=bridge.store.get_ticket(selected)
        if ticket is None:
            for pname,pinfo in projects.items():
                if pname==name:continue
                try:
                    alt_bridge=PlanfileBridge(project_root(pinfo))
                    alt_ticket=alt_bridge.store.get_ticket(selected)
                    if alt_ticket:
                        name=pname;bridge=alt_bridge;ticket=alt_ticket;break
                except Exception:pass
        if ticket is None:raise ValueError('Nieznany ticket w wybranym projekcie')
        if ticket.execution and ticket.execution.state=='running':raise ValueError('Ticket jest wykonywany')
    if kind=='update-ticket':
        status=body.get('status')
        if status not in ('open','review','done','blocked','canceled'):raise ValueError('Niepoprawny status ręczny')
        if any(read(p,{}).get('status') in ('queued','running') and read(p,{}).get('project')==name for p in (engine.data/'control-jobs').glob('*.json')):
            raise ValueError('Poczekaj na zakończenie operacji projektu')
        with bridge.lock:ticket=bridge.store.update_ticket(selected,status=status,actor='gitive.web',reason='Manual status change in web UI')
        return ticket_view(ticket,name)
    if kind=='run-ticket':
        target_repo=extract_ticket_target(ticket.name,getattr(ticket,'description','') or '')
        if target_repo:
            matched_name=resolve_project_for_repo(projects,target_repo)
            if matched_name and matched_name!=name:
                target_bridge=PlanfileBridge(project_root(projects[matched_name]))
                target_ticket=target_bridge.store.get_ticket(selected)
                if not target_ticket:
                    target_ticket=find_matching_ticket(target_bridge,ticket)
                if not target_ticket:
                    assigned=ticket.execution.assigned_to if (ticket.execution and ticket.execution.assigned_to) else 'glm53'
                    target_ticket=target_bridge.ensure(f"routed:{ticket.id}",ticket.name,assigned,getattr(ticket,'description','') or '')
                name=matched_name
                bridge=target_bridge
                ticket=target_ticket
                selected=target_ticket.id
            elif not matched_name:
                current_repo=_repository_from_source(projects[name])
                if current_repo and current_repo.lower()!=target_repo.lower():
                    raise ValueError('Ticket wskazuje '+target_repo+'; projekt '+name+' ma checkout '+current_repo+'. Zarejestruj właściwy projekt przed wykonaniem.')
        if ticket.status.value in ('done','canceled'):raise ValueError('Zakończony ticket: utwórz kolejne zadanie')
        from .jobs import start
        return start(engine,kind='develop',name=name,ticket_id=selected,cycles=1)
    if kind not in ('runtime-test','runtime-terminal','sync-ticket'):raise ValueError('Nieznana operacja')
    if kind.startswith('runtime-') and not projects[name].get('workspace_ref'):raise ValueError('Najpierw przygotuj runtime: gitive twin prepare '+name)
    observer=read(engine.data/'runtime-host.json',{})
    if time.time()-observer.get('at',0)>=20:raise ValueError('Proces hosta jest offline; uruchom make start lub gitive host start')
    folder=engine.data/'control-jobs';folder.mkdir(exist_ok=True)
    for p in folder.glob('*.json'):
        job=read(p,{})
        if job.get('project')==name and job.get('status') in ('queued','running'):raise ValueError('Ten projekt ma już operację w kolejce')
    job=dict(id=time.strftime('%Y%m%dT%H%M%SZ',time.gmtime())+'-'+uuid.uuid4().hex[:8],project=name,
             action=kind,status='queued',created=datetime.now(timezone.utc).isoformat())
    if kind=='sync-ticket':
        repo=body.get('repository');direction=body.get('direction')
        if not isinstance(repo,str) or not re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+',repo) or direction not in ('push','pull'):raise ValueError('Wybierz repo owner/name i kierunek')
        job.update(ticket=selected,repository=repo,direction=direction)
    write(folder/(job['id']+'.json'),job)
    return job
