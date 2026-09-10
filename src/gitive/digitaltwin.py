"""Host-owned P0 catalog and full selected project/runtime copies.

No Docker socket is delegated. Source trees are only read; project code and
runtime prefixes are independently copied before container mounts are created.
"""
from contextlib import contextmanager
from datetime import datetime,timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
import time
import uuid
from filelock import FileLock
from .capacity import assess
from .engine import write
from .isolation import BASE


def now():return datetime.now(timezone.utc).isoformat()
def command(argv,**kwargs):
    result=subprocess.run(argv,capture_output=True,text=True,timeout=kwargs.pop('timeout',120),**kwargs)
    if result.returncode:raise RuntimeError(Path(argv[0]).name+' failed (exit '+str(result.returncode)+'); no credential output retained')
    return result.stdout.strip()


def inventory(root):
    """Full byte/mode/link inventory; never dereference symlinks or inspect secrets."""
    root=Path(root);result={};size=0
    for folder,dirs,names in os.walk(root,followlinks=False):
        for name in sorted(dirs+names):
            path=Path(folder)/name;info=path.lstat();key=str(path.relative_to(root))
            if stat.S_ISLNK(info.st_mode):result[key]={'link':os.readlink(path)}
            elif stat.S_ISDIR(info.st_mode):result[key]={'mode':stat.S_IMODE(info.st_mode),'directory':True}
            elif stat.S_ISREG(info.st_mode):
                with path.open('rb') as stream:digest=hashlib.file_digest(stream,'sha256').hexdigest()
                result[key]={'sha256':digest,'mode':stat.S_IMODE(info.st_mode),'size':info.st_size};size+=info.st_size
            else:raise ValueError('Active/special file in selected tree: '+key)
    return {'files':result,'bytes':size}


def tree_size(root):
    total=0
    for folder,dirs,names in os.walk(root,followlinks=False):
        for name in names:
            path=Path(folder)/name
            if not path.is_symlink():total+=path.stat().st_size
    return total


def probe_python(executable):
    script="""import sys,json,importlib.metadata,urllib.parse
paths=[]
for d in importlib.metadata.distributions():
    raw=d.read_text('direct_url.json')
    if raw:
        value=json.loads(raw);url=urllib.parse.urlparse(value.get('url',''))
        if url.scheme=='file' and value.get('dir_info',{}).get('editable'):paths.append(urllib.parse.unquote(url.path))
print(json.dumps(dict(executable=sys.executable,prefix=sys.prefix,base_prefix=sys.base_prefix,version=sys.version.split()[0],editable_projects=sorted(set(paths)))))
"""
    return json.loads(command([str(executable),'-B','-c',script]))


def pick_python(source):
    for relative in ('.venv/bin/python','venv/bin/python'):
        if (source/relative).exists():return source/relative
    located=shutil.which('python3')
    if not located:raise ValueError('Python not found')
    return Path(located)


def normalize_roots(paths):
    roots=[]
    for path in sorted({Path(p).resolve() for p in paths},key=lambda p:len(p.parts)):
        if str(path) in ('/','/home','/usr','/etc'):raise ValueError('Select bounded runtime prefixes, not an entire system')
        if not path.is_dir():raise ValueError('Runtime prefix is not a directory')
        if not any(path.is_relative_to(parent) for parent in roots):roots.append(path)
    return roots


def runtime_path(record):
    bins=[str(Path(record['python']['executable']).parent),str(Path(record['python']['base_prefix'])/'bin')]
    if record.get('node'):bins.append(str(Path(record['node']['executable']).parent))
    return ':'.join(dict.fromkeys(bins+['/usr/local/sbin','/usr/local/bin','/usr/sbin','/usr/bin','/sbin','/bin']))


def source_path(project):
    path=Path(project['source_path']);prefix=Path('/source/github')
    if not path.is_relative_to(prefix):raise ValueError('Unknown source mapping')
    root=Path(os.getenv('GITIVE_GITHUB_ROOT','/home/tom/github')).resolve()
    source=(root/path.relative_to(prefix)).resolve()
    if not source.is_relative_to(root):raise ValueError('Source escapes PC project root')
    return source


def local_path(registered,base=BASE):
    path=Path(registered)
    if not path.is_relative_to('/workspace/github'):raise ValueError('Project must be a private copy')
    target=base/'github'/path.relative_to('/workspace/github')
    if not target.resolve().is_relative_to((base/'github').resolve()):raise ValueError('Copy escapes private storage')
    return target


