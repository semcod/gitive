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
def request(path,body=None):
    headers={}
    if body is not None:
        page=urllib.request.urlopen(URL,timeout=5).read().decode()
        headers={'Content-Type':'application/json','X-Loop-Token':re.search(r"const token='([^']+)'",page)[1]}
    req=urllib.request.Request(URL+path,data=json.dumps(body).encode() if body is not None else None,headers=headers)
    try:
        with urllib.request.urlopen(req,timeout=20) as r:return json.load(r)
    except urllib.error.HTTPError as exc:raise RuntimeError(json.load(exc).get('error',str(exc))) from None

def choose_clone():
    clones=request('/api/workspace').get('clones',[])
    if not clones:
        raise ValueError("""Brak kopii do synchronizacji. Przygotuj pierwszą kopię:

1. Zatrzymaj pętlę:
   ./gitive stop

2. Wybierz repozytorium względem ~/github, np. organizacja/projekt.
   Zastąp tę przykładową ścieżkę własną; wybierz repo inne niż kontroler Gitive.
   Zamknij Firefox na PC przed kopiowaniem jego profilu:
   ./gitive workspace snapshot pc-firefox --project organizacja/projekt --browser firefox
   Przeglądarki: firefox | chrome | chromium | all | none.
   Opcjonalnie dodaj --include-sessions, aby skopiować też obsługiwane sesje CLI/LLM/IDE.

3. Poczekaj na zakończenie i odczytaj SNAPSHOT_ID z wyniku:
   ./gitive workspace status
   ./gitive workspace inspect
   Jeśli masz już snapshot, możesz pominąć krok 2 i użyć jego ID z inspect.

4. Zastąp SNAPSHOT_ID otrzymanym ID. Cel musi być nowym katalogiem w kopiach:
   ./gitive workspace clone SNAPSHOT_ID --target kopie/moj-projekt
   ./gitive workspace status
   Poczekaj na zakończenie clone.

5. Teraz sprawdź zmiany, również w skopiowanym profilu:
   ./gitive workspace resync --include-sessions
   ./gitive workspace status
   Po zakończeniu podglądu zastosuj zmiany:
   ./gitive workspace resync --apply --include-sessions

Oryginały PC pozostają bez zmian. Profile są kopiami offline;
nie uruchamiają automatycznie przeglądarki w noVNC.""")
    if len(clones)==1:
        selected=clones[0]
    else:
        if not sys.stdin.isatty():
            raise ValueError('Jest kilka kopii. Podaj CLONE_ID: '+', '.join(c['id'] for c in clones))
        for i,c in enumerate(clones,1):
            print(f"{i}. {c['source']} → {c['target']} [{c['id']}]",file=sys.stderr)
        try:
            index=int(input('Numer kopii do synchronizacji: '))-1
        except (ValueError,EOFError):
            raise ValueError('Nie wybrano poprawnego numeru kopii') from None
        if not 0<=index<len(clones):raise ValueError('Niepoprawny numer kopii')
        selected=clones[index]
    print(f"Kopia: {selected['source']} → {selected['target']} [{selected['id']}]",file=sys.stderr)
    return selected['id']

def status_hint(state):
    lines=['To zapis ostatniej operacji. Polecenie status nie tworzy ani nie aktualizuje kopii.']
    status=state.get('status')
    if status=='running':
        lines.append('Operacja trwa. Sprawdź ponownie: ./gitive workspace status')
    elif status=='complete':
        result=state.get('result') or {}
        operation=state.get('operation')
        if operation=='snapshot':
            sessions=result.get('sessions',[])
            lines.append('Snapshot zapisano jako archiwum; nie oznacza to wykonania clone ani uruchomienia przeglądarki.')
            lines.append('Skopiowane profile/sesje: '+(', '.join(sessions) if sessions else 'BRAK. Ten snapshot nie zawiera profili przeglądarek.'))
            if '.subactor/recovery/' in result.get('project',''):
                lines.append('Źródło znajduje się w katalogu recovery; nie jest to profil przeglądarki PC.')
            if not sessions:
                lines.extend(['Aby skopiować Firefox, zamknij go na PC, zastąp organizacja/projekt własnym repo i wykonaj:',
                    '  ./gitive workspace snapshot pc-firefox --project organizacja/projekt --browser firefox',
                    '  ./gitive workspace status'])
            if result.get('id'):
                lines.extend(['Jeśli chcesz odtworzyć właśnie ten snapshot projektu (wybierz nieistniejący katalog celu):',
                    '  ./gitive workspace clone '+shlex.quote(result['id'])+' --target kopie/moj-projekt'])
        elif operation=='clone':
            lines.append('Kopia gotowa. Profile pozostają offline; noVNC nie uruchamia ich automatycznie.')
            if result.get('id'):lines.append('Podgląd aktualizacji: ./gitive workspace resync '+shlex.quote(result['id'])+' --include-sessions')
        elif operation=='resync':
            if result.get('conflict_count') or result.get('session_conflict_count'):
                lines.append('Wykryto konflikty. Sprawdź raport przed kolejną synchronizacją.')
            elif result.get('dry_run'):
                lines.append('To tylko podgląd. Zapis: ./gitive workspace resync '+shlex.quote(str(result.get('clone','CLONE_ID')))+' --apply'+(' --include-sessions' if state.get('request',{}).get('include_sessions') else ''))
            else:lines.append('Sprawdź applied w raporcie; complete oznacza zakończenie operacji, niekoniecznie zmianę plików.')
    elif status in ('error','failed','interrupted'):
        lines.append('Operacja nie została pomyślnie zakończona. Sprawdź komunikat błędu przed ponowieniem.')
    return '\n'.join(lines)

