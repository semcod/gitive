"""Host-side activation of an imported private workspace, with backups.

The application container has no Docker socket. This explicit CLI operation runs
on the host, audits the desktop mounts, and never writes to a PC source profile.
"""
from datetime import datetime,timezone
import json
from pathlib import Path
import shutil
import subprocess
import uuid


def activate(clone,browser,include_sessions=False):
    import fcntl
    from .isolation import BASE
    BASE.mkdir(parents=True,exist_ok=True,mode=0o700)
    with (BASE/'desktop-activation.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        return _activate(clone,browser,include_sessions)


def _activate(clone,browser,include_sessions=False):
    if __package__:from .isolation import BASE,audit
    else:from isolation import BASE,audit
    if browser not in ('firefox','chrome'):raise ValueError('Aktywacja obsługuje zweryfikowane Firefox lub Chrome')
    if len(clone)!=32 or any(c not in '0123456789abcdef' for c in clone):raise ValueError('Niepoprawna kopia')
    container='llm-account-hub-softreck';audit(container)
    store=BASE/'app-data/workspaces'
    record=json.loads((store/'clones'/f'{clone}.json').read_text())
    offline=store/('restored-home-'+clone)
    paths=record.get('session_paths',[])
    source_name=next((n for n in paths if (n.endswith('/.mozilla/firefox') or n=='.mozilla/firefox') and browser=='firefox' or n=='.config/google-chrome' and browser=='chrome'),None)
    if not source_name:raise ValueError('Ta kopia nie zawiera wybranego profilu')
    install=json.loads((BASE/'desktop/browser-install.json').read_text())[browser]
    version=subprocess.check_output(['docker','exec','-u','browser',container,install['binary'],'--version'],text=True,stderr=subprocess.DEVNULL,timeout=30)
    if install['version'] not in version:raise RuntimeError('Wersja przeglądarki niezgodna z przygotowanym środowiskiem')
    home=BASE/'desktop/home/browser'
    selected={source_name:'.mozilla/firefox' if browser=='firefox' else '.config/google-chrome'}
    if include_sessions:
        if __package__:from .workspace import SESSIONS
        else:from workspace import SESSIONS
        selected.update({n:n for n in paths if n in SESSIONS})
    for src,dst in selected.items():
        if not (offline/src).resolve().is_relative_to(offline.resolve()):raise ValueError('Źródło poza kopią')
        if not (home/dst).resolve().is_relative_to(home.resolve()):raise ValueError('Cel poza prywatnym home')
        if not (offline/src).exists():raise ValueError('Brakuje danych profilu w kopii')
    stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'-'+uuid.uuid4().hex[:6]
    backup=BASE/'desktop-backups'/stamp;backup.mkdir(parents=True,mode=0o700)
    staged=backup/'staging';staged.mkdir()
    # Stage before stopping the desktop; no active profile is overwritten during copying.
    for src,dst in selected.items():
        target=staged/dst;target.parent.mkdir(parents=True,exist_ok=True)
        if (offline/src).is_dir():shutil.copytree(offline/src,target,symlinks=True)
        else:shutil.copy2(offline/src,target)
    subprocess.run(['docker','stop',container],check=True,stdout=subprocess.DEVNULL)
    applied=[]
    try:
        for src,dst in selected.items():
            target=home/dst;old=backup/'previous'/dst;old.parent.mkdir(parents=True,exist_ok=True)
            target.parent.mkdir(parents=True,exist_ok=True)
            had_old=target.exists() or target.is_symlink()
            if had_old:target.rename(old)
            applied.append((target,old,had_old))
            (staged/dst).rename(target)
        profile=home/selected[source_name]
        for pattern in ('SingletonLock','SingletonCookie','SingletonSocket','*/.parentlock','*/lock'):
            for lock in profile.glob(pattern):
                if lock.is_file() or lock.is_symlink():lock.unlink()
        desktop=home/'Desktop';desktop.mkdir(exist_ok=True)
        binary=install['binary']
        extra='--ProfileManager --no-remote' if browser=='firefox' else '--user-data-dir=/home/browser/.config/google-chrome --no-first-run'
        (desktop/f'gitive-pc-{browser}.desktop').write_text('[Desktop Entry]\nType=Application\nName='+browser.title()+' — PC '+datetime.now().astimezone().strftime('%Y-%m-%d %H:%M:%S %Z')+'\nComment=Zaimportowana kopia; logowanie może wymagać ponownego potwierdzenia.\nExec='+binary+' '+extra+'\nIcon='+('firefox' if browser=='firefox' else 'google-chrome')+'\nTerminal=false\n')
        (desktop/f'gitive-pc-{browser}.desktop').chmod(0o755)
        result={'status':'activated','clone':clone,'account':'softreck','browser':browser,'version':install['version'],'copied_paths':list(selected),'backup':str(backup),'login_verified':False,'created':stamp}
        (backup/'activation.json').write_text(json.dumps(result,indent=2)+'\n')
    except Exception:
        for target,old,had_old in reversed(applied):
            if target.exists() or target.is_symlink():target.rename(backup/('failed-'+uuid.uuid4().hex))
            if had_old:old.rename(target)
        raise
    finally:
        subprocess.run(['docker','start',container],check=True,stdout=subprocess.DEVNULL)
    audit(container)
    return result
