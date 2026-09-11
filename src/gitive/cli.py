"""Local HTTP client and interactive gitive shell."""
import argparse
import json
import os
from pathlib import Path
import re
import shlex
import sys
import urllib.request
import urllib.error
URL=os.getenv('GITIVE_URL','http://127.0.0.1:8793')
def color(text,tone='cyan'):
    if not sys.stdout.isatty() or 'NO_COLOR' in os.environ or os.getenv('TERM')=='dumb':return text
    codes={'cyan':'36','green':'32','yellow':'33','red':'31','bold':'1'}
    return '\033['+codes[tone]+'m'+text+'\033[0m'

def human(text):
    for line in text.splitlines():
        lower=line.lower()
        tone=('red' if any(x in lower for x in ('błąd','zablokowana','przerwana')) else
              'yellow' if any(x in lower for x in ('brak','nie skopiowano','offline','podgląd')) else
              'green' if 'zakończona' in lower else 'cyan')
        print(color(line,tone))

def sync_help():
    print(color('Synchronizacja PC → prywatna kopia noVNC','bold'))
    print('W shellu wpisuj polecenia bez ./gitive. Zastąp organizacja/projekt własnym repo z ~/github.')
    print(color('Pierwsza kopia (zamknij wybraną przeglądarkę na PC):','yellow'))
    print('  stop')
    print(color('  workspace snapshot pc-firefox --project organizacja/projekt --browser firefox'))
    print('  workspace status  → poczekaj na zakończenie')
    print(color('  workspace clone'))
    print('  workspace status  → poczekaj na zakończenie clone')
    print(color('Kolejne aktualizacje:','bold'))
    print(color('  workspace resync --include-sessions'))
    print('  workspace status  → poczekaj i sprawdź podgląd / konflikty')
    print(color('  workspace resync --apply --include-sessions'))
    print('  workspace status  → sprawdź wynik zapisu')
    print('Przeglądarka: firefox | chrome | chromium | all. Zmiana wyboru wymaga nowego snapshotu.')
    print(color('Profile pozostają offline; przeglądarka w noVNC nie uruchomi ich automatycznie.','yellow'))
    print('Oryginały PC nie są nadpisywane. Poza shellem poprzedź komendę ./gitive.')

def request(path,body=None,timeout=20):
    headers={}
    if body is not None:
        page=urllib.request.urlopen(URL,timeout=5).read().decode()
        headers={'Content-Type':'application/json','X-Loop-Token':re.search(r"const token='([^']+)'",page)[1]}
    req=urllib.request.Request(URL+path,data=json.dumps(body).encode() if body is not None else None,headers=headers)
    try:
        with urllib.request.urlopen(req,timeout=timeout) as r:return json.load(r)
    except urllib.error.HTTPError as exc:raise RuntimeError(json.load(exc).get('error',str(exc))) from None

def choose_record(kind):
    if __package__:from .presentation import choice_label
    else:from presentation import choice_label
    rows=request('/api/workspace').get(kind,[])
    if not rows:raise ValueError('Brak kopii do wyboru. Najpierw wykonaj snapshot, a następnie clone.' if kind=='clones' else 'Brak zapisanych snapshotów. Najpierw utwórz snapshot.')
    print('Dostępne '+{'clones':'kopie','snapshots':'snapshoty','profiles':'profile'}[kind]+' (czas: Europe/Warsaw):',file=sys.stderr)
    for i,row in enumerate(rows,1):print(f"{i}. {choice_label(row)}",file=sys.stderr)
    if len(rows)==1:
        selected=rows[0]
    else:
        if not sys.stdin.isatty():raise ValueError('Wybierz w terminalu lub podaj '+('CLONE_ID' if kind=='clones' else 'SNAPSHOT_ID')+'; pełne dane: workspace inspect --json')
        try:index=int(input('Wybierz numer (0 = anuluj): '))-1
        except (ValueError,EOFError):raise ValueError('Nie wybrano poprawnego numeru') from None
        if not 0<=index<len(rows):raise ValueError('Anulowano wybór' if index==-1 else 'Niepoprawny numer')
        selected=rows[index]
    print('Wybrano: '+choice_label(selected),file=sys.stderr)
    return selected['id']

