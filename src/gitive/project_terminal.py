"""Host-owned noVNC → private project SSH terminal. No host Docker access is delegated."""
import json
import os
from pathlib import Path
import shlex
import subprocess
import time
import uuid
from .digitaltwin import command, pc_identity, identity_build_args, runtime_path, now
from .engine import write


def setup_ssh(root, workspace, identity):
    folder=root/'ssh';folder.mkdir(exist_ok=True,mode=0o700)
    for name in ('host_ed25519','client_ed25519'):
        key=folder/name
        if not key.exists():command(['ssh-keygen','-q','-t','ed25519','-N','','-f',str(key)])
        key.chmod(0o600)
    (folder/'authorized_keys').write_text((folder/'client_ed25519.pub').read_text())
    (folder/'sshd_config').write_text('''Port 2222
ListenAddress 0.0.0.0
HostKey /gitive-ssh/host_ed25519
PidFile /tmp/gitive-sshd.pid
AuthorizedKeysFile /gitive-ssh/authorized_keys
PasswordAuthentication no
KbdInteractiveAuthentication no
PermitRootLogin no
UsePAM no
StrictModes yes
AllowAgentForwarding no
AllowTcpForwarding no
X11Forwarding yes
X11UseLocalhost yes
PermitTunnel no
PermitUserEnvironment no
ForceCommand /gitive-ssh/session
AllowUsers '''+identity['username']+'\n')
    # Values are shell-quoted by the host controller. User commands come only from
    # the freshly provisioned, authenticated SSH client, never from LLM output.
    script='#!/bin/sh\nexport HOME='+shlex.quote(identity['home'])+'\nexport PATH='+shlex.quote(runtime_path(workspace))+'\n'
    script+='cd -- '+shlex.quote(workspace['source'])+' || exit 1\n'
    script+='if [ -n "$SSH_ORIGINAL_COMMAND" ]; then exec /bin/bash -c "$SSH_ORIGINAL_COMMAND"; fi\n'
    script+='exec /bin/bash --noprofile --rcfile /gitive-ssh/bashrc -i\n'
    (folder/'session').write_text(script);(folder/'session').chmod(0o700)
    (folder/'bashrc').write_text("export PS1='\\u@\\h:$PWD\\$ '\n")


def verify_identity(container, workspace, identity):
    script='import os,pwd,json; print(json.dumps(dict(username=pwd.getpwuid(os.getuid()).pw_name,uid=os.getuid(),gid=os.getgid(),home=os.environ["HOME"],pwd=os.getcwd())))'
    actual=json.loads(command(['docker','exec',container,workspace['python']['executable'],'-B','-c',script]))
    expected={k:identity[k] for k in ('username','uid','gid','home')};expected['pwd']=workspace['source']
    if actual!=expected:raise RuntimeError('Project identity/path mismatch')
    return actual


def provision(twin,name):
    """Migrate only an idle owned runtime; preserve mounts and stopped predecessor."""
    with twin.lock:
        workspace=twin.status(name)
        if workspace.get('container_status')!='running':raise ValueError('Najpierw uruchom kontener projektu')
        state=twin.data/'state.json'
        if state.exists() and json.loads(state.read_text()).get('status') in ('running','stopping'):
            raise ValueError('Zatrzymaj pętlę przed konfiguracją terminala projektu')
        identity=pc_identity(Path(workspace['source']))
        if workspace.get('terminal') and workspace.get('identity')==identity:
            verify_identity(workspace['container'],workspace,identity)
            return workspace
        processes=command(['docker','top',workspace['container'],'-eo','pid,comm']).splitlines()[1:]
        if any(p.split()[-1] not in ('sleep','sshd') for p in processes):
            raise ValueError('Kontener ma aktywne procesy; zakończ je przed zmianą konta')
        root=Path(workspace['root']);setup_ssh(root,workspace,identity)
        template=Path(__file__).parent/'templates/workspace/Runtime.Dockerfile'
        tag='gitive-project-terminal:'+workspace['id']
        base_tag='gitive-terminal-base:'+workspace['id']
        command(['docker','tag',workspace['image_id'],base_tag])
        log=root/'terminal-image-build.log'
        with log.open('w') as stream:
            result=subprocess.run(['docker','build','--builder','default','--build-arg','BASE_IMAGE='+base_tag,
                    *identity_build_args(identity),'-t',tag,'-f',str(template),str(template.parent)],
                    stdout=stream,stderr=subprocess.STDOUT,timeout=600)
        if result.returncode:raise RuntimeError('Budowa terminala nieudana; log: '+str(log))
        image=command(['docker','image','inspect',tag,'--format','{{.Id}}'])
        network='llm-account-hub-network'
        command(['docker','network','inspect',network])
        replacement={**workspace,'identity':identity,'image_id':image,
                     'terminal':{'network':network,'port':2222,'transport':'ssh-public-key','created':now()}}
        old=workspace['container'];backup=old+'-backup-'+uuid.uuid4().hex[:6]
        command(['docker','stop',old]);command(['docker','rename',old,backup])
        launched=False
        try:
            twin.launch(old,root,{**replacement,'roots':list(workspace['source_inventories'])},image)
            launched=True
            twin.audit_container(old,root)
            verify_identity(old,replacement,identity)
        except Exception:
            if launched:
                twin.audit_container(old,root);command(['docker','rm','-f',old])
            command(['docker','rename',backup,old]);command(['docker','start',old]);raise
        replacement.pop('container_status',None)
        replacement.setdefault('container_backups',[]).append(backup)
        catalog=twin.all();catalog['workspaces'][name]=replacement
        # Retain rollback material if either catalog write is interrupted.
        write(root/'terminal-previous-workspace.json',workspace)
        write(root/'operation.json',{'status':'verified-awaiting-registry','workspace':replacement})
        write(twin.catalog,catalog)
        write(root/'operation.json',{'status':'complete','workspace':replacement})
        return replacement


