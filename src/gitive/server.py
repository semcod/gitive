import json
import os
from pathlib import Path
import secrets
import shlex
from urllib.parse import urlsplit, parse_qs
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from .engine import Engine

HTML=Path(__file__).with_name('index.html').read_text()
def _load_or_create_token():
    token_path = Path(os.getenv('LOOP_DATA', '/data')) / 'control-token.txt'
    try:
        if token_path.exists():
            val = token_path.read_text().strip()
            if val:
                return val
    except Exception:
        pass
    new_token = secrets.token_urlsafe(32)
    try:
        token_path.parent.mkdir(parents=True, exist_ok=True)
        token_path.write_text(new_token)
    except Exception:
        pass
    return new_token

TOKEN = _load_or_create_token()
engine=None
workspace=None
class Handler(BaseHTTPRequestHandler):
    def log_message(self,*args): pass
    def send(self,code,data,kind='application/json'):
        if isinstance(data, bytes): raw = data
        elif isinstance(data, str): raw = data.encode()
        else: raw = json.dumps(data, ensure_ascii=False).encode()
        self.send_response(code); self.send_header('Content-Type',kind); self.send_header('Content-Length',str(len(raw)))
        self.send_header('Cache-Control','no-store'); self.send_header('X-Content-Type-Options','nosniff'); self.end_headers(); self.wfile.write(raw)
    def do_GET(self):
        clean_path = urlsplit(self.path).path
        if clean_path == '/favicon.ico':
            return self.send(204, b'', 'image/x-icon')
        if clean_path in ('/control.js','/control.css'):
            return self.send(200,Path(__file__).with_name(clean_path[1:]).read_text(),('text/css' if clean_path.endswith('.css') else 'text/javascript')+'; charset=utf-8')
        if self.path=='/api/control':
            from .control import dashboard
            try:return self.send(200,dashboard(engine))
            except (ValueError,OSError):return self.send(409,{'error':'Stan projektu chwilowo niedostępny'})
        if self.path.split('?')[0]=='/tools':
            return self.send(200,Path(__file__).with_name('tools.html').read_text().replace('__TOKEN__',TOKEN).replace('__NOVNC__',os.getenv('NOVNC_URL','http://127.0.0.1:6083/vnc.html')), 'text/html; charset=utf-8')
        if self.path=='/workspace-ui.js':return self.send(200,Path(__file__).with_name('workspace-ui.js').read_text(),'text/javascript; charset=utf-8')
        if urlsplit(self.path).path=='/api/integrations/tickets':
            from .integrations import aggregate_tickets
            from .projects import Projects
            query_params = parse_qs(urlsplit(self.path).query)
            source = query_params.get('source', ['all'])[0]
            repo = query_params.get('repo', [''])[0]
            q = query_params.get('q', [''])[0]
            custom_repos = [r.strip() for r in repo.split(',') if r.strip()] if repo else None
            tickets = aggregate_tickets(Projects(engine.root, engine.data).all(), source=source, custom_repos=custom_repos, query=q)
            return self.send(200, tickets)
        if self.path=='/api/overview':
            from .overview import overview
            from .projects import Projects
            return self.send(200,overview(engine.state,workspace.state,workspace.inspect(),Projects(engine.root,engine.data).all()))
        if self.path=='/health': return self.send(200,{'ok':True})
        if self.path.split('?')[0]=='/':
            return self.send(200,HTML.replace('__TOKEN__',TOKEN).replace('__NOVNC__',os.getenv('NOVNC_URL','http://127.0.0.1:6083/vnc.html')), 'text/html; charset=utf-8')
        if urlsplit(self.path).path=='/api/folders':
            from .folders import browse
            try:
                relative=parse_qs(urlsplit(self.path).query).get('path',[''])[0]
                return self.send(200,browse(relative))
            except (ValueError,OSError):return self.send(400,{'error':'Folder niedostępny lub poza ~/github'})
        if self.path=='/api/workspace':return self.send(200,workspace.inspect())
        if self.path=='/api/workspace/state':return self.send(200,workspace.state)
        if urlsplit(self.path).path=='/api/operations':
            from .operations import current
            query=parse_qs(urlsplit(self.path).query)
            project=query.get('project',[''])[0];ticket=query.get('ticket',[''])[0]
            if not project or not ticket:return self.send(400,{'error':'Wybierz projekt i ticket'})
            with engine.lock:
                state=json.loads(json.dumps(engine.state))
            return self.send(200,current(engine.data,state,project,ticket))
        if self.path=='/api/state': return self.send(200,engine.state)
        if self.path=='/api/progress':
            folder=engine.data/engine.state.get('run','missing')
            logs=sorted(folder.glob('**/*.log'),key=lambda p:p.stat().st_mtime)
            lines=[]
            for log in logs[-4:]:
                try:
                    with log.open('rb') as stream:
                        stream.seek(max(0,log.stat().st_size-32000));tail=stream.read().decode(errors='replace')
                    for s in tail.splitlines():
                        s_strip=s.strip()
                        if not s_strip:continue
                        if s_strip.startswith(('START ','ITERATION ','GITIVE_RESULT ','WORKER FAILED ','gitive:','stage:','[Gitive]')) or any(w in s_strip for w in ('Error','FAILED','passed','PASSED','FAIL','OK','test_')):
                            lines.append(s_strip[:250])
                        elif len(lines)<40:
                            lines.append(s_strip[:250])
                except OSError:pass
            events = []
            ops_candidates = sorted(folder.glob('**/operations.jsonl'), key=lambda p: p.stat().st_mtime)
            if ops_candidates:
                try:
                    for line in ops_candidates[-1].read_text(encoding='utf-8', errors='replace').splitlines()[-20:]:
                        if line.strip():
                            events.append(json.loads(line))
                except Exception:pass
            if not lines and events:
                for ev in events:
                    op=ev.get('operation') or ev.get('stage') or 'stage'
                    fn=ev.get('function') or ''
                    st=ev.get('status') or ''
                    t=ev.get('at','')
                    t_str=f"[{t[11:19]}] " if len(t)>=19 else ""
                    lines.append(f"stage: {t_str}{op} -> {fn} ({st})"[:250])
            if not lines and engine.state.get('status')=='running':
                cur_proj=engine.state.get('project','')
                cur_tick=engine.state.get('ticket_id') or engine.state.get('requested_ticket') or ''
                cur_phase=engine.state.get('phase','running')
                lines.append(f"gitive: Inicjalizacja zadania {cur_tick} w projekcie {cur_proj} (etap: {cur_phase})")
            return self.send(200, {'lines': lines[-40:], 'events': events, 'state': engine.state})
        if self.path=='/api/projects':
            from .projects import Projects
            return self.send(200,Projects(engine.root,engine.data).all())
        if self.path=='/api/rank':
            from .projects import winner
            try: return self.send(200,winner(engine.root))
            except RuntimeError as exc:return self.send(409,{'error':str(exc)})
        self.send(404,{'error':'not found'})
    def do_POST(self):
        if self.headers.get('X-Loop-Token')!=TOKEN: return self.send(403,{'error':'Otwórz panel ponownie'})
        try:
            length=int(self.headers.get('Content-Length','0'))
            if not 0<length<16000: raise ValueError('body limit')
            body=json.loads(self.rfile.read(length))
            if self.path in ('/api/control/action', '/api/integrations/realize'):
                from .control import action
                with engine.lock:
                    if workspace.state.get('status')=='running':raise RuntimeError('Operacja workspace trwa')
                    if engine.state.get('status') in ('running','stopping') and body.get('action') in ('run-ticket','realize-remote-ticket'):
                        raise RuntimeError('Pętla Gitive jest już aktywna — zaczekaj na zakończenie')
                    if self.path=='/api/integrations/realize':
                        body['action'] = 'realize-remote-ticket'
                        from .integrations import match_project_for_repo
                        from .projects import Projects
                        all_p = Projects(engine.root, engine.data).all()
                        if not body.get('project') and body.get('repository'):
                            body['project'] = match_project_for_repo(body['repository'], all_p)
                    value=action(engine,body)
            elif self.path=='/api/workspace':
                with engine.lock:
                    if engine.state.get('status') in ('running','stopping'):raise RuntimeError('Zatrzymaj pętlę Gitive przed operacją workspace')
                    value=workspace.start(**body)
            elif self.path=='/api/start':
                with engine.lock:
                    if workspace.state.get('status')=='running':raise RuntimeError('Operacja workspace trwa')
                    value=engine.start(**body)
            elif self.path=='/api/job':
                from .jobs import start
                with engine.lock:
                    if workspace.state.get('status')=='running':raise RuntimeError('Operacja workspace trwa')
                    value=start(engine,**body)
            elif self.path=='/api/projects':
                from .projects import Projects
                if 'test_command' in body:
                    body['test_argv']=shlex.split(body.pop('test_command'))
                with engine.lock:
                    value=Projects(engine.root,engine.data).add(**body)
            elif self.path=='/api/stop': engine.stop(); value=engine.state
            else: return self.send(404,{'error':'not found'})
            self.send(200,value)
        except RuntimeError as exc:
            print(f'[gitive action] 409 Conflict: {exc}', flush=True)
            self.send(409,{'error':str(exc)})
        except ValueError as exc:
            print(f'[gitive action] 400 Bad Request: {exc}', flush=True)
            self.send(400,{'error':str(exc)[:300]})
        except (TypeError,OSError) as exc:
            print(f'[gitive action] 400 Bad Request (Type/OS): {exc}', flush=True)
            self.send(400,{'error':'Niepoprawne parametry lub niedostępny folder'})

def main():
    global engine, workspace
    os.umask(0o077)
    import fcntl
    data=Path(os.getenv('LOOP_DATA','/data')); data.mkdir(parents=True,exist_ok=True)
    lock=(data/'service.lock').open('a')
    fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    engine=Engine(os.getenv('PROJECT_ROOT','/workspace/github/semcod/gitive'),os.getenv('LOOP_DATA','/data'))
    from .workspace import Workspace
    workspace=Workspace(engine.root,engine.data)
    ThreadingHTTPServer(('0.0.0.0',8787),Handler).serve_forever()
if __name__=='__main__': main()
