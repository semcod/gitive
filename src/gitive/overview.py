"""Read-only application overview shared by the terminal and web menus."""
STATUS={'idle':'bezczynna','running':'w toku','stopping':'zatrzymywanie','stopped':'zatrzymana','complete':'zakończona','blocked':'zablokowana','error':'błąd','failed':'błąd','interrupted':'przerwana'}

def overview(app,workspace,inventory,projects):
    snapshots=inventory.get('snapshots',[]);clones=inventory.get('clones',[])
    profiles=inventory.get('profiles',[])
    busy=app.get('status') in ('running','stopping') or workspace.get('status')=='running'
    lines=[f"Pętla aplikacji: {STATUS.get(app.get('status'),app.get('status','brak danych'))}",
           f"Ostatnia operacja workspace: {workspace.get('operation','brak')} · {STATUS.get(workspace.get('status'),workspace.get('status','brak danych'))}"]
    if app.get('error'):lines.append('Powód zatrzymania pętli: '+str(app['error'])[:500])
    if workspace.get('error'):lines.append('Błąd workspace: '+str(workspace['error'])[:500])
    result=workspace.get('result') or {}
    if workspace.get('operation')=='snapshot' and workspace.get('status')=='complete':
        lines.append('Profile w tym snapshocie: '+(', '.join(result.get('sessions',[])) or 'brak — nie skopiowano przeglądarki'))
    lines.append(f"Archiwa: {len(snapshots)} | Kopie: {len(clones)} | Projekty: {len(projects)}")
    provisioned=sum(bool(p.get('workspace_ref')) for p in projects.values())
    if provisioned:lines.append('Zarejestrowane środowiska projektów DigitalTwin: '+str(provisioned)+' · stan: twin status NAZWA')
    actions=[{'label':'Odśwież','argv':['menu'],'anchor':'overview'},
             {'label':'Ostatnia operacja','argv':['workspace','status'],'anchor':'workspace-state'},
             {'label':'Archiwa i kopie','argv':['workspace','inspect'],'anchor':'workspace-inventory'},
             {'label':'Wybierz projekt — tickety, procesy, wyniki','argv':['project','open'],'anchor':'projects'},
             {'label':'Ranking','argv':['rank'],'anchor':'results'}]
    if busy:
        lines.append('Operacja trwa. Poczekaj na zakończenie przed kopiowaniem lub resync.')
    else:
        actions.append({'label':'Dodaj projekt z PC — kreator','argv':['project','new'],'anchor':'projects'})
        actions.append({'label':'Nowy snapshot','argv':['workspace','snapshot','--help'],'anchor':'ws-snapshot-form'})
        if snapshots:actions.append({'label':'Odtwórz kopię','argv':['workspace','clone'],'anchor':'ws-clone-form'})
        if clones:actions.append({'label':'Podgląd resync','argv':['workspace','resync','--include-sessions'],'anchor':'ws-sync-form'})
        else:lines.append('Dalej: snapshot → clone. Brak kopii do resync.')
    return {'lines':lines,'actions':actions,'busy':busy,'counts':{'snapshots':len(snapshots),'clones':len(clones),'profiles':len(profiles),'projects':len(projects)}}