class DigitalTwin:
    def __init__(self,base=BASE):
        self.base=Path(base);self.data=self.base/'app-data';self.catalog=self.data/'digitaltwins.json'
        self.projects=self.data/'projects.json';self.lock=FileLock(str(self.data/'workspace-provision.lock'),timeout=0)
    def all(self):return json.loads(self.catalog.read_text()) if self.catalog.exists() else {'schema_version':1,'twins':{},'workspaces':{}}
    def record(self,name):
        if not re.fullmatch(r'[a-z][a-z0-9-]{1,40}',name):raise ValueError('Invalid project name')
        projects=json.loads(self.projects.read_text())
        if name not in projects or not projects[name].get('copy_only'):raise ValueError('Register a private project first')
        return projects[name]
    def plan(self,name,python=None,node=None,image=None,extra_paths=()):
        project=self.record(name);source=source_path(project)
        py=probe_python(Path(python) if python else pick_python(source))
        node_path=Path(node or shutil.which('node') or '')
        node_info=None
        if node and not node_path.is_file():raise ValueError('Node executable not found')
        roots=[source,Path(py['base_prefix'])]
        if py['prefix']!=py['base_prefix'] and not Path(py['prefix']).is_relative_to(source):roots.append(Path(py['prefix']))
        if node_path.is_file():
            node_path=node_path.resolve();node_info={'executable':str(node_path),'version':command([str(node_path),'--version'])}
            if '/.nvm/' in str(node_path):roots.append(node_path.parent.parent)
            elif node:raise ValueError('For non-nvm Node, provide its bounded installation via --include-path')
            else:node_info=None
        if node and not node_path.is_file():raise ValueError('Node executable not found')
        roots=normalize_roots([*roots,*py.get('editable_projects',[]),*extra_paths])
        if any(self.base.resolve().is_relative_to(root) for root in roots):raise ValueError('Source would include private storage recursively')
        release=dict(line.split('=',1) for line in Path('/etc/os-release').read_text().splitlines() if '=' in line)
        family=release.get('ID','').strip('"');version=release.get('VERSION_ID','').strip('"')
        if not image:
            if family!='ubuntu':raise ValueError('Specify --image for this PC distribution')
            image='ubuntu:'+version
        sizes={str(root):tree_size(root) for root in roots};new_bytes=sum(sizes.values())
        existing=tree_size(self.base/'github/.digitaltwin') if (self.base/'github/.digitaltwin').exists() else 0
        capacity=assess(shutil.disk_usage(self.base).free,existing+new_bytes,new_bytes+1024**3)
        return {'project':name,'source':str(source),'roots':[str(p) for p in roots],'sizes':sizes,'python':py,'node':node_info,'image':image,'capacity':capacity,'created':now()}
    def prepare(self,name,python=None,node=None,image=None,extra_paths=()):
        self.data.mkdir(parents=True,exist_ok=True)
        with self.lock:
            return self._prepare(self.plan(name,python,node,image,extra_paths))
    def _prepare(self,plan):
        name=plan['project'];project=self.record(name)
        state_path=self.data/'state.json'
        if state_path.exists() and json.loads(state_path.read_text()).get('status') in ('running','stopping'):raise ValueError('Stop the project loop before provisioning')
        if not plan['capacity']['fits']:raise ValueError('Insufficient capacity: '+str(plan['capacity']['shortfall_bytes'])+' bytes')
        catalog=self.all()
        if name in catalog['workspaces']:raise ValueError('Workspace already exists; use status/test/exec (no overwrite)')
        identifier=name+'-'+uuid.uuid4().hex[:8]
        root=self.base/'github/.digitaltwin'/identifier;root.mkdir(parents=True,mode=0o700)
        # Partial imports remain recoverable and are never presented as ready.
        write(root/'operation.json',{'status':'copying','plan':plan})
        rootfs=root/'rootfs';rootfs.mkdir()
        container='gitive-project-'+identifier
        try:
            inventories={}
            for source_name in plan['roots']:
                source=Path(source_name);destination=rootfs/source.relative_to('/')
                destination.parent.mkdir(parents=True,exist_ok=True)
                write(root/'operation.json',{'status':'inventory','source':source_name,'plan':plan})
                before=inventory(source)
                write(root/'operation.json',{'status':'copying','source':source_name,'plan':plan})
                command(['cp','-a','--reflink=auto',str(source),str(destination)],timeout=3600)
                after=inventory(source);copied=inventory(destination)
                if before!=after or before!=copied:raise RuntimeError('Selected source changed during copying; private stage retained')
                inventories[source_name]={'bytes':before['bytes'],'sha256':hashlib.sha256(json.dumps(before,sort_keys=True).encode()).hexdigest()}
            target=rootfs/Path(plan['source']).relative_to('/')
            previous=local_path(project['path'],self.base)
            # Preserve the active Gitive Planfile store; never overwrite another native store.
            if (previous/'.planfile').exists():
                if (target/'.planfile').exists():
                    if inventory(previous/'.planfile')!=inventory(target/'.planfile'):raise ValueError('Two different Planfile stores; explicit reconciliation required')
                else:shutil.copytree(previous/'.planfile',target/'.planfile',symlinks=True)
            write(root/'inventory.json',inventories)
            try:base_image_id=command(['docker','image','inspect',plan['image'],'--format','{{.Id}}'])
            except RuntimeError:
                command(['docker','pull',plan['image']],timeout=600)
                base_image_id=command(['docker','image','inspect',plan['image'],'--format','{{.Id}}'])
            base_digest=command(['docker','image','inspect',plan['image'],'--format','{{index .RepoDigests 0}}'])
            dockerfile=Path(__file__).parent/'templates/workspace/Runtime.Dockerfile'
            build_log=root/'image-build.log'
            tag='gitive-project-runtime:'+identifier
            with build_log.open('w') as stream:
                stream_result=subprocess.run(['docker','build','--build-arg','BASE_IMAGE='+base_digest,'-t',tag,'-f',str(dockerfile),str(dockerfile.parent)],stdout=stream,stderr=subprocess.STDOUT,timeout=600)
            if stream_result.returncode:raise RuntimeError('Runtime image build failed; inspect private image-build.log')
            image_id=command(['docker','image','inspect',tag,'--format','{{.Id}}'])
            self.launch(container,root,plan,image_id)
            py=json.loads(command(['docker','exec',container,plan['python']['executable'],'-B','-c','import sys,json; print(json.dumps(dict(version=sys.version.split()[0],prefix=sys.prefix,base_prefix=sys.base_prefix)))']))
            if any(py[k]!=plan['python'][k] for k in ('version','prefix','base_prefix')):raise RuntimeError('Python environment mismatch')
            if plan['node'] and command(['docker','exec',container,plan['node']['executable'],'--version'])!=plan['node']['version']:raise RuntimeError('Node version mismatch')
            self.audit_container(container,root)
            account={'credential_ref':'host-gh:default','login':None,'verification':'pending'}
            try:account.update(login=command(['gh','api','user','--jq','.login']),verification='verified')
            except (OSError,RuntimeError):pass
            workspace={'id':identifier,'project':name,'container':container,'root':str(root),'path_in_container':plan['source'],
                'path_in_app':'/workspace/github/'+str(target.relative_to(self.base/'github')),
                'source':plan['source'],'python':plan['python'],'node':plan['node'],'image_id':image_id,'base_image_id':base_image_id,'status':'ready',
                'verification':{'dependency_copy':'full-content-sha256','python':True,'node':bool(plan['node']),'project_tests':'pending','scope':'selected runtime versions; not all host packages'},
                'created':now(),'previous_project_path':project['path'],'account_ref':'github-pc','source_inventories':inventories}
            catalog['workspaces'][name]=workspace
            catalog['twins'].setdefault('pc-nvidia',{'id':'pc-nvidia','control_container':'llm-account-hub-softreck','projects':[],'accounts':{}})
            twin=catalog['twins']['pc-nvidia'];twin['accounts']['github-pc']=account
            if name not in twin['projects']:twin['projects'].append(name)
            backups=self.data/'catalog-backups'/identifier;backups.mkdir(parents=True)
            shutil.copy2(self.projects,backups/'projects.json')
            if self.catalog.exists():shutil.copy2(self.catalog,backups/'digitaltwins.json')
            rows=json.loads(self.projects.read_text());rows[name].update(path=workspace['path_in_app'],workspace_ref=identifier,digitaltwin_ref='pc-nvidia')
            write(root/'operation.json',{'status':'verified-awaiting-registry','workspace':workspace})
            write(self.catalog,catalog)
            try:write(self.projects,rows)
            except Exception:
                if (backups/'digitaltwins.json').exists():shutil.copy2(backups/'digitaltwins.json',self.catalog)
                else:self.catalog.unlink(missing_ok=True)
                raise
            write(root/'operation.json',{'status':'complete','workspace':workspace})
            return workspace
        except Exception as exc:
            write(root/'operation.json',{'status':'blocked','error_type':type(exc).__name__,'message':str(exc),'plan':plan})
            # Only our named container is stopped; stage and prior copies remain recoverable.
            subprocess.run(['docker','stop',container],capture_output=True)
            raise
    def launch(self,container,root,plan,image_id):
        mount_args=[]
        for source in plan['roots']:
            copied=root/'rootfs'/Path(source).relative_to('/')
            readonly=not Path(plan['source']).is_relative_to(Path(source))
            mount_args+=['--mount','type=bind,src='+str(copied)+',dst='+source+(',readonly' if readonly else '')]
        home=root/'home';home.mkdir(exist_ok=True)
        command(['docker','run','-d','--name',container,'--label','gitive.workspace='+root.name,
            '--restart','unless-stopped','--user',str(os.getuid())+':'+str(os.getgid()),
            '--cap-drop','ALL','--security-opt','no-new-privileges','--read-only',
            '--tmpfs','/tmp:rw,exec,mode=1777','--mount','type=bind,src='+str(home)+',dst=/gitive-home',
            '--env','HOME=/gitive-home','--env','PATH='+runtime_path(plan),'--env','PYTHONDONTWRITEBYTECODE=1',
            '--workdir',plan['source'],*mount_args,image_id,'sleep','infinity'])

    def extend(self,name,paths):
        with self.lock:
            workspace=self.status(name)
            if workspace.get('container_status')!='running':raise ValueError('Workspace must be running before extension')
            root=Path(workspace['root']);existing=list(workspace['source_inventories'])
            additions=normalize_roots(paths)
            if not additions:raise ValueError('Provide --include-path')
            for source in additions:
                if root.resolve().is_relative_to(source):raise ValueError('Recursive copy is forbidden')
                if any(source.is_relative_to(Path(p)) or Path(p).is_relative_to(source) for p in existing):raise ValueError('Dependency overlaps an existing mount')
            amount=sum(tree_size(p) for p in additions)
            if not assess(shutil.disk_usage(self.base).free,tree_size(root)+amount,amount)['fits']:raise ValueError('Insufficient space for dependency and reserve')
            inventories=dict(workspace['source_inventories'])
            for source in additions:
                target=root/'rootfs'/source.relative_to('/')
                if target.exists():raise ValueError('Private dependency already exists; not overwritten')
                before=inventory(source);target.parent.mkdir(parents=True,exist_ok=True)
                command(['cp','-a','--reflink=auto',str(source),str(target)],timeout=3600)
                if before!=inventory(source) or before!=inventory(target):raise RuntimeError('Dependency changed while copying; private stage retained')
                inventories[str(source)]={'bytes':before['bytes'],'sha256':hashlib.sha256(json.dumps(before,sort_keys=True).encode()).hexdigest()}
            old=workspace['container'];backup=old+'-backup-'+uuid.uuid4().hex[:6]
            command(['docker','stop',old]);command(['docker','rename',old,backup])
            launched=False
            try:
                self.launch(old,root,{**workspace,'roots':list(inventories)},workspace['image_id'])
                launched=True
                self.audit_container(old,root)
                command(['docker','exec',old,workspace['python']['executable'],'--version'])
            except Exception:
                if launched:
                    self.audit_container(old,root)
                    subprocess.run(['docker','rm','-f',old],capture_output=True)
                command(['docker','rename',backup,old]);command(['docker','start',old]);raise
            workspace.pop('container_status',None)
            workspace['source_inventories']=inventories
            workspace.setdefault('container_backups',[]).append(backup)
            workspace['verification']['project_tests']='pending-after-dependency-extension'
            catalog=self.all();catalog['workspaces'][name]=workspace;write(self.catalog,catalog)
            write(root/'operation.json',{'status':'complete','workspace':workspace})
            return workspace

    def audit_container(self,container,root):
        data=json.loads(command(['docker','inspect',container]))[0]
        if data['HostConfig'].get('Privileged'):raise ValueError('Unexpected privileged container')
        if data['Config'].get('Labels',{}).get('gitive.workspace')!=root.name:raise ValueError('Container ownership label mismatch')
        for mount in data['Mounts']:
            if mount['Type']=='bind' and not Path(mount['Source']).resolve().is_relative_to(root.resolve()):raise ValueError('Mount escapes workspace')
            if mount['Destination'].endswith('docker.sock'):raise ValueError('Docker socket is forbidden')
        return data
    def status(self,name):
        self.record(name);workspace=self.all()['workspaces'].get(name)
        if not workspace:
            pending=sorted((self.base/'github/.digitaltwin').glob(name+'-*/operation.json'),key=lambda p:p.stat().st_mtime)
            return {'project':name,'status':'not-provisioned','last_import':str(pending[-1]) if pending else None}
        operation=json.loads((Path(workspace['root'])/'operation.json').read_text())
        if operation.get('status')!='complete':raise ValueError('Incomplete catalog transaction; use twin recover '+name)
        observed=self.audit_container(workspace['container'],Path(workspace['root']))
        return {**workspace,'container_status':observed['State']['Status']}
    def recover(self,name):
        with self.lock:
            catalog=self.all();workspace=catalog['workspaces'].get(name)
            if not workspace:raise ValueError('No registered transaction to recover; incomplete private stages are retained')
            root=Path(workspace['root']);operation=json.loads((root/'operation.json').read_text())
            if operation.get('status')=='complete':raise ValueError('Workspace is complete; recovery will not overwrite it')
            backups=self.data/'catalog-backups'/workspace['id']
            before=json.loads((backups/'projects.json').read_text())
            rows=json.loads(self.projects.read_text())
            if rows[name]['path'] not in (before[name]['path'],workspace['path_in_app']):raise ValueError('Registry changed; recovery conflict')
            self.audit_container(workspace['container'],root)
            command(['docker','stop',workspace['container']])
            rows[name]=before[name];write(self.projects,rows)
            catalog['workspaces'].pop(name)
            for twin in catalog['twins'].values():twin['projects']=[p for p in twin['projects'] if p!=name]
            write(self.catalog,catalog);write(root/'operation.json',{'status':'recovered','workspace':workspace})
            return {'project':name,'status':'recovered','preserved_copy':str(root)}

    def execute(self,name,argv,test=False,env=None):
        with self.lock:
            workspace=self.status(name)
            if workspace.get('container_status')!='running':raise ValueError('Project container is not running')
            if not argv or any(not isinstance(a,str) or not a for a in argv):raise ValueError('Provide an argument list')
            # Interpreter alias resolves to the copied environment, not the image default.
            argv=list(argv)
            if argv[0] in ('python','python3'):argv[0]=workspace['python']['executable']
            if argv[0]=='node' and workspace['node']:argv[0]=workspace['node']['executable']
            environment=['--env','PATH='+runtime_path(workspace)]
            settings=Path(workspace['root'])/'test-environment.json'
            effective=json.loads(settings.read_text()) if test and settings.exists() else {}
            effective.update(env or {})
            for key,value in effective.items():
                if not re.fullmatch('[A-Z][A-Z0-9_]*',key):raise ValueError('Invalid environment variable name')
                environment+=['--env',key+'='+value]
            run=Path(workspace['root'])/'runs'/(time.strftime('%Y%m%dT%H%M%SZ',time.gmtime())+'-'+uuid.uuid4().hex[:6]);run.mkdir(parents=True)
            log=run/'output.log'
            with log.open('w') as out:
                log.chmod(0o600)
                process=subprocess.Popen(['docker','exec',*environment,workspace['container'],*argv],stdout=out,stderr=subprocess.STDOUT,start_new_session=True)
                try:code=process.wait(600)
                except subprocess.TimeoutExpired:
                    # docker exec client termination alone cannot prove remote process termination.
                    command(['docker','stop',workspace['container']]);process.wait(10);code=124
            result={'project':name,'exit_code':code,'status':'passed' if code==0 else 'failed','log':str(log),'created':now(),'test':test}
            write(run/'result.json',result)
            if test:
                if code==0 and env:write(settings,effective)
                catalog=self.all();catalog['workspaces'][name]['verification']['project_tests']=result;write(self.catalog,catalog)
            return result
