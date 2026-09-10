"""Encrypted workspace copies, conservative resync and existing Hub adapters."""
import hashlib
import inspect
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tarfile
import tempfile
import threading
import time
import uuid
from .engine import write
from .hub import Hub

SESSIONS=('.codex','.claude','.aider.conf.yml','.continue','.config/Code/User','.config/Cursor/User','.config/subactor-shell','.bash_history','.zsh_history','.tmux.conf')
BROWSERS={'firefox':'.mozilla/firefox','chrome':'.config/google-chrome','chromium':'.config/chromium'}
SKIP={'.subactor','node_modules','.venv','venv','__pycache__','.cache','Cache','GPUCache','Code Cache'}

def execute(argv,**kw):
    r=subprocess.run(argv,capture_output=True,timeout=kw.pop('timeout',300),**kw)
    if r.returncode:raise RuntimeError('Niepowodzenie narzędzia '+Path(argv[0]).name+'; kod '+str(r.returncode))
    return r.stdout

def digest(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream,"sha256").hexdigest()

def link_target(path):
    raw=Path(os.readlink(path))
    if not raw.is_absolute():return (path.parent/raw).resolve()
    aliases=[(Path(os.getenv('GITIVE_PC_HOME','/home/tom')),os.getenv('GITIVE_HOST_HOME')),
             (Path(os.getenv('GITIVE_GITHUB_ROOT','/home/tom/github')),os.getenv('GITIVE_SOURCE_ROOT'))]
    for original,alias in aliases:
        if alias and path.is_relative_to(Path(alias)) and raw.is_relative_to(original):
            return (Path(alias)/raw.relative_to(original)).resolve()
    return raw.resolve()

def files(root):
    result={}
    for directory,dirs,names in os.walk(root,followlinks=False):
        dirs[:]=sorted(d for d in dirs if d not in SKIP)
        for name in sorted(names+ [d for d in dirs if (Path(directory)/d).is_symlink()]):
            p=Path(directory)/name;key=str(p.relative_to(root))
            if p.is_symlink():
                target=os.readlink(p)
                if not link_target(p).is_relative_to(Path(root).resolve()):raise ValueError('Symlink poza wybranym drzewem: '+key)
                if Path(target).is_absolute():target=os.path.relpath(link_target(p),p.parent)
                result[key]='link:'+target
            elif p.is_file():
                result[key]=digest(p)+':'+oct(p.stat().st_mode&0o777)
            else:raise ValueError('Nieobsługiwany plik specjalny: '+key)
    return result

def copy(source,target):
    shutil.copytree(source,target,symlinks=True,ignore=lambda _,names:set(names)&SKIP)
    for directory,dirs,names in os.walk(target,followlinks=False):
        for name in dirs+names:
            link=Path(directory)/name
            if link.is_symlink() and Path(os.readlink(link)).is_absolute():
                original=Path(source)/link.relative_to(target)
                if not link_target(original).is_relative_to(Path(source).resolve()):raise ValueError('Symlink poza źródłem')
                relative=os.path.relpath(link_target(original),original.parent)
                link.unlink();link.symlink_to(relative)

