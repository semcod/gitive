"""Per-project Planfile store and bounded, explicit GitHub synchronization.

All three Gitive executors share this boundary. It never scans/publishes unrelated
GitHub tickets, and never merges PRs. Credentials stay in process memory.
"""
import hashlib
import json
import os
from pathlib import Path
import subprocess
from filelock import FileLock

ENGINES=('glm53','gpt6','opus5')

def signature(value):return hashlib.sha256(json.dumps(value,sort_keys=True).encode()).hexdigest()
def local_version(ticket):return signature([ticket.name,ticket.description,ticket.status.value])
def remote_version(ticket):return signature([ticket.name,ticket.description,ticket.status])

class PlanfileBridge:
    def __init__(self,project,repository=None,backend=None):
        from planfile.core.store import Store
        self.root=Path(project).resolve();self.repository=repository;self.backend=backend
        if (self.root/'.git').is_dir():
            exclude=self.root/'.git/info/exclude';exclude.parent.mkdir(parents=True,exist_ok=True)
            existing=exclude.read_text() if exclude.exists() else ''
            if '/.planfile/' not in existing.splitlines():exclude.write_text(existing+'\n/.planfile/\n')
        self.store=Store(self.root)
        self.store.base_dir.mkdir(parents=True,exist_ok=True)
        self.lock=FileLock(str(self.store.base_dir/"gitive-integration.lock"),timeout=30)
    def ensure(self,key,title,engine,description=''):
        from planfile.core.models import Ticket,TicketSource,TicketExecutor
        if engine not in ENGINES:raise ValueError('Nieznany wykonawca')
        with self.lock:
            for ticket in self.store.list_tickets(sprint='gitive'):
                if ticket.source and ticket.source.context.get('gitive_key')==key:
                    if ticket.executor.handler!=engine:raise ValueError('Ticket przypisany do innego wykonawcy')
                    return ticket
            ticket=Ticket(id=self.store.next_id(),name=title,description=description,sprint='gitive',priority='low',
                source=TicketSource(tool='gitive',context={'gitive_key':key}),
                executor=TicketExecutor(kind='llm',mode='manual',handler=engine))
            return self.store.create_ticket(ticket)
    def outcome(self,ticket_id,status):
        # A code repair is awaiting independent validation, never automatically done/merged.
        mapped={'already_green':'done','repaired':'in_progress','rejected':'blocked','error':'blocked'}.get(status,'blocked')
        return self.store.update_ticket(ticket_id,status=mapped,reason='Gitive result: '+status,actor='gitive')
    def github(self):
        if self.backend is None:
            from planfile.sync.github import GitHubBackend
            token=os.getenv('GH_TOKEN') or os.getenv('GITHUB_TOKEN')
            if not token:
                response=subprocess.run(['gh','auth','token'],capture_output=True,text=True)
                if response.returncode:raise RuntimeError('Brak uwierzytelnienia gh')
                token=response.stdout.strip()
            if not token:raise RuntimeError('Brak tokenu GitHub')
            self.backend=GitHubBackend(self.repository,token=token)
        return self.backend
    def sync(self,ticket_id,direction='push'):
        if direction not in ('push','pull'):raise ValueError('Wybierz push lub pull')
        if not self.repository or self.repository.count('/')!=1:raise ValueError('Wymagane repo owner/name')
        with self.lock:
            ticket=self.store.get_ticket(ticket_id)
            if ticket is None:raise ValueError('Nieznany ticket')
            if not ticket.source or ticket.source.tool!='gitive':raise ValueError('Ticket nie należy do integracji Gitive')
            binding=ticket.sync.get('github',{})
            if binding and binding.get('repository')!=self.repository:raise ValueError('Ticket przypisany do innego repozytorium')
            backend=self.github()
            key='gitive:'+self.repository+':'+ticket.source.context['gitive_key']
            marker='<!-- planfile:deduplication-key='+key+' -->'
            current=backend.get_ticket(binding['id']) if binding.get('id') else None
            if current and (not current.url.startswith('https://github.com/'+self.repository+'/issues/') or marker not in current.description):raise RuntimeError('Niezgodne powiązanie zdalnego ticketu')
            if direction=='push':
                if current and binding.get('remote_version')!=remote_version(current):raise RuntimeError('Zdalny ticket zmienił się; najpierw pull (bez nadpisania)')
                body=ticket.description if marker in ticket.description else marker+'\n'+ticket.description+'\n\nPlanfile: '+ticket.id
                state='closed' if ticket.status.value in ('done','canceled') else 'open'
                if current:
                    backend.update_ticket(binding['id'],name=ticket.name,body=body,status=state)
                    rid=binding['id']
                else:
                    ref=backend.create_ticket({'name':ticket.name,'description':body,'metadata':{'deduplication_key':key,'planfile_id':ticket.id}})
                    rid=ref.id
                    if state=='closed':backend.update_ticket(rid,status=state)
                current=backend.get_ticket(rid)
                if current.name!=ticket.name or marker not in current.description or current.status!=state:raise RuntimeError('Niepotwierdzona synchronizacja GitHub')
            else:
                if current is None:raise ValueError('Najpierw opublikuj powiązany ticket')
                if binding.get('local_version')!=local_version(ticket):raise RuntimeError('Lokalny ticket zmienił się; konflikt bez nadpisania')
                status='done' if current.status=='closed' else ('open' if ticket.status.value in ('done','canceled') else ticket.status.value)
                ticket=self.store.update_ticket(ticket.id,name=current.name,description=current.description,status=status,actor='gitive.github',reason='Explicit GitHub readback')
            binding={'repository':self.repository,'id':current.id,'url':current.url,'local_version':local_version(ticket),'remote_version':remote_version(current),'status':current.status}
            self.store.update_ticket(ticket.id,sync={**ticket.sync,'github':binding})
            return {'planfile_id':ticket.id,'github_url':current.url,'direction':direction,'status':'synchronized','remote_state':current.status}
