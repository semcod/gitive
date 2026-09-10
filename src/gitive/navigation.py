"""Interactive project navigation; mutations use the same CLI/API as scripts."""
from pathlib import Path
import os
import shlex
from urllib.parse import quote


def choose(rows,label):
    if not rows:raise ValueError('Brak pozycji: '+label)
    print('\n'+label)
    for i,(name,_) in enumerate(rows,1):print(f'{i}. {name}')
    try:n=int(input('Numer (0 = powrót): '))
    except (ValueError,EOFError):return None
    if n==0:return None
    if not 1<=n<=len(rows):raise ValueError('Niepoprawny numer')
    return rows[n-1][1]


def select_folder(request):
    current=''
    while True:
        data=request('/api/folders?path='+quote(current))
        choices=[]
        if data['is_repo']:choices.append(('Wybierz ten projekt: '+current,('select',current)))
        if data.get('parent') is not None:choices.append(('..',('browse',data['parent'])))
        choices += [(x['name'],('browse',x['path'])) for x in data['folders']]
        answer=choose(choices,'Foldery ~/github/'+current)
        if answer is None:return None
        if answer[0]=='select':return answer[1]
        current=answer[1]


def new_project(main,request):
    relative=select_folder(request)
    if relative is None:return
    name=input('Nazwa projektu ['+Path(relative).name+']: ').strip() or Path(relative).name
    goal=input('Cel projektu: ').strip()
    test=input('Komenda testów (np. python3 -m pytest): ').strip()
    allowed=input('Katalog kodu dopuszczony do zmian [src]: ').strip() or 'src'
    if not goal or not test:raise ValueError('Cel i komenda testów są wymagane')
    path=str(Path(os.getenv('GITIVE_GITHUB_ROOT','/home/tom/github'))/relative)
    main(['project','add',name,path,'--goal',goal,'--test',test,'--allow',allowed])
    print('Utworzono prywatną kopię kodu. Dokładny runtime projektu nie został jeszcze sklonowany.')
    project_menu(name,main,request)


def project_menu(name,main,request):
    projects=request('/api/projects')
    if not name:
        name=choose([(n+' · '+p.get('status','?'),n) for n,p in projects.items()],'Wybierz projekt')
    if name is None:return
    if name not in projects:raise ValueError('Nieznany projekt')
    while True:
        print('\nPROJEKT: '+name)
        main(['project','status',name])
        action=choose([(label,key) for key,label in [
            ('tickets','Tickety: lista i szczegóły'),('create','Dodaj ticket'),
            ('run-ticket','Uruchom wybrany ticket'),('sync','Synchronizacja ticketu z GitHub'),
            ('status','Odśwież procesy i wyniki'),('run','Uruchom diagnozę celu projektu (1 cykl)'),
            ('workspace','DigitalTwin: plan / przygotowanie / test środowiska'),('stop','Zatrzymaj pętlę tego projektu')]],'Działania')
        if action is None:return
        try:
            if action=='tickets':
                main(['tickets','show',name])
            elif action=='create':
                title=input('Tytuł: ').strip();description=input('Oczekiwany wynik / kryterium odbioru: ').strip()
                engine=choose([('Najlepszy według aktualnego benchmarku','auto'),('GLM53','glm53'),('GPT6','gpt6'),('Opus5','opus5')],'Wykonawca')
                if engine and title:main(['tickets','create',name,'--title',title,'--description',description,'--engine',engine])
            elif action=='run-ticket':main(['tickets','run',name])
            elif action=='sync':
                repo=input('Repo GitHub (owner/repo): ').strip()
                direction=choose([('Lokalny → GitHub','push'),('GitHub → lokalny','pull')],'Kierunek')
                if repo and direction:main(['tickets','sync',name,'--repo',repo,'--direction',direction])
            elif action=='status':main(['project','status',name])
            elif action=='run':main(['project','run',name,'--cycles','1'])
            elif action=='workspace':
                choice=choose([('Podgląd pełnej kopii środowiska','plan'),('Utwórz prywatne środowisko projektu','prepare'),('Stan kontenera i wersje','status'),('Testy w środowisku projektu','test')],'DigitalTwin')
                if choice:main(['twin',choice,name])
            elif action=='stop':
                state=request('/api/state')
                if state.get('project')!=name or state.get('status') not in ('running','stopping'):print('Ten projekt nie ma aktywnej pętli.')
                else:main(['stop'])
        except (RuntimeError,ValueError,OSError) as exc:print('Błąd: '+str(exc))
