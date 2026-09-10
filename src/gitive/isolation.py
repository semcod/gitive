"""Host preparation and fail-closed mount audit for copy-only desktops."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import uuid

ROOT=Path(__file__).resolve().parents[2]
BASE=Path(os.getenv('GITIVE_ISOLATION_ROOT',str(Path.home()/'.local/share/gitive-isolated'))).expanduser().resolve()

def copied(source,target):
    source=Path(source).resolve();target=Path(target)
    if target.exists():return
    target.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
    stage=target.with_name(target.name+'.copy-'+uuid.uuid4().hex[:8])
    try:
        # Reflinks, where available, are independent inodes with copy-on-write; never hardlinks.
        subprocess.run(['cp','-a','--reflink=auto',str(source),str(stage)],check=True)
        stage.rename(target)
    finally:
        if stage.exists():
            if stage.is_dir():shutil.rmtree(stage)
            else:stage.unlink()

def inspect_container(name):
    return json.loads(subprocess.check_output(['docker','inspect',name]))[0]

def audit(name,base=BASE,allow_sources=False):
    c=inspect_container(name);issues=[]
    if c['HostConfig'].get('Privileged'):issues.append('privileged')
    for m in c['Mounts']:
        if m['Type']!='bind':continue
        source=Path(m['Source']).resolve()
        private=source.is_relative_to(base.resolve())
        if not private and not (allow_sources and not m['RW'] and m['Destination'] in ('/source/github','/host-home')):
            issues.append(m['Destination']+' → '+str(source))
        if m['Destination'].endswith('docker.sock'):issues.append('Docker socket')
    if issues:raise RuntimeError('Mounty poza izolacją: '+', '.join(issues))
    return {'container':name,'only_private_writes':True,'mounts':[{k:m.get(k) for k in ('Source','Destination','RW')} for m in c['Mounts']]}

def desktop_accounts():
    names=subprocess.check_output(['docker','ps','-a','--format','{{.Names}}'],text=True).splitlines()
    return [name.removeprefix('llm-account-hub-') for name in names if name.startswith('llm-account-hub-')]

def prepare(hub):
    if Path.home().resolve().is_relative_to(BASE) or ROOT.is_relative_to(BASE) or BASE.is_relative_to(ROOT):
        raise RuntimeError('Izolacja musi być osobnym katalogiem poza repozytorium i nie może obejmować home PC')
    BASE.mkdir(parents=True,exist_ok=True,mode=0o700);BASE.chmod(0o700)
    work=BASE/'github';work.mkdir(exist_ok=True)
    target=work/'semcod/gitive'
    if not target.exists():
        stage=work/('controller-copy-'+uuid.uuid4().hex[:8])
        shutil.copytree(ROOT,stage,symlinks=True,ignore=lambda _,names:set(names)&{'.subactor','node_modules','.venv','__pycache__'})
        target.parent.mkdir(parents=True,exist_ok=True);stage.rename(target)
    if (ROOT/'.subactor/recovery/loop-app').exists():copied(ROOT/'.subactor/recovery/loop-app',BASE/'app-data')
    (BASE/'app-data').mkdir(exist_ok=True,mode=0o700)
    # The old state remains untouched. Legacy registrations must be reimported into the private tree.
    marker=BASE/'app-data/copy-only-v1.json'
    if not marker.exists():
        p=BASE/'app-data/projects.json'
        if p.exists():p.rename(p.with_name('projects.before-isolation.json'))
        (BASE/'app-data/projects.json').write_text('{}\n')
        marker.write_text(json.dumps({'copy_only':True,'legacy_records_disabled':True}))
    legacy=BASE/'app-data/workspaces/clones'
    if legacy.exists() and not (BASE/'app-data/copy-only-clones-v1.json').exists():
        legacy.rename(legacy.with_name('clones.before-isolation-'+uuid.uuid4().hex[:6]))
    (BASE/'app-data/copy-only-clones-v1.json').write_text('{}')
    declared=json.loads(subprocess.check_output(['docker','compose','--env-file',str(Path(hub)/'.env'),'-f',str(Path(hub)/'generated/compose.yaml'),'config','--format','json']))
    override={'services':{}}
    for account in desktop_accounts():
        service='account-'+account
        if service not in declared['services']:raise RuntimeError('Nieznany profil desktopu: '+account)
        c=inspect_container('llm-account-hub-'+account)
        mounts=[];all_mounts={m['Destination']:m for m in c['Mounts']}
        for m in declared['services'][service].get('volumes',[]):
            if m['type']=='bind':all_mounts[m['target']]={'Type':'bind','Source':m['source'],'Destination':m['target'],'RW':not m.get('read_only',False)}
        for m in all_mounts.values():
            if m['Type']!='bind':continue
            if m['Destination']=='/workspace/github':destination=work
            elif Path(m['Source']).resolve().is_relative_to(BASE):destination=Path(m['Source']).resolve()
            else:
                desktop=BASE/'desktop' if account=='softreck' or m['Destination'].startswith('/opt/') else BASE/'desktop-accounts'/account
                destination=desktop/m['Destination'].lstrip('/')
                if not destination.exists() and c['State']['Running']:
                    raise RuntimeError('Zatrzymaj konto przed kopiowaniem profilu: '+account)
                copied(m['Source'],destination)
            mounts.append({'type':'bind','source':str(destination),'target':m['Destination'],'read_only':not m['RW']})
        override['services'][service]={'volumes':mounts}
    (BASE/'hub-copy-only.json').write_text(json.dumps(override,indent=2))
    return BASE

def validate_compose(hub):
    command=['docker','compose','--env-file',str(Path(hub)/'.env'),'-f',str(Path(hub)/'generated/compose.yaml'),'-f',str(BASE/'hub-copy-only.json'),'config','--format','json']
    merged=json.loads(subprocess.check_output(command))
    for account in desktop_accounts():
        for mount in merged['services']['account-'+account].get('volumes',[]):
            if mount['type']!='bind' or not Path(mount['source']).resolve().is_relative_to(BASE):
                raise RuntimeError('Plan noVNC zawiera mount poza prywatną kopią')

def configure_hub(hub):
    from dotenv import set_key
    env=Path(hub)/'.env'
    for key,value in {'WORKSPACE_HOST_PATH':str(BASE/'github'),
                      'KORU_PROJECT_HOST_PATH':str(BASE/'desktop/opt/koru'),
                      'KVM_CONNECTOR_HOST_PATH':str(BASE/'desktop/opt/urirun-connector-kvm')}.items():
        set_key(str(env),key,value)
    # Control's immutable code stays intact. Point only its mutable account home at the copy.
    deployed=Path(subprocess.check_output(['systemctl','--user','show','llm-account-hub.service','--property=WorkingDirectory','--value'],text=True).strip())
    if not deployed.is_dir():raise RuntimeError('Nie znaleziono wdrożenia Control')
    for account in desktop_accounts():
        home=deployed/'state/homes'/account;home.parent.mkdir(parents=True,exist_ok=True)
        desktop=BASE/'desktop' if account=='softreck' else BASE/'desktop-accounts'/account
        copied_home=desktop/'home/browser'
        if home.resolve()!=copied_home.resolve():
            if home.exists() or home.is_symlink():home.rename(home.with_name(account+'.before-isolation-'+uuid.uuid4().hex[:8]))
            home.symlink_to(copied_home,target_is_directory=True)
    subprocess.run(['systemctl','--user','restart','llm-account-hub.service'],check=True)

if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('--prepare',action='store_true');a=p.parse_args()
    if a.prepare:print(prepare(Path(os.getenv('LLM_HUB_ROOT','/home/tom/github/subactor/llm-account-hub'))))
    else:
        print(json.dumps([audit('llm-account-hub-'+a) for a in desktop_accounts()]+[audit('loop_app-loop-1',allow_sources=True)],indent=2))
