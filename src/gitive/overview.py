"""Read-only application overview shared by the terminal and web menus."""
STATUS={'idle':'bezczynna','running':'w toku','stopping':'zatrzymywanie','stopped':'zatrzymana','complete':'zakończona','blocked':'zablokowana','error':'błąd','failed':'błąd','interrupted':'przerwana'}

def overview(app,workspace,inventory,projects):
    snapshots=inventory.get('snapshots',[]);clones=inventory.get('clones',[])
    profiles=inventory.get('profiles',[])
    busy=app.get('status') in ('running','stopping') or workspace.get('status')=='running'
    lines=[f"Pętla aplikacji: {STATUS.get(app.get('status'),app.get('status','brak danych'))} · {app.get('phase') or 'brak aktywnego etapu'}",
           f"Ostatnia operacja workspace: {workspace.get('operation','brak')} · {STATUS.get(workspace.get('status'),workspace.get('status','brak danych'))}"]
    if app.get('error'):lines.append('Powód zatrzymania pętli: '+str(app['error'])[:500])
    if workspace.get('error'):lines.append('Błąd workspace: '+str(workspace['error'])[:500])
    result=workspace.get('result') or {}
    if workspace.get('operation')=='snapshot' and workspace.get('status')=='complete':
        lines.append('Ostatni snapshot: '+str(result.get('id','?')))
        lines.append('Profile w tym snapshocie: '+(', '.join(result.get('sessions',[])) or 'brak — nie skopiowano przeglądarki'))
    lines.append(f"Zapisane zasoby: {len(snapshots)} snapshotów, {len(clones)} kopii projektów, {len(profiles)} snapshotów profilu noVNC, {len(projects)} projektów developmentu.")
    for row in snapshots[-5:]:lines.append('Archiwum: '+row['id']+' · '+row.get('project','')+' · profile: '+(', '.join(row.get('sessions',[])) or 'brak'))
    for row in clones[-5:]:lines.append('Kopia: '+row['id']+' · '+row['source']+' → '+row['target'])
    for name,row in list(projects.items())[-5:]:lines.append('Development: '+name+' · '+str(row.get('status','brak statusu'))+' · '+str(row.get('solution','rozwiązanie jeszcze niewybrane')))
    lines.append('Snapshot to archiwum; clone to odtworzona kopia. Profile PC pozostają offline, a oryginały PC są tylko do odczytu.')
    actions=[{'label':'Odśwież menu i stan','argv':['menu'],'anchor':'overview'},
             {'label':'Szczegóły ostatniej operacji','argv':['workspace','status'],'anchor':'workspace-state'},
             {'label':'Lista snapshotów, kopii i profili','argv':['workspace','inspect'],'anchor':'workspace-inventory'},
             {'label':'Projekty developmentu','argv':['project','list'],'anchor':'projects'},
             {'label':'Ranking rozwiązań według benchmarku','argv':['rank'],'anchor':'results'}]
    if busy:
        lines.append('Operacja trwa. Poczekaj na zakończenie przed kopiowaniem lub resync.')
    else:
        actions.append({'label':'Utwórz snapshot projektu i wybranej przeglądarki — instrukcja / formularz','argv':['workspace','snapshot','--help'],'anchor':'ws-snapshot-form'})
        if snapshots:actions.append({'label':'Odtwórz snapshot jako kopię — instrukcja / formularz','argv':['workspace','clone','--help'],'anchor':'ws-clone-form'})
        if clones:actions.append({'label':'Podgląd resync istniejącej kopii wraz z profilami','argv':['workspace','resync','--include-sessions'],'anchor':'ws-sync-form'})
        else:lines.append('Następny krok: utwórz snapshot własnego projektu z wybraną przeglądarką, a następnie wykonaj clone. Brak kopii do resync.')
    return {'lines':lines,'actions':actions,'busy':busy,'counts':{'snapshots':len(snapshots),'clones':len(clones),'profiles':len(profiles),'projects':len(projects)}}