def choose_clone():return choose_record('clones')

def main(argv=None):
    p=argparse.ArgumentParser(prog='gitive');sub=p.add_subparsers(dest='cmd',required=True)
    for name in ('status','rank','benchmark','shell','stop','sync-help'):sub.add_parser(name)
    host=sub.add_parser('host');host.add_argument('host_action',choices=['start','stop','status'])
    menu=sub.add_parser('menu');menu.add_argument('choice',nargs='?',type=int,help='Wykonaj pozycję menu, np. menu 4')
    project=sub.add_parser('project').add_subparsers(dest='operation',required=True)
    project.add_parser('list')
    project.add_parser('new')
    project.add_parser('open').add_argument('name',nargs='?')
    project.add_parser('status').add_argument('name')
    add=project.add_parser('add');add.add_argument('name');add.add_argument('path');add.add_argument('--goal',required=True);add.add_argument('--test',required=True);add.add_argument('--allow',default='src')
    run=project.add_parser('run');run.add_argument('name');run.add_argument('--cycles',type=int,default=3)
    watch=project.add_parser('watch');watch.add_argument('name');watch.add_argument('--interval',type=int,default=60)
    delivery=sub.add_parser('delivery',help='Natywny GPT6: istniejące Issue → draft PR → testy').add_subparsers(dest='delivery_action',required=True)
    for name in ('import','run','status'):
        dp=delivery.add_parser(name);dp.add_argument('project')
        if name=='import':
            dp.add_argument('--repo',required=True);dp.add_argument('--issue',required=True,type=int)
            dp.add_argument('--file',action='append',required=True);dp.add_argument('--accept',action='append',required=True)
            dp.add_argument('--image',required=True,help='Lokalny obraz Docker z runtime i zależnościami testów')
            dp.add_argument('--test',required=True,help='Zaufane polecenie testów jako JSON argv')
        else:dp.add_argument('--ticket',required=True)
        if name=='run':
            dp.add_argument('--apply',action='store_true');dp.add_argument('--cycles',type=int,choices=range(1,4),default=1)
    tickets=sub.add_parser('tickets').add_subparsers(dest='ticket_action',required=True)
    for action in ('list','create','sync','show','run','update','import'):
        tp=tickets.add_parser(action);tp.add_argument('project')
        if action=='create':
            tp.add_argument('--title',required=True);tp.add_argument('--engine',choices=['auto','glm53','gpt6','opus5'],default='auto');tp.add_argument('--key');tp.add_argument('--description',default='')
        if action in ('sync','show','run','update'):
            tp.add_argument('ticket',nargs='?',default=None)
            tp.add_argument('--ticket',dest='flag_ticket',default=None)
        if action=='run':
            tp.add_argument('--authorize',action='store_true',help='Autoryzuj naprawę dla ticketu diagnostycznego (review_required)')
        if action=='sync':
            tp.add_argument('--repo',required=True);tp.add_argument('--direction',choices=['push','pull'],required=True)
        if action=='update':tp.add_argument('--status',choices=['open','review','done','blocked','canceled'],required=True)
        if action=='import':
            tp.add_argument('--repo',required=True);tp.add_argument('--issue',required=True,type=int);tp.add_argument('--title',required=True)
            tp.add_argument('--description',default='');tp.add_argument('--engine',choices=['auto','glm53','gpt6','opus5'],default='auto');tp.add_argument('--url',default='')
    twin=sub.add_parser('twin').add_subparsers(dest='twin_action',required=True)
    for name in ('plan','prepare','status','test','exec','recover','extend','terminal'):
        tp=twin.add_parser(name);tp.add_argument('project')
        if name in ('plan','prepare'):
            tp.add_argument('--python');tp.add_argument('--node');tp.add_argument('--image')
            tp.add_argument('--include-path',action='append',default=[])
        if name=='extend':tp.add_argument('--include-path',action='append',required=True)
        if name=='test':tp.add_argument('--env',action='append',default=[])
        if name=='exec':tp.add_argument('argv',nargs=argparse.REMAINDER)
    ws=sub.add_parser('workspace').add_subparsers(dest='ws',required=True)
    for name in ('inspect','status','inventory'):ws.add_parser(name)
    snap=ws.add_parser('snapshot');snap.add_argument('name');snap.add_argument('--project',required=True,help='Ścieżka względem ~/github');snap.add_argument('--include-sessions',action='store_true');snap.add_argument('--exclude-session',dest='exclude_sessions',action='append',default=[],help='Pomiń aktywnego klienta, np. .codex');snap.add_argument('--browser',choices=['none','all','firefox','chrome','chromium'],default='none')
    clone=ws.add_parser('clone');clone.add_argument('snapshot',nargs='?',help='Pomiń, aby wybrać snapshot z listy');clone.add_argument('--target',help='Nowy katalog w prywatnym magazynie kopii')
    sync=ws.add_parser('resync');sync.add_argument('clone',nargs='?',help='ID kopii; pomiń, aby wybrać automatycznie lub z listy');sync.add_argument('--include-sessions',action='store_true');mode=sync.add_mutually_exclusive_group();mode.add_argument('--apply',action='store_true');mode.add_argument('--dry-run',action='store_true')
    resume=ws.add_parser('resume');resume.add_argument('clone',nargs='?');resume.add_argument('--application',choices=['terminal','vscode','cursor'],default='terminal')
    activation=ws.add_parser('activate');activation.add_argument('clone',nargs='?');activation.add_argument('--browser',choices=['firefox','chrome'],required=True);activation.add_argument('--include-sessions',action='store_true')
    profile=ws.add_parser('profile');profile.add_argument('action',choices=['snapshot','restore']);profile.add_argument('--browser',choices=['all','chrome','chromium','firefox'],default='all');profile.add_argument('--snapshot')
    def json_option(parser):
        parser.add_argument('--json',action='store_true',default=argparse.SUPPRESS,help='Pokaż pełne dane JSON')
        for action in parser._actions:
            if isinstance(action,argparse._SubParsersAction):
                for child in action.choices.values():json_option(child)
    json_option(p)
    a=p.parse_args(argv)
    if a.cmd=='host':
        sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
        from gitive.host import main as host_main
        return host_main([a.host_action])
    if a.cmd=='shell':return Shell().cmdloop()
    if a.cmd=='delivery':
        sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
        from gitive.delivery import run_cli
        return run_cli(a)
    if a.cmd=='tickets':return ticket_command(a)
    if a.cmd=='twin':return twin_command(a)
    if a.cmd=='sync-help':return sync_help()
    if a.cmd=='menu':
        actions=show_menu(getattr(a,'json',False))
        if a.choice is not None:
            if not 1<=a.choice<=len(actions):raise ValueError('Niepoprawny numer menu')
            target=actions[a.choice-1]['argv']
            if target!=['menu']:return main(target)
        return
    if a.cmd=='project' and a.operation in ('open','new'):
        if __package__:from .navigation import project_menu,new_project
        else:from navigation import project_menu,new_project
        return new_project(main,request) if a.operation=='new' else project_menu(a.name,main,request)
    if a.cmd=='project' and a.operation=='status':return project_status(a.name,getattr(a,'json',False))
    if a.cmd=='workspace' and a.ws=='activate':
        if __package__:from .novnc_workspace import activate
        else:
            sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
            from gitive.novnc_workspace import activate
        result=activate(a.clone or choose_clone(),a.browser,a.include_sessions)
        print(json.dumps(result,ensure_ascii=False,indent=2) if getattr(a,'json',False) else 'Aktywowano prywatną kopię '+result['browser']+' '+result['version']+'; poprzedni profil zachowano w backupie. Logowanie nie jest potwierdzone.')
        return
    if a.cmd=='workspace':
        if a.ws in ('inspect','status'):result=request('/api/workspace'+('/state' if a.ws=='status' else ''))
        else:
            body={k:v for k,v in vars(a).items() if k not in ('cmd','ws','apply','dry_run','json')}
            if a.ws=='clone':
                body['snapshot']=a.snapshot or choose_record('snapshots')
                if not a.target:
                    if not sys.stdin.isatty():raise ValueError('Podaj --target lub uruchom wybór w terminalu')
                    body['target']=input('Nowy katalog kopii (np. kopie/moj-projekt): ').strip()
                    if not body['target']:raise ValueError('Nie podano katalogu kopii')
            if a.ws=='resume':body['clone']=a.clone or choose_clone()
            if a.ws=='profile' and a.action=='restore' and not a.snapshot:body['snapshot']=choose_record('profiles')
            if a.ws=='resync':
                body['clone']=a.clone or choose_clone()
                body['dry_run']=not a.apply
            result=request('/api/workspace',{'operation':a.ws,**body})
    elif a.cmd=='status':result=request('/api/state')
    elif a.cmd=='rank':
        try:result=request('/api/rank')
        except RuntimeError as exc:
            if 'Brak aktualnego wspólnego benchmarku' in str(exc):
                print(str(exc))
                return
            raise
    elif a.cmd=='benchmark':result=request('/api/job',{'kind':'benchmark'})
    elif a.cmd=='stop':result=request('/api/stop',{})
    elif a.operation=='list':result=request('/api/projects')
    elif a.operation=='watch':result=request('/api/job',{'kind':'develop','name':a.name,'watch':True,'interval':a.interval})
    elif a.operation=='run':result=request('/api/job',{'kind':'develop','name':a.name,'cycles':a.cycles})
    else:
        path=Path(a.path).resolve();host=Path(os.getenv('GITIVE_GITHUB_ROOT','/home/tom/github')).resolve()
        if not path.is_relative_to(host):raise ValueError('Projekt musi znajdować się pod '+str(host))
        result=request('/api/projects',dict(name=a.name,path=str(Path('/source/github')/path.relative_to(host)),goal=a.goal,test_argv=shlex.split(a.test),allow=a.allow))
    if getattr(a,'json',False):print(json.dumps(result,ensure_ascii=False,indent=2))
    else:
        if __package__:from .presentation import render
        else:from presentation import render
        kind=('inspect' if a.cmd=='workspace' and a.ws=='inspect' else
              'projects' if a.cmd=='project' and a.operation=='list' else a.cmd)
        human(render(result,kind))
