"""Local HTTP client and interactive gitive shell."""
import argparse
import cmd
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

def request(path,body=None):
    headers={}
    if body is not None:
        page=urllib.request.urlopen(URL,timeout=5).read().decode()
        headers={'Content-Type':'application/json','X-Loop-Token':re.search(r"const token='([^']+)'",page)[1]}
    req=urllib.request.Request(URL+path,data=json.dumps(body).encode() if body is not None else None,headers=headers)
    try:
        with urllib.request.urlopen(req,timeout=20) as r:return json.load(r)
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
    for name in ('status','rank','benchmark','shell','stop','menu','sync-help'):sub.add_parser(name)
    project=sub.add_parser('project').add_subparsers(dest='operation',required=True)
    project.add_parser('list')
    add=project.add_parser('add');add.add_argument('name');add.add_argument('path');add.add_argument('--goal',required=True);add.add_argument('--test',required=True);add.add_argument('--allow',default='src')
    run=project.add_parser('run');run.add_argument('name');run.add_argument('--cycles',type=int,default=3)
    watch=project.add_parser('watch');watch.add_argument('name');watch.add_argument('--interval',type=int,default=60)
    tickets=sub.add_parser('tickets').add_subparsers(dest='ticket_action',required=True)
    for action in ('list','create','sync'):
        tp=tickets.add_parser(action);tp.add_argument('project')
        if action=='create':
            tp.add_argument('--title',required=True);tp.add_argument('--engine',choices=['glm53','gpt6','opus5'],required=True);tp.add_argument('--key',required=True)
        if action=='sync':
            tp.add_argument('--ticket');tp.add_argument('--repo',required=True);tp.add_argument('--direction',choices=['push','pull'],required=True)
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
    if a.cmd=='shell':return Shell().cmdloop()
    if a.cmd=='tickets':return ticket_command(a)
    if a.cmd=='sync-help':return sync_help()
    if a.cmd=='menu':return show_menu(getattr(a,'json',False))
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
    elif a.cmd=='rank':result=request('/api/rank')
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
def ticket_command(args):
    if __package__:from .planfile_bridge import PlanfileBridge
    else:from planfile_bridge import PlanfileBridge
    rows=request('/api/projects')
    if args.project not in rows or not rows[args.project].get('copy_only'):raise ValueError('Najpierw zarejestruj prywatną kopię projektu')
    registered=Path(rows[args.project]['path'])
    root=registered if registered.is_dir() else Path(os.getenv('GITIVE_ISOLATION_ROOT',str(Path.home()/'.local/share/gitive-isolated')))/'github'/registered.relative_to('/workspace/github')
    if not root.is_dir():raise ValueError('Kopia projektu jest niedostępna na tym hoście')
    bridge=PlanfileBridge(root,getattr(args,'repo',None))
    if args.ticket_action=='create':
        ticket=bridge.ensure(args.key,args.title,args.engine,'Gitive integration ticket; no autonomous repair or merge authorization.')
        result={'id':ticket.id,'title':ticket.name,'executor':args.engine}
    else:
        records=[t for t in bridge.store.list_tickets(sprint='gitive') if t.source and t.source.tool=='gitive']
        if args.ticket_action=='list':
            result=[{'id':t.id,'name':t.name,'status':t.status.value,'executor':t.executor.handler,'github':t.sync.get('github',{}).get('url')} for t in records]
        else:
            selected=args.ticket
            if not selected:
                if not records:raise ValueError('Brak lokalnych ticketów Gitive')
                for i,t in enumerate(records,1):print(f'{i}. {t.name} · {t.created_at:%Y-%m-%d %H:%M} UTC')
                if len(records)==1:selected=records[0].id
                else:
                    if not sys.stdin.isatty():raise ValueError('Wybierz w terminalu lub użyj --ticket')
                    try:i=int(input('Numer ticketu: '))-1
                    except (ValueError,EOFError):raise ValueError('Anulowano wybór') from None
                    if not 0<=i<len(records):raise ValueError('Niepoprawny numer')
                    selected=records[i].id
            result=bridge.sync(selected,args.direction)
    if getattr(args,'json',False):print(json.dumps(result,ensure_ascii=False,indent=2))
    elif isinstance(result,list):
        for row in result:print(f"{row['id']} · {row['name']} · {row['status']} · {row['executor']}")
    else:print(' · '.join(str(v) for v in result.values()))

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
    return value['actions']

class Shell(cmd.Cmd):
    intro='Wybierz numer · sync: instrukcja PC → noVNC · menu: odśwież · exit: wyjdź';prompt='gitive> '
    def preloop(self):self.do_menu('')
    def do_sync(self,arg):
        """Pokaż instrukcję kopiowania i aktualizacji PC → noVNC."""
        sync_help()
    def do_pomoc(self,arg):sync_help()
    def do_menu(self,arg):
        try:self.menu_actions=show_menu()
        except Exception as exc:print(color('Nie można odczytać stanu: '+str(exc),'red'));self.menu_actions=[]
    def emptyline(self):pass
    def default(self,line):
        try:
            if line.strip().isdigit():
                index=int(line.strip())-1
                if not 0<=index<len(getattr(self,'menu_actions',[])):raise ValueError('Niepoprawny numer. Wpisz menu.')
                main(self.menu_actions[index]['argv'])
            else:main(shlex.split(line))
        except (Exception,SystemExit) as exc:
            if isinstance(exc,SystemExit) and exc.code in (None,0):return
            print(color(str(exc),'red'))
    def do_exit(self,arg):return True
    def do_EOF(self,arg):return True
if __name__=='__main__':
    try:main()
    except (RuntimeError,ValueError,OSError) as exc:raise SystemExit(str(exc))
