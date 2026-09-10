"""Sequential, file-backed benchmark / Codex / verification loop."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import threading
import time
import uuid
from .hub import Hub


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    temp = path.with_name(path.name+'.'+uuid.uuid4().hex+'.tmp')
    temp.write_text(json.dumps(value,ensure_ascii=False,indent=2))
    temp.chmod(0o600); temp.replace(path)


def source_snapshot(root):
    names = subprocess.check_output(['git','ls-files','--cached','--others','--exclude-standard','-z'],cwd=root).decode().split('\0')
    result={}
    for name in names:
        if not name or name.startswith('benchmark/runs/'): continue
        p=root/name
        if p.is_symlink(): result[name]='symlink:'+os.readlink(p)
        elif p.is_file(): result[name]=hashlib.sha256(p.read_bytes()).hexdigest()
    return result


def permitted(name):
    return name.startswith(('glm53/intuition/','gpt6/intuition_github/','opus5/src/intuition/')) and name.endswith('.py')


class Engine:
    def __init__(self, root, data, hub=None):
        self.root=Path(root); self.data=Path(data); self.hub=hub or Hub()
        self.lock=threading.RLock(); self.thread=None
        self.path=self.data/'state.json'; self.state=json.loads(self.path.read_text()) if self.path.exists() else {'status':'idle'}
        if self.state.get('status') in ('running','stopping'):
            self.state.update(status='interrupted',error='Restart w trakcie operacji: sprawdź zapis i stan huba przed nowym uruchomieniem.')
            self.save()
    def save(self):
        with self.lock:
            write(self.path,self.state)
            if self.state.get("run"): write(self.data/self.state["run"]/"state.json",self.state)
    def event(self, phase, **extra):
        self.state.update(phase=phase,updated=time.time(),**extra); self.save()
    def start(self, cycles=3, demo=False, max_usd=1.0):
        if type(cycles) is not int or not 0<=cycles<=20: raise ValueError('cycles: 0 (ciągle) lub 1–20')
        if type(demo) is not bool or type(max_usd) not in (int,float) or not 0<max_usd<=100: raise ValueError('Niepoprawny limit kosztu')
        if not demo and isinstance(self.hub, Hub):
            _, plan = self.hub.plan('Read README.md. Do not change files.')
            if plan.get('request',{}).get('argument_count') != 5:
                raise RuntimeError('Hub wymaga poprawki Codex exec (ticket-030); benchmark nie został uruchomiony.')
        with self.lock:
            if self.thread and self.thread.is_alive(): raise ValueError('Pętla już działa')
            run=time.strftime('%Y%m%dT%H%M%SZ',time.gmtime())+'-'+uuid.uuid4().hex[:6]
            self.state=dict(status='running',phase='starting',run=run,cycle=0,cycles=cycles,demo=demo,
                spent_usd=0,max_usd=max_usd,stop=False,history=[])
            self.save(); self.thread=threading.Thread(target=self.run,daemon=True); self.thread.start()
        return self.state
    def stop(self):
        with self.lock:
            self.state['stop']=True
            if self.state['status']=='running': self.state['status']='stopping'
            self.save()
    def command(self, argv, name, timeout):
        folder=self.data/self.state['run']; folder.mkdir(parents=True,exist_ok=True,mode=0o700)
        log=folder/(name+'.log')
        env={k:v for k,v in os.environ.items() if k not in ('HUB_TOKEN_FILE','CONTROL_API_TOKEN')}
        with log.open('w') as stream:
            log.chmod(0o600)
            process=subprocess.Popen(argv,cwd=self.root,env=env,stdout=stream,stderr=subprocess.STDOUT,start_new_session=True)
            try: rc=process.wait(timeout)
            except subprocess.TimeoutExpired:
                import signal
                os.killpg(process.pid,signal.SIGTERM)
                try: process.wait(5)
                except subprocess.TimeoutExpired: os.killpg(process.pid,signal.SIGKILL); process.wait()
                raise RuntimeError('Timeout etapu '+name)
        if rc: raise RuntimeError(f'{name}: kod wyjścia {rc}; log prywatny: {log.name}')
        return log
    def benchmark(self, prefix):
        args=[sys.executable,'benchmark/run.py']
        if self.state['demo']: args.append('--mock')
        log=self.command(args,prefix+'-benchmark',9000)
        lines=log.read_text().splitlines()
        location=next((s.split('=',1)[1] for s in lines if s.startswith('BENCHMARK_RUN=')),None)
        if not location: raise RuntimeError('Brak identyfikatora benchmarku')
        run=Path(location).resolve()
        if run.parent != (self.root/'benchmark/runs').resolve(): raise RuntimeError('Raport poza benchmark/runs')
        summary=json.loads((run/'summary.json').read_text())
        if summary['completed_iterations']!=27: raise RuntimeError('Benchmark niekompletny')
        if not self.state['demo']:
            self.command([sys.executable,'benchmark/analyze_transcripts.py',str(run)],prefix+'-transcripts',120)
        values=list(summary['solutions'].values())
        if not self.state['demo'] and any(s.get('cost_usd') is None for s in values):
            raise RuntimeError('Nieznany koszt LLM')
        self.state['spent_usd']+=sum(s.get('cost_usd') or 0 for s in values)
        self.event(self.state['phase'],report=str(run.relative_to(self.root)),summary=summary)
        return summary
    def codex(self):
        if not self.state['demo'] and isinstance(self.hub, Hub):
            _, check = self.hub.plan('Read README.md. Do not change files.')
            if check.get('request',{}).get('argument_count') != 5:
                raise RuntimeError('Hub wymaga wdrożenia poprawki Codex exec (ticket-030); raport błędu zachowany.')
        report=self.state['report']
        analysis_rel=f".subactor/recovery/loop-app/{self.state['run']}/{self.state['cycle']}-analysis.json"
        prompt=(f'Przeanalizuj {report}/report.md, summary.json i transcript-audit.json oraz '
            'docs/analysis/quality-fixes-v2-2026-09-10.md. Wybierz i wdroż ograniczoną poprawkę jakości '
            'na podstawie dowodów. Edytuj wyłącznie istniejące moduły Python w glm53/intuition/, '
            'gpt6/intuition_github/ i opus5/src/intuition/. Zachowaj publiczne API. '
            'Nie zmieniaj testów, benchmarku, konfiguracji, dokumentów ani historii Git. '
            'Nie wykonuj operacji zdalnych. Nie uruchamiaj benchmarku ani zapytań LLM; '
            'zewnętrzny kontroler uruchomi testy i nowy benchmark. '
            f'Wyjątek od zakresu zapisu: zapisz raport w {analysis_rel}, jako obiekt JSON '
            'z polami summary (tekst), findings (lista tekstów), changed_files (lista ścieżek), limitations (lista tekstów). '
            'Powiąż ustalenia z raportem benchmarku. Nie zapisuj sekretów.')
        if self.state.get('failure_report'):
            prompt += ' Uwzględnij także raport błędu projektu: ' + self.state['failure_report'].replace(str(self.data), '.subactor/recovery/loop-app')
        folder=self.data/self.state['run']; write(folder/f"{self.state['cycle']}-prompt.json",{'prompt':prompt})
        if self.state['demo']: return {'mode':'demo','changed':False}
        before=source_snapshot(self.root)
        head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=self.root).decode()
        request,plan=self.hub.plan(prompt)
        write(folder/f"{self.state['cycle']}-plan.json",{'request':request,'plan':plan})
        self.event('codex',execution_id=request['execution_id'])
        # No replay after timeout/connection loss: Hub may have consumed the operation.
        result=self.hub.execute(request,plan)
        write(folder/f"{self.state['cycle']}-codex.json",result)
        after=source_snapshot(self.root)
        changed=[n for n in before.keys()|after.keys() if before.get(n)!=after.get(n)]
        violation=[n for n in changed if not permitted(n) or n not in before or n not in after]
        if violation or subprocess.check_output(['git','rev-parse','HEAD'],cwd=self.root).decode()!=head:
            raise RuntimeError('Zmiana poza dozwolonym zakresem; zachowano pliki do przeglądu')
        if not result.get('result',{}).get('ok'): raise RuntimeError('Codex nie potwierdził wykonania; sprawdź receipt huba')
        analysis_file=self.root/analysis_rel
        if analysis_file.is_symlink() or not analysis_file.is_file() or analysis_file.stat().st_size>32000:
            raise RuntimeError('Brak poprawnego raportu analizy Codexa')
        analysis=json.loads(analysis_file.read_text())
        if not isinstance(analysis,dict) or not isinstance(analysis.get('summary'),str):
            raise RuntimeError('Niepoprawny kontrakt raportu Codexa')
        for field in ('findings','changed_files','limitations'):
            if not isinstance(analysis.get(field),list) or not all(isinstance(x,str) for x in analysis[field]):
                raise RuntimeError('Niepoprawny kontrakt raportu Codexa')
        if set(analysis['changed_files']) != set(changed):
            raise RuntimeError('Raport Codexa nie odpowiada rzeczywistym zmianom')
        analysis_file.chmod(0o600)
        return {'changed':changed,'analysis':analysis_rel}
    def run(self):
        try:
            baseline=None
            while not self.state['stop'] and (not self.state['cycles'] or self.state['cycle']<self.state['cycles']):
                if self.state['spent_usd']>=self.state['max_usd']: break
                self.state['cycle']+=1; n=str(self.state['cycle'])
                self.event('benchmark')
                baseline=baseline or self.benchmark(n+'-before')
                if self.state['stop'] or self.state['spent_usd']>=self.state['max_usd']: break
                self.event('analysis-and-codex'); result=self.codex()
                if self.state['stop']: break
                self.event('tests')
                if not self.state['demo']: self.command(['make','test'],n+'-tests',1800)
                if self.state['stop']: break
                self.event('rebenchmark'); after=self.benchmark(n+'-after')
                regression=any(after['solutions'][s]['final_tests_passed']<baseline['solutions'][s]['final_tests_passed'] for s in baseline['solutions'])
                self.state['history'].append({'cycle':self.state['cycle'],'codex':result,'regression':regression,'report':self.state['report']})
                self.save()
                if regression: raise RuntimeError('Regresja wyniku benchmarku — pętla zatrzymana, zmiany zachowane')
                baseline=after
            self.event('finished',status='stopped' if self.state['stop'] else 'complete')
        except Exception as exc:
            # Transport exceptions may include URLs or credentials; expose only fixed messages from our layers.
            message=str(exc) if type(exc) in (RuntimeError,ValueError) else type(exc).__name__
            self.event('blocked',status='blocked',error=message[:500])