def twin_command(args):
    if __package__:from .digitaltwin import DigitalTwin
    else:
        sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
        from gitive.digitaltwin import DigitalTwin
    twin=DigitalTwin()
    if args.twin_action in ('plan','prepare'):
        method=twin.plan if args.twin_action=='plan' else twin.prepare
        result=method(args.project,args.python,args.node,args.image,args.include_path)
    elif args.twin_action=='terminal':
        from gitive.project_terminal import open_terminal
        result=open_terminal(twin,args.project)
    elif args.twin_action=='status':result=twin.status(args.project)
    elif args.twin_action=='recover':result=twin.recover(args.project)
    elif args.twin_action=='extend':result=twin.extend(args.project,args.include_path)
    elif args.twin_action=='exec':result=twin.execute(args.project,args.argv[1:] if args.argv[:1]==['--'] else args.argv)
    else:
        env={}
        for pair in args.env:
            if '=' not in pair:raise ValueError('Użyj --env NAZWA=wartość')
            key,value=pair.split('=',1);env[key]=value
        result=twin.execute(args.project,twin.record(args.project)['test_argv'],test=True,env=env)
    if getattr(args,'json',False):print(json.dumps(result,ensure_ascii=False,indent=2))
    elif args.twin_action=='plan':
        print('Projekt: '+result['project']+' · Python '+result['python']['version'])
        print('Kopia pełnych katalogów: '+str(len(result['roots']))+' · '+str(round(sum(result['sizes'].values())/1024**3,2))+' GiB')
        print('Pojemność: '+('wystarczająca' if result['capacity']['fits'] else 'niedobór '+str(result['capacity']['shortfall_bytes'])+' bajtów'))
        print('Dalej: twin prepare '+args.project)
    else:
        print('Projekt: '+args.project+' · '+(result['status'] if args.twin_action=='terminal' else result.get('container_status',result.get('status','?'))))
        if result.get('identity'):print('Użytkownik: '+result['identity']['username']+' · HOME: '+result['identity']['home'])
        if result.get('path_in_container'):print('Ścieżka: '+result['path_in_container'])
        if result.get('python'):print('Python: '+result['python']['version'])
        if result.get('node'):print('Node: '+result['node']['version'])
        if result.get('last_import'):print('Import jeszcze niezatwierdzony; zapis: '+result['last_import'])
        if result.get('log'):print('Log prywatny: '+result['log'])
        print('Dalej: twin status/test '+args.project)
    if args.twin_action in ('exec','test') and result.get('exit_code'):raise SystemExit(result['exit_code'])