def open_terminal(twin,name):
    workspace=provision(twin,name)
    gui=twin.all()['twins']['pc-nvidia']['control_container']
    observed=json.loads(command(['docker','inspect',gui]))[0]
    # GUI keeps its desktop-service account. The shell itself runs as the PC user
    # inside the project container; it never receives a Docker socket or PC mounts.
    for mount in observed['Mounts']:
        if mount['Type']=='bind' and not Path(mount['Source']).resolve().is_relative_to(twin.base.resolve()):
            raise ValueError('GUI mount is not a private copy')
        if mount['Destination'].endswith('docker.sock'):raise ValueError('Docker socket in GUI is forbidden')
    try:command(['docker','exec',gui,'test','-x','/usr/bin/ssh'])
    except RuntimeError:
        command(['docker','exec','--user','root',gui,'apt-get','update'],timeout=600)
        command(['docker','exec','--user','root','--env','DEBIAN_FRONTEND=noninteractive',gui,
                 'apt-get','install','-y','--no-install-recommends','openssh-client'],timeout=600)
    gui_home=next(Path(m['Source']) for m in observed['Mounts'] if m['Destination']=='/home/browser')
    folder=gui_home/'.local/share/gitive/project-terminals'/workspace['id'];folder.mkdir(parents=True,exist_ok=True,mode=0o700)
    root=Path(workspace['root']);key=folder/'id_ed25519'
    key.write_bytes((root/'ssh/client_ed25519').read_bytes());key.chmod(0o600)
    public=(root/'ssh/host_ed25519.pub').read_text().split()
    known=folder/'known_hosts';known.write_text('['+workspace['container']+']:2222 '+' '.join(public[:2])+'\n')
    remote=Path('/home/browser')/folder.relative_to(gui_home)
    ssh=['/usr/bin/ssh','-F','/dev/null','-tt','-p','2222','-i',str(remote/'id_ed25519'),'-o','IdentitiesOnly=yes',
         '-o','StrictHostKeyChecking=yes','-o','UserKnownHostsFile='+str(remote/'known_hosts'),
         '-o','BatchMode=yes','-o','ConnectTimeout=10','-o','ServerAliveInterval=15',
         workspace['identity']['username']+'@'+workspace['container']]
    # Verify the GUI→project connection, not just docker exec on the host.
    probe=[x for x in ssh if x!='-tt']
    actual=command(['docker','exec','--user','browser',gui,*probe,'whoami; pwd; printf "%s\\n" "$HOME"'])
    expected='\n'.join([workspace['identity']['username'],workspace['source'],workspace['identity']['home']])
    if actual!=expected:raise RuntimeError('GUI → project SSH identity/path check failed')
    launcher=folder/'open';launcher.write_text('#!/bin/sh\nexec '+shlex.join(ssh)+'\n');launcher.chmod(0o700)
    desktop=gui_home/'Desktop';desktop.mkdir(exist_ok=True)
    title='Gitive '+name+' — '+workspace['identity']['username']
    entry=desktop/('gitive-project-'+name+'.desktop')
    entry.write_text('[Desktop Entry]\nType=Application\nName='+title+'\nComment='+workspace['source']+
                     '\nExec=xfce4-terminal --disable-server --title="'+title+'" --execute '+str(remote/'open')+
                     '\nIcon=utilities-terminal\nTerminal=false\n')
    entry.chmod(0o700)
    wm=['docker','exec','--user','browser',gui,'wmctrl']
    before={line.split()[0] for line in command([*wm,'-l']).splitlines()}
    command(['docker','exec','-d','--user','browser',gui,
             'xfce4-terminal','--disable-server','--title',title,'--execute',str(remote/'open')])
    deadline=time.monotonic()+5
    window=None
    while time.monotonic()<deadline:
        for line in command([*wm,'-l']).splitlines():
            if title in line and line.split()[0] not in before:window=line.split()[0]
        if window:break
        time.sleep(.2)
    if not window:raise RuntimeError('SSH działa, ale okno terminala nie zostało potwierdzone')
    desktop_number=next(line.split()[0] for line in command([*wm,'-d']).splitlines() if line.split()[1]=='*')
    command([*wm,'-i','-r',window,'-t',desktop_number])
    command([*wm,'-i','-r',window,'-b','add,maximized_vert,maximized_horz'])
    command([*wm,'-i','-a',window])
    return {**workspace,'window_id':window,'status':'terminal-opened','identity_verified':True,'desktop_shortcut':str(entry)}
