"""Idempotent local demo projects. Sources are owned scaffolds, never user repos."""
import json
import os
from pathlib import Path
import subprocess
import urllib.request
from .cli import request
from .digitaltwin import DigitalTwin,local_path
from .engine import write
from .planfile_bridge import PlanfileBridge

DEFINITIONS={
 'atlas-api':dict(title='Atlas API',goal='API katalogu produktów · walidacja i paginacja',code='def page(items, number=1, size=2):\n    if number < 1 or size < 1: raise ValueError("positive page and size required")\n    return items[(number-1)*size:number*size]\n',test='''import unittest
from src.app import page
class Pagination(unittest.TestCase):
    def test_second_page(self): self.assertEqual(page([1,2,3,4,5],2),[3,4])
    def test_empty(self): self.assertEqual(page([],1),[])
    def test_invalid(self):
        with self.assertRaises(ValueError): page([1],0)
''',tickets=[('Paginacja katalogu: testy brzegowe','gpt6','open'),('Kontrakt odpowiedzi API','glm53','review'),('Weryfikacja pustej kolekcji','opus5','open')]),
 'orbit-web':dict(title='Orbit Web',goal='Formularze web · bezpieczny HTML i czytelne komunikaty',code='from html import escape\n\ndef card(name):\n    return "<h1>" + escape(name) + "</h1>"\n',test='''import unittest
from src.app import card
class Rendering(unittest.TestCase):
    def test_title(self): self.assertEqual(card("Orbit"),"<h1>Orbit</h1>")
    def test_untrusted_text(self): self.assertNotIn("<script>",card("<script>"))
    def test_ampersand(self): self.assertIn("&amp;",card("A & B"))
''',tickets=[('Obsługa pustego formularza','opus5','open'),('Przegląd komunikatów walidacji','gpt6','review'),('Testy znaków specjalnych','glm53','open')]),
 'relay-jobs':dict(title='Relay Jobs',goal='Kolejka zadań · kontrolowany błąd ponawiania',code='def retry_delay(attempt):\n    # Controlled defect: exponential backoff is expected.\n    return attempt * 2\n',test='''import unittest
from src.app import retry_delay
class Retry(unittest.TestCase):
    def test_first(self): self.assertEqual(retry_delay(1),2)
    def test_second(self): self.assertEqual(retry_delay(2),4)
    def test_third(self): self.assertEqual(retry_delay(3),8)
''',tickets=[('Napraw wykładniczy backoff','glm53','open'),('Limity liczby ponowień','gpt6','blocked'),('Weryfikacja logów kolejki','opus5','review')]),
}

def main():
    os.umask(0o077)
    github=Path(os.getenv('GITIVE_GITHUB_ROOT','/home/tom/github'))
    python=Path.home()/'.local/share/uv/python/cpython-3.12.13-linux-x86_64-gnu/bin/python3.12'
    if not python.is_file():raise ValueError('Demo wymaga lokalnego Python 3.12.13: '+str(python))
    twin=DigitalTwin()
    for name,d in DEFINITIONS.items():
        source=github/'gitive-demos'/name
        if source.exists():
            if not (source/'.gitive-demo.json').is_file() or json.loads((source/'.gitive-demo.json').read_text()).get('name')!=name:raise ValueError('Istniejący folder nie jest zarządzanym demo: '+str(source))
        else:
            source.mkdir(parents=True)
            (source/'src').mkdir();(source/'src/__init__.py').write_text('');(source/'src/app.py').write_text(d['code']);(source/'test_app.py').write_text(d['test'])
            (source/'README.md').write_text('# '+d['title']+'\n\nLokalny projekt demonstracyjny Gitive.\n\n'+d['goal']+'\n\nTesty: `python3 -m unittest -v`\n')
            (source/'.gitignore').write_text('__pycache__/\n.planfile/\n.venv/\n')
            write(source/'.gitive-demo.json',{'name':name,'version':1})
            for args in (['init','-b','main'],['add','.'],['-c','user.name=Gitive Demo','-c','user.email=demo@localhost','commit','-m','Initialize controlled local demo']):
                subprocess.run(['git','-C',str(source),*args],check=True,capture_output=True)
        if not (source/'.venv/bin/python').is_file():
            subprocess.run([str(python),'-m','venv','--without-pip',str(source/'.venv')],check=True)
        registered=request('/api/projects')
        if name in registered and (registered[name].get('source_path')!='/source/github/gitive-demos/'+name or not registered[name].get('copy_only')):
            raise ValueError('Nazwa demo zajęta przez inny projekt: '+name)
        if name not in registered:
            request('/api/projects',{'name':name,'path':'/source/github/gitive-demos/'+name,'goal':d['goal'],'test_argv':['python3','-m','unittest','-v'],'allow':'src'})
        if name not in twin.all()['workspaces']:
            print('Przygotowanie runtime '+name,flush=True);twin.prepare(name,python=str(source/'.venv/bin/python'))
        with twin.lock:
            registry=json.loads(twin.projects.read_text());registry[name].update(display_name=d['title'],demo=True);write(twin.projects,registry)
        bridge=PlanfileBridge(local_path(twin.record(name)['path'],twin.base))
        for index,(title,engine,status) in enumerate(d['tickets']):
            key='demo:v1:'+str(index)
            exists=any(t.source.context.get('gitive_key')==key for t in bridge.store.list_tickets(sprint='gitive') if t.source)
            ticket=bridge.ensure(key,title,engine,'Scenariusz demonstracyjny lokalnego projektu. Status startowy ustawiony ręcznie; nie stanowi wyniku wykonania agenta. Kryterium: testy projektu przechodzą w jego prywatnym runtime.')
            if not exists and status!='open':bridge.store.update_ticket(ticket.id,status=status,actor='gitive.demo',reason='Manual demo starting state')
        print(name+': workspace gotowy, 3 tickety Planfile',flush=True)
if __name__=='__main__':main()
