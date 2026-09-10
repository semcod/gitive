import json
import os
from pathlib import Path
import secrets
import shlex
from urllib.parse import urlsplit, parse_qs
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from .engine import Engine

HTML=Path(__file__).with_name('index.html').read_text()
TOKEN=secrets.token_urlsafe(32)
engine=None
workspace=None
class Handler(BaseHTTPRequestHandler):
    def log_message(self,*args): pass
    def send(self,code,data,kind='application/json'):
        raw=data.encode() if isinstance(data,str) else json.dumps(data,ensure_ascii=False).encode()
        self.send_response(code); self.send_header('Content-Type',kind); self.send_header('Content-Length',str(len(raw)))
        self.send_header('Cache-Control','no-store'); self.send_header('X-Content-Type-Options','nosniff'); self.end_headers(); self.wfile.write(raw)
    def do_GET(self):
        if self.path in ('/control.js','/control.css'):
            return self.send(200,Path(__file__).with_name(self.path[1:]).read_text(),('text/css' if self.path.endswith('.css') else 'text/javascript')+'; charset=utf-8')
        if self.path=='/api/control':
            from .control import dashboard
            try:return self.send(200,dashboard(engine))
            except (ValueError,OSError):return self.send(409,{'error':'Stan projektu chwilowo niedostępny'})
        if self.path.split('?')[0]=='/tools':
            return self.send(200,Path(__file__).with_name('tools.html').read_text().replace('__TOKEN__',TOKEN).replace('__NOVNC__',os.getenv('NOVNC_URL','http://127.0.0.1:6083/vnc.html')), 'text/html; charset=utf-8')
        if self.path=='/workspace-ui.js':return self.send(200,Path(__file__).with_name('workspace-ui.js').read_text(),'text/javascript; charset=utf-8')
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
            logs=sorted(folder.glob('*.log'),key=lambda p:p.stat().st_mtime)
            lines=[]
            for log in logs[-3:]:
                with log.open('rb') as stream:
                    stream.seek(max(0,log.stat().st_size-16000));tail=stream.read().decode(errors='replace')
                lines += [s[:250] for s in tail.splitlines() if s.startswith(('START ','ITERATION ','GITIVE_RESULT ','WORKER FAILED '))]
            return self.send(200,lines[-30:])
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
            if self.path=='/api/control/action':
                from .control import action
                with engine.lock:
                    if workspace.state.get('status')=='running':raise RuntimeError('Operacja workspace trwa')
                    if engine.state.get('status') in ('running','stopping'):raise RuntimeError('Najpierw zatrzymaj pętlę Gitive')
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
        except RuntimeError as exc: self.send(409,{'error':str(exc)})
        except ValueError as exc: self.send(400,{'error':str(exc)[:300]})
        except (TypeError,OSError): self.send(400,{'error':'Niepoprawne parametry lub niedostępny folder'})

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
