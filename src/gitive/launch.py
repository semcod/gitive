"""Host launcher: existing local noVNC, application and browser windows."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import time
import urllib.request
from dotenv import set_key
from isolation import BASE, prepare, configure_hub, audit, validate_compose, desktop_accounts

ROOT=Path(__file__).resolve().parents[2]
def run(*args): subprocess.run(args,cwd=ROOT,check=True)
def main():
    p=argparse.ArgumentParser();p.add_argument('--no-open',action='store_true');a=p.parse_args()
    hub=Path(os.getenv('LLM_HUB_ROOT','/home/tom/github/subactor/llm-account-hub'))
    inspected=json.loads(subprocess.check_output(['docker','inspect','llm-account-hub-softreck']))[0]
    bindings=inspected['HostConfig']['PortBindings'].get('6080/tcp',[])
    if not bindings or any(b['HostIp'] not in ('127.0.0.1','::1') for b in bindings):
        raise SystemExit('Passwordless noVNC requires loopback-only port binding')
    # Never copy a live desktop profile and never restart an unsafe bind configuration.
    accounts=desktop_accounts()
    for account in accounts:
        try:audit('llm-account-hub-'+account)
        except RuntimeError:run('docker','stop','llm-account-hub-'+account)
    prepare(hub)
    configure_hub(hub)
    # User explicitly requested no VNC password. Preserve every other account setting.
    set_key(str(hub/'.env'),'VNC_PASSWORD_SOFTRECK','none')
    validate_compose(hub)
    run('docker','compose','--env-file',str(hub/'.env'),'-f',str(hub/'generated/compose.yaml'),'-f',str(BASE/'hub-copy-only.json'),
        'up','-d','--no-build','--no-deps',*('account-'+a for a in accounts))
    for account in accounts:audit('llm-account-hub-'+account)
    # Persist the launcher and refresh its session timestamp on desktop login.
    script = (ROOT/'src/gitive/browser_shortcut.py').read_bytes()
    for account in accounts:
        container = 'llm-account-hub-'+account
        run('docker','exec','-u','browser',container,'mkdir','-p','/home/browser/.local/bin','/home/browser/.config/autostart')
        subprocess.run(['docker','exec','-i','-u','browser',container,'tee','/home/browser/.local/bin/gitive-browser-shortcut.py'],input=script,stdout=subprocess.DEVNULL,check=True)
        entry = '[Desktop Entry]\nType=Application\nName=Gitive session timestamp\nExec=python3 /home/browser/.local/bin/gitive-browser-shortcut.py --watch\nTerminal=false\n'
        subprocess.run(['docker','exec','-i','-u','browser',container,'tee','/home/browser/.config/autostart/gitive-session-date.desktop'],input=entry.encode(),stdout=subprocess.DEVNULL,check=True)
        run('docker','exec','-u','browser',container,'python3','/home/browser/.local/bin/gitive-browser-shortcut.py')
        run('docker','exec','-d','-u','browser',container,'python3','/home/browser/.local/bin/gitive-browser-shortcut.py','--watch')
    run('python3','src/gitive/setup.py')
    run('docker','compose','-f','src/gitive/compose.yaml','up','-d','--build')
    audit('loop_app-loop-1',allow_sources=True)
    for _ in range(60):
        try:
            urllib.request.urlopen('http://127.0.0.1:8793/health',timeout=2);break
        except OSError:time.sleep(1)
    else:raise SystemExit('Panel did not become healthy')
    if not a.no_open:
        for url in ('http://127.0.0.1:8793','http://127.0.0.1:6083/vnc.html?autoconnect=true&resize=scale'):
            subprocess.Popen(['xdg-open',url],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    # Display the live dashboard in the existing desktop; no agent commands or credentials are injected.
    subprocess.run(['docker','exec','-d','-u','browser','-e','DISPLAY=:1','llm-account-hub-softreck',
        '/usr/local/bin/llmhub-browser-open','chromium','http://gitive-loop:8787/?desktop=1'],check=False)
    print('Gitive: http://127.0.0.1:8793 | noVNC: http://127.0.0.1:6083/vnc.html?autoconnect=true')
if __name__=='__main__':main()