class Workspace:
    def __init__(self,root,data,hub=None,workspace='/workspace/github',home=None,source_workspace=None):
        self.root=Path(root).resolve();self.data=Path(data)/'workspaces';self.data.mkdir(parents=True,exist_ok=True,mode=0o700)
        self.sources=Path(source_workspace or (os.getenv('GITIVE_SOURCE_ROOT',workspace) if workspace=='/workspace/github' else workspace)).resolve()
        self.workspace=Path(workspace).resolve();self.home=Path(home or os.getenv('GITIVE_HOST_HOME','/host-home'))
        self.browser_paths=dict(BROWSERS)
        snap_firefox='snap/firefox/common/.mozilla/firefox'
        if (self.home/snap_firefox/'profiles.ini').is_file():self.browser_paths['firefox']=snap_firefox
        self.hub=hub or Hub();self.lock=threading.Lock();self.thread=None
        self.status_file=self.data/'status.json'
        self.state=json.loads(self.status_file.read_text()) if self.status_file.exists() else {'status':'idle'}
        if self.state.get('status')=='running':self.state.update(status='interrupted',error='Operacja przerwana; sprawdź zapis przed ponowieniem');write(self.status_file,self.state)
    def path(self,relative,existing=True):
        if not isinstance(relative,str) or Path(relative).is_absolute():raise ValueError('Podaj ścieżkę względem ~/github')
        p=(self.workspace/relative).resolve()
        if p==self.workspace or not p.is_relative_to(self.workspace) or (existing and not p.is_dir()):raise ValueError('Niedozwolony lub nieistniejący katalog')
        if p==self.root or p in self.root.parents:raise ValueError('Wybierz osobne repozytorium; katalog kontrolera nie jest przenośnym projektem')
        return p
    def source_path(self,relative):
        if not isinstance(relative,str) or Path(relative).is_absolute():raise ValueError('Ścieżka źródłowa musi być względna')
        p=(self.sources/relative).resolve()
        if p==self.sources or not p.is_relative_to(self.sources) or not p.is_dir():raise ValueError('Źródło poza katalogiem PC')
        return p
    def inspect(self):
        return {'sessions':[{'path':n,'present':(self.home/n).exists()} for n in SESSIONS],
                'browsers':[{'browser':n,'path':p,'present':(self.home/p).exists()} for n,p in self.browser_paths.items()],
                'tools':{n:bool(shutil.which(n)) for n in ('age','age-keygen','llm-accounts')},
                'snapshots':[json.loads(p.read_text()) for p in sorted(self.data.glob('*/manifest.json'))],
                'clones':[{k:v for k,v in json.loads(p.read_text()).items() if k not in ('baseline','session_baseline')} for p in sorted(self.data.glob('clones/*.json'))],
                'profiles':[json.loads(p.read_text()) for p in sorted(self.data.glob('profiles/*.json'))],
                'isolation':{'source':str(self.sources),'copies':str(self.workspace),'direction':'PC read-only → private copy'},
                'limitations':['Procesy i pamięć RAM nie są kopiowane','Resume otwiera aplikację; polecenie wznowienia rozmowy zależy od klienta','Profile przeglądarek obsługuje osobno Hub; snapshot zatrzymuje jego kontener','Resync blokuje każdą własną zmianę w kopii docelowej']}
    def snapshot(self,name,project,include_sessions=False,browser='none',exclude_sessions=None):
        if not re.fullmatch(r'[a-z][a-z0-9-]{1,40}',name):raise ValueError('Nazwa: 2–41 małych liter/cyfr/myślników')
        if type(include_sessions) is not bool:raise ValueError('Niepoprawny wybór sesji')
        if browser not in ('none','all',*BROWSERS):raise ValueError('Niepoprawna przeglądarka')
        exclude_sessions=exclude_sessions or []
        if not isinstance(exclude_sessions,list) or any(n not in SESSIONS for n in exclude_sessions):raise ValueError('Niepoprawne wykluczenie sesji')
        source=self.source_path(project)
        if not (source/'.git').is_dir():raise ValueError('Snapshot wymaga repo z lokalnym katalogiem .git; worktree z zewnętrznym .git wymaga osobnego eksportu')
        if (source/'.git/objects/info/alternates').exists():raise ValueError('Repo używa zewnętrznych obiektów Git; wymagany samodzielny eksport')
        stamp=time.strftime('%Y%m%dT%H%M%SZ',time.gmtime())+'-'+uuid.uuid4().hex[:6];sid=name+'-'+stamp
        destination=self.data/sid;destination.mkdir(mode=0o700)
        identity=self.data/'identity.age'
        if not identity.exists():execute(['age-keygen','-o',str(identity)]);identity.chmod(0o600)
        recipient=execute(['age-keygen','-y',str(identity)]).decode().strip()
        with tempfile.TemporaryDirectory(dir=self.data,prefix='.capture-') as tmp:
            temp=Path(tmp);before=files(source);copy(source,temp/'project')
            if before!=files(source) or before!=files(temp/'project'):raise RuntimeError('Źródło zmieniło się podczas snapshotu')
            sessions=[]
            selected=[n for n in SESSIONS if n not in exclude_sessions] if include_sessions else []
            selected += list(self.browser_paths.values()) if browser=='all' else ([self.browser_paths[browser]] if browser in self.browser_paths else [])
            if selected:
                for n in selected:
                    p=self.home/n
                    if not p.exists():continue
                    out=temp/'sessions'/n;out.parent.mkdir(parents=True,exist_ok=True)
                    if p.is_symlink():raise ValueError('Profil jest symlinkiem; wymagany jawny adapter')
                    if p.is_dir():
                        initial=files(p);copy(p,out)
                        if initial!=files(p) or initial!=files(out):raise RuntimeError('Profil jest aktywny i zmienił się podczas kopii: '+n)
                    else:
                        content=p.read_bytes();shutil.copy2(p,out)
                        if content!=p.read_bytes() or content!=out.read_bytes():raise RuntimeError('Profil zmienił się podczas kopii: '+n)
                    sessions.append(n)
            archive=temp/'payload.tar'
            with tarfile.open(archive,'w') as tar:
                tar.add(temp/'project',arcname='project')
                if sessions:tar.add(temp/'sessions',arcname='sessions')
            execute(['age','-r',recipient,'-o',str(destination/'payload.tar.age'),str(archive)])
        manifest={'id':sid,'project':project,'excluded_sessions':exclude_sessions,'sessions':sessions,'encrypted':True,'excluded_directories':sorted(SKIP),'created':stamp,'archive_sha256':digest(destination/'payload.tar.age')}
        write(destination/'manifest.json',manifest);return manifest
    def snapshot_dir(self,snapshot):
        if not isinstance(snapshot,str) or not re.fullmatch(r'[a-z0-9TZ-]+',snapshot):raise ValueError('Niepoprawny snapshot ID')
        folder=self.data/snapshot
        if not (folder/'manifest.json').is_file():raise ValueError('Nieznany ukończony snapshot')
        return folder
    def clone(self,snapshot,target):
        source=self.snapshot_dir(snapshot);dest=self.path(target,False)
        if dest.exists():raise ValueError('Katalog docelowy już istnieje')
        manifest=json.loads((source/'manifest.json').read_text())
        if dest.is_relative_to(self.source_path(manifest['project'])):raise ValueError('Kopia musi być poza źródłowym repozytorium')
        clone_id=uuid.uuid4().hex
        encrypted=source/'payload.tar.age'
        if digest(encrypted)!=manifest['archive_sha256']:raise ValueError('Niezgodna suma archiwum')
        dest.parent.mkdir(parents=True,exist_ok=True)
        with tempfile.TemporaryDirectory(dir=dest.parent,prefix='.gitive-clone-') as tmp:
            temp=Path(tmp);archive=temp/'payload.tar'
            execute(['age','-d','-i',str(self.data/'identity.age'),'-o',str(archive),str(encrypted)])
            with tarfile.open(archive) as tar:
                for member in tar:
                    if not member.name.startswith(('project/','sessions/')) and member.name not in ('project','sessions'):raise ValueError('Nieprawidłowy zakres archiwum')
                def safe_member(member,destination):
                    filtered=tarfile.data_filter(member,destination)
                    # Restore ordinary source permissions inside the private staging tree.
                    # Keep data_filter path/link checks and drop setuid/setgid/sticky bits.
                    return filtered.replace(mode=member.mode&0o777) if filtered is not None else None
                tar.extractall(temp/'restored',filter=safe_member)
            project=temp/'restored/project';baseline=files(project)
            if (temp/'restored/sessions').exists():
                # Profiles remain offline in a separate home; never overwrite live PC/account profiles.
                copy(temp/'restored/sessions',self.data/('restored-home-'+clone_id))
            project.rename(dest)
        record={'created':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),'id':clone_id,'snapshot':snapshot,'source':manifest['project'],'target':target,'baseline':baseline,'session_paths':manifest['sessions'],
                'session_baseline':files(self.data/('restored-home-'+clone_id)) if manifest['sessions'] else {}}
        write(self.data/'clones'/f'{clone_id}.json',record)
        return {k:v for k,v in record.items() if k not in ('baseline','session_baseline')}
    def resync(self,clone,dry_run=True,include_sessions=False):
        if not re.fullmatch(r'[0-9a-f]{32}',clone):raise ValueError('Niepoprawny clone ID')
        if type(dry_run) is not bool:raise ValueError('dry_run musi być boolean')
        if type(include_sessions) is not bool:raise ValueError('include_sessions musi być boolean')
        record_path=self.data/'clones'/f'{clone}.json';record=json.loads(record_path.read_text())
        source=self.source_path(record['source']);target=self.path(record['target']);baseline=record['baseline'];current=files(target);incoming=files(source)
        conflicts=sorted(k for k in baseline.keys()|current.keys() if baseline.get(k)!=current.get(k))
        changes=sorted(k for k in current.keys()|incoming.keys() if current.get(k)!=incoming.get(k))
        report={'clone':clone,'dry_run':dry_run,'conflicts':conflicts[:200],'conflict_count':len(conflicts),'changes':changes[:200],'change_count':len(changes),'applied':False}
        if include_sessions:
            return self.resync_sessions(record_path,record,report,dry_run,incoming,current)
        if dry_run or conflicts or not changes:return report
        backup=target.with_name(target.name+'.gitive-backup-'+uuid.uuid4().hex[:8])
        with tempfile.TemporaryDirectory(dir=target.parent,prefix='.gitive-resync-') as tmp:
            stage=Path(tmp)/'project';copy(source,stage)
            if files(stage)!=incoming or files(source)!=incoming or files(target)!=current:raise RuntimeError('Zmiana podczas synchronizacji')
            target.rename(backup)
            try:stage.rename(target)
            except Exception:backup.rename(target);raise
        record['baseline']=incoming;write(record_path,record);report.update(applied=True,backup=str(backup.relative_to(self.workspace)));return report
    def resync_sessions(self,record_path,record,report,dry_run,incoming,current):
        paths=record.get('session_paths',[])
        if not paths:raise ValueError('Ta kopia nie zawiera sesji; utwórz snapshot z profilami')
        allowed=set(SESSIONS)|set(BROWSERS.values())
        if not set(paths)<=allowed:raise ValueError('Nieznany zakres sesji')
        home=self.data/('restored-home-'+record['id']);before=files(home)
        with tempfile.TemporaryDirectory(dir=self.data,prefix='.session-sync-') as tmp:
            stage=Path(tmp)/'home';stage.mkdir()
            for n in paths:
                p=self.home/n;out=stage/n;out.parent.mkdir(parents=True,exist_ok=True)
                if not p.exists() or p.is_symlink():raise ValueError('Brak profilu lub symlink: '+n)
                if p.is_dir():
                    initial=files(p);copy(p,out)
                    if initial!=files(p) or initial!=files(out):raise RuntimeError('Profil zmienił się podczas kopii: '+n)
                else:
                    content=p.read_bytes();shutil.copy2(p,out)
                    if content!=p.read_bytes() or content!=out.read_bytes():raise RuntimeError('Profil zmienił się podczas kopii')
            after=files(stage);baseline=record['session_baseline']
            conflicts=['sessions/'+k for k in before.keys()|baseline.keys() if before.get(k)!=baseline.get(k)]
            changes=['sessions/'+k for k in before.keys()|after.keys() if before.get(k)!=after.get(k)]
            report['conflict_count']+=len(conflicts);report['conflicts']=(report['conflicts']+sorted(conflicts))[:200]
            report['change_count']+=len(changes);report['changes']=(report['changes']+sorted(changes))[:200]
            if dry_run or report['conflict_count'] or not report['change_count']:return report
            source=self.source_path(record['source']);target=self.path(record['target'])
            with tempfile.TemporaryDirectory(dir=target.parent,prefix='.gitive-resync-') as project_tmp:
                project=Path(project_tmp)/'project';copy(source,project)
                if files(project)!=incoming or files(source)!=incoming or files(target)!=current or files(home)!=before:raise RuntimeError('Stan zmienił się podczas synchronizacji')
                suffix='.gitive-backup-'+uuid.uuid4().hex[:8];backup=target.with_name(target.name+suffix);home_backup=home.with_name(home.name+suffix)
                target.rename(backup)
                try:home.rename(home_backup)
                except Exception:backup.rename(target);raise
                try:project.rename(target);stage.rename(home)
                except Exception:
                    if target.exists():shutil.rmtree(target)
                    if home.exists():shutil.rmtree(home)
                    backup.rename(target);home_backup.rename(home);raise
                record.update(baseline=incoming,session_baseline=after);write(record_path,record)
                report.update(applied=True,backup=str(backup.relative_to(self.workspace)),session_backup=home_backup.name)
            return report
    def resume(self,clone,application='terminal'):
        if application not in ('terminal','vscode','cursor'):raise ValueError('Wybierz terminal, vscode lub cursor')
        if not re.fullmatch(r'[0-9a-f]{32}',clone):raise ValueError('Niepoprawny clone ID')
        record=json.loads((self.data/'clones'/f'{clone}.json').read_text());self.path(record['target'])
        return self.hub.call('/v1/applications/launch',{'account_id':'softreck','provider':'chatgpt','application_id':application,'project':record['target']})
    def inventory(self):
        output=self.data/('inventory-'+uuid.uuid4().hex+'.json')
        execute(['llm-accounts','scan','--home',str(self.home),'--platform','linux','--max-files','2000','--credential-access','none','--output',str(output)],timeout=120)
        output.chmod(0o600)
        return {'report':output.name,'sha256':digest(output),'secret_export':False}
    def profile(self,action,browser='all',snapshot=None):
        if browser not in ('all','firefox','chrome','chromium'):raise ValueError('Niepoprawna przeglądarka')
        if action=='snapshot':
            value=self.hub.call('/v1/commands/snapshot',{'account_id':'softreck','browser':browser})
            sid=uuid.uuid4().hex
            if not value.get('snapshot_path'):raise RuntimeError('Hub nie zwrócił ścieżki snapshotu')
            write(self.data/'profiles'/f'{sid}.json',{'created':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),'id':sid,'browser':browser,'snapshot_path':value['snapshot_path']})
            return {'id':sid,'browser':browser,'status':value.get('status'),'storage':'Hub native snapshot; local private storage'}
        if action=='restore':
            if not isinstance(snapshot,str) or not re.fullmatch(r'[0-9a-f]{32}',snapshot):raise ValueError('Niepoprawny profil ID')
            receipt=self.data/'profiles'/f'{snapshot}.json'
            value=json.loads(receipt.read_text())
            return self.hub.call('/v1/commands/restore',{'account_id':'softreck','snapshot_path':value['snapshot_path']})
        raise ValueError('Nieobsługiwana operacja profilu')
    def start(self,operation,**args):
        methods={'snapshot':self.snapshot,'clone':self.clone,'resync':self.resync,'resume':self.resume,'inventory':self.inventory,'profile':self.profile}
        if operation not in methods:raise ValueError('Nieznana operacja')
        inspect.signature(methods[operation]).bind(**args)
        with self.lock:
            if self.thread and self.thread.is_alive():raise RuntimeError('Operacja workspace już trwa')
            self.state={'id':uuid.uuid4().hex,'status':'running','operation':operation,'request':args};write(self.status_file,self.state)
            def work():
                try:self.state.update(status='complete',result=methods[operation](**args))
                except Exception as exc:self.state.update(status='blocked',error=str(exc)[:400] if isinstance(exc,(ValueError,RuntimeError)) else type(exc).__name__)
                write(self.status_file,self.state);write(self.data/'operations'/(self.state['id']+'.json'),self.state)
            self.thread=threading.Thread(target=work,daemon=True);self.thread.start();return self.state