def ticket_bridge(project,repository=None):
    if __package__:from .planfile_bridge import PlanfileBridge
    else:from planfile_bridge import PlanfileBridge
    rows=request('/api/projects')
    if project not in rows or not rows[project].get('copy_only'):raise ValueError('Najpierw zarejestruj prywatną kopię projektu')
    registered=Path(rows[project]['path'])
    root=registered if registered.is_dir() else Path(os.getenv('GITIVE_ISOLATION_ROOT',str(Path.home()/'.local/share/gitive-isolated')))/'github'/registered.relative_to('/workspace/github')
    if not root.is_dir():raise ValueError('Kopia projektu jest niedostępna na tym hoście')
    return PlanfileBridge(root,repository)


def ticket_records(project):
    from zoneinfo import ZoneInfo
    return [dict(id=t.id,title=t.name,status=t.status.value,executor=t.executor.handler,
                 created=t.created_at.astimezone(ZoneInfo('Europe/Warsaw')).strftime('%Y-%m-%d %H:%M:%S %Z'),
                 github=t.sync.get('github',{}))
            for t in ticket_bridge(project).store.list_tickets(sprint='gitive') if t.source and t.source.tool=='gitive']


def ticket_command(args):
    ticket_val = getattr(args, 'flag_ticket', None) or getattr(args, 'ticket', None)
    args.ticket = ticket_val
    bridge=ticket_bridge(args.project,getattr(args,'repo',None))
    if args.ticket_action=='update':
        if not args.ticket:raise ValueError('Podaj ticket')
        result=request('/api/control/action',{'action':'update-ticket','project':args.project,'ticket':args.ticket,'status':args.status})
    elif args.ticket_action=='import':
        result=request('/api/control/action',{'action':'import-remote-ticket','project':args.project,'repository':args.repo,
                                              'number':args.issue,'title':args.title,'description':args.description,
                                              'engine':args.engine,'url':args.url})
    elif args.ticket_action=='create':
        import uuid
        engine=request('/api/rank')['solution'] if args.engine=='auto' else args.engine
        ticket=bridge.ensure(args.key or 'manual:'+uuid.uuid4().hex,args.title,engine,args.description)
        args.engine=engine
        result={'id':ticket.id,'title':ticket.name,'executor':args.engine}
    else:
        records=[t for t in bridge.store.list_tickets(sprint='gitive') if t.source and t.source.tool=='gitive']
        if args.ticket_action=='list':
            result=[{'id':t.id,'name':t.name,'status':t.status.value,'executor':t.executor.handler,'github':t.sync.get('github',{}).get('url')} for t in records]
        else:
            selected=args.ticket
            if not selected:
                if not records:raise ValueError('Brak lokalnych ticketów Gitive')
                for i,t in enumerate(records,1):print(f'{i}. {t.name} · {t.status.value} · {t.executor.handler} · {t.created_at:%Y-%m-%d %H:%M} UTC',file=sys.stderr)
                if len(records)==1:selected=records[0].id
                else:
                    if not sys.stdin.isatty():raise ValueError('Wybierz w terminalu lub użyj --ticket')
                    try:i=int(input('Numer ticketu: '))-1
                    except (ValueError,EOFError):raise ValueError('Anulowano wybór') from None
                    if not 0<=i<len(records):raise ValueError('Niepoprawny numer')
                    selected=records[i].id
            ticket=bridge.store.get_ticket(selected)
            if ticket is None:raise ValueError('Nieznany ticket')
            if args.ticket_action=='show':
                result={'id':ticket.id,'title':ticket.name,'status':ticket.status.value,'executor':ticket.executor.handler,'description':ticket.description,'execution':ticket.execution.model_dump(mode='json') if ticket.execution else None,'last_run':ticket.source.context.get('last_execution'),'github':ticket.sync.get('github',{}).get('url')}
            elif args.ticket_action=='run':
                payload={'kind':'develop','name':args.project,'cycles':1,'ticket_id':selected}
                if getattr(args,'authorize',False): payload['authorize']=True
                result=request('/api/job',payload)
            else:result=bridge.sync(selected,args.direction)
    if getattr(args,'json',False):print(json.dumps(result,ensure_ascii=False,indent=2))
    elif isinstance(result,list):
        for row in result:print(f"{row['id']} · {row['name']} · {row['status']} · {row['executor']}")
    else:
        for key,value in result.items():
            if value is not None:
                if isinstance(value,dict):print(str(key)+': '+' · '.join(str(k)+'='+str(v) for k,v in value.items() if v is not None))
                else:print(str(key)+': '+str(value))
    if args.ticket_action=='list' and not result:print('Brak ticketów. Dodaj: tickets create '+args.project+' --title "Cel zadania"')
    if args.ticket_action=='show' and not getattr(args,'json',False):project_status(args.project)