def main(argv=None):
    p=argparse.ArgumentParser(prog='gitive');sub=p.add_subparsers(dest='cmd',required=True)
    for name in ('status','rank','benchmark','shell','stop','menu'):sub.add_parser(name)
    project=sub.add_parser('project').add_subparsers(dest='operation',required=True)
    project.add_parser('list')
    add=project.add_parser('add');add.add_argument('name');add.add_argument('path');add.add_argument('--goal',required=True);add.add_argument('--test',required=True);add.add_argument('--allow',default='src')
    run=project.add_parser('run');run.add_argument('name');run.add_argument('--cycles',type=int,default=3)
    watch=project.add_parser('watch');watch.add_argument('name');watch.add_argument('--interval',type=int,default=60)
    ws=sub.add_parser('workspace').add_subparsers(dest='ws',required=True)
    for name in ('inspect','status','inventory'):ws.add_parser(name)
    snap=ws.add_parser('snapshot');snap.add_argument('name');snap.add_argument('--project',required=True,help='Ścieżka względem ~/github');snap.add_argument('--include-sessions',action='store_true');snap.add_argument('--browser',choices=['none','all','firefox','chrome','chromium'],default='none')
    clone=ws.add_parser('clone');clone.add_argument('snapshot');clone.add_argument('--target',required=True,help='Nowy katalog w prywatnym magazynie kopii')
    sync=ws.add_parser('resync');sync.add_argument('clone',nargs='?',help='ID kopii; pomiń, aby wybrać automatycznie lub z listy');sync.add_argument('--include-sessions',action='store_true');mode=sync.add_mutually_exclusive_group();mode.add_argument('--apply',action='store_true');mode.add_argument('--dry-run',action='store_true')
    resume=ws.add_parser('resume');resume.add_argument('clone');resume.add_argument('--application',choices=['terminal','vscode','cursor'],default='terminal')
    profile=ws.add_parser('profile');profile.add_argument('action',choices=['snapshot','restore']);profile.add_argument('--browser',choices=['all','chrome','chromium','firefox'],default='all');profile.add_argument('--snapshot')
    a=p.parse_args(argv)
    if a.cmd=='shell':return Shell().cmdloop()
    if a.cmd=='menu':return show_menu()
    if a.cmd=='workspace':
        if a.ws in ('inspect','status'):result=request('/api/workspace'+('/state' if a.ws=='status' else ''))
        else:
            body={k:v for k,v in vars(a).items() if k not in ('cmd','ws','apply','dry_run')}
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
    print(json.dumps(result,ensure_ascii=False,indent=2))
    if a.cmd=='workspace' and a.ws=='status':print("\n"+status_hint(result),file=sys.stderr)
def show_menu():
    value=request('/api/overview')
    print('\nGITIVE — stan aplikacji\n')
    print('\n'.join(value['lines']))
    print('\nDostępne kroki:')
    for i,action in enumerate(value['actions'],1):
        print(f"{i}. {action['label']}\n   ./gitive {shlex.join(action['argv'])}")
    return value['actions']

class Shell(cmd.Cmd):
    intro='Wpisz menu lub numer wybranej pozycji. Gitive: benchmark | rank | status | project add/list/run | stop | workspace inspect/snapshot/clone/resync/resume/profile | exit';prompt='gitive> '
    def preloop(self):self.do_menu('')
    def do_menu(self,arg):
        try:self.menu_actions=show_menu()
        except Exception as exc:print('Nie można odczytać stanu: '+str(exc));self.menu_actions=[]
    def emptyline(self):pass
    def default(self,line):
        try:
            if line.strip().isdigit():
                index=int(line.strip())-1
                if not 0<=index<len(getattr(self,'menu_actions',[])):raise ValueError('Niepoprawny numer. Wpisz menu.')
                main(self.menu_actions[index]['argv'])
            else:main(shlex.split(line))
        except (Exception,SystemExit) as exc:print(str(exc))
    def do_exit(self,arg):return True
    def do_EOF(self,arg):return True
if __name__=='__main__':
    try:main()
    except (RuntimeError,ValueError,OSError) as exc:raise SystemExit(str(exc))