def project_status(name,raw=False):
    rows=request('/api/projects')
    if name not in rows:raise ValueError('Nieznany projekt')
    project=rows[name];state=request('/api/state');bound=state.get('project')==name
    value={'project':project,'execution':state if bound else None}
    if raw:print(json.dumps(value,ensure_ascii=False,indent=2));return
    print('Cel: '+project['goal'])
    print('Kod: '+project['path'])
    print('Testy: '+shlex.join(project.get('test_argv',[])))
    print('Workspace: '+project['workspace_ref'] if project.get('workspace_ref') else 'Workspace: prywatna kopia kodu; zgodność runtime PC niepotwierdzona')
    if bound:
        print('Pętla: '+state.get('status','?')+' · etap: '+state.get('phase','?')+' · ticket: '+str(state.get('ticket_id','brak')))
        process=state.get('process') or {}
        if process:print('Proces: '+str(process.get('name'))+' · '+str(process.get('status'))+' · PID kontenera: '+str(process.get('pid')))
        if state.get('error'):print('Powód: '+state['error'])
        for event in state.get('history',[])[-3:]:print('Wynik: '+str(event.get('ticket_id','?'))+' · '+event.get('solution','?')+' · '+event.get('status','?'))
    else:print('Pętla: brak zapisanego uruchomienia dla tego projektu w bieżącym stanie')
    if project.get('result_path'):print('Raport: '+project['result_path'])
    print('Tickety: tickets show '+name+' · zarządzanie: project open '+name)


def show_menu(raw=False):
    value=request('/api/overview')
    if raw:
        print(json.dumps(value,ensure_ascii=False,indent=2));return value['actions']
    print(color('\nGITIVE','bold'))
    human('\n'.join(value['lines']))
    value['actions'] = [*value['actions'], {'label':'Synchronizacja PC → noVNC — instrukcja','argv':['sync-help']}]
    print(color('\nDostępne kroki:','bold'))
    for i,action in enumerate(value['actions'],1):
        print(color(str(i)+'.','bold')+' '+action['label'])
    print('Bash: ./gitive menu NUMER · tryb interaktywny: ./gitive shell')
    return value['actions']

if __package__:from .shell import ContextShell
else:from shell import ContextShell

class Shell(ContextShell):
    def __init__(self):
        super().__init__(request,main,ticket_records,show_menu,color,sync_help)

if __name__=='__main__':
    try:main()
    except (RuntimeError,ValueError,OSError) as exc:raise SystemExit(str(exc))
