"""Native planning/validation components, with explicitly identified local execution bridges.
Only one adapter is imported per subprocess: glm53 and opus5 share the package name intuition.
"""
from __future__ import annotations
import json
import os
import sys
import time
from pathlib import Path
from .common import ROOT, dump, git, sha, utc



class GLM53:
    label = 'native critic + native patch validator + local test/commit bridge'
    def __init__(self, root, description, seed):
        sys.path.insert(0,str(ROOT/'glm53'))
        from intuition.store import Store
        self.store=Store(root); self.seed=seed
        from intuition.llm import Client
        self.client=Client('litellm')
        self.store.init(description,m=2)

    def propose_patch(self, evidence, code, iteration):
        from intuition.core import choose
        from intuition.refactor import PATCH, validate_edits
        observation=dict(content=evidence,tags=['ci','error','open'],references=[])
        if hasattr(self,'evidence_id'): observation['supersedes']=self.evidence_id
        files,ids=self.store.fact_files([observation],f'benchmark:{iteration}')
        self.evidence_id=ids[0]
        self.store.transaction(files,f'benchmark evidence {iteration}')
        self.state=self.store.state()
        parsed_ev = {}
        try: parsed_ev = json.loads(evidence) if isinstance(evidence, str) else (evidence or {})
        except Exception: pass
        if parsed_ev.get('ticket_title'):
            self.task = {'archetype': 'derive', 'prompt': parsed_ev['ticket_title'], 'references': [self.evidence_id], 'rationale': (parsed_ev.get('ticket_description') or parsed_ev['ticket_title'])[:500]}
            self.candidates = [self.task]
            self.probs = [1.0]
        else:
            self.task,self.candidates,self.probs=choose(self.client,self.store.facts(),self.state,self.seed,code)
        payload=dict(task=self.task,files=code,test_failures=evidence)
        edits=validate_edits(self.client(PATCH,json.dumps(payload),.2),code)
        return self.task,edits

    def feedback(self, summary, accepted):
        if not hasattr(self,'task'): return
        from intuition.core import persist
        persist(self.store,self.task,[dict(content=summary,tags=['observation','test'],references=self.task['references'])],
                self.state,self.candidates,self.probs,self.seed,dict(benchmark=True,patch_accepted=accepted,execution_reward=int(accepted)))
        del self.task


class GPT6:
    label = 'native task scorer + native patch validator + local controller bridge'
    def __init__(self, root, description, seed):
        sys.path.insert(0,str(ROOT/'gpt6'))
        from intuition_github.config import load_config
        from intuition_github.memory import initial_state
        from intuition_github.llm import LiteLLMClient
        from intuition_github.util import Redactor
        self.root=root; self.config=load_config(ROOT/'gpt6/.intuition/config.json')
        self.config['allowed_paths']=['src/*.py']; self.config['goal']=description
        self.config['task_cooldown_days']=0
        self.state=initial_state(self.config); self.client=LiteLLMClient(self.config); self.redactor=Redactor()
        self.statefile=root/'.bench/native-state.json'

    def propose_patch(self,evidence,code,iteration):
        from intuition_github.planning import TASK_CONTRACT,PATCH_CONTRACT,validate_tasks,validate_patch
        self.base=git(self.root,'rev-parse','HEAD')
        fact=dict(id=f'local-ci:{iteration}',text=evidence,kind='ci_failure',source=f'local://iteration/{iteration}',observed_at=utc())
        self.state['facts'].append(fact)
        current_facts=[fact]
        pending=getattr(self,'pending_task',None)
        parsed_ev = {}
        try: parsed_ev = json.loads(evidence) if isinstance(evidence, str) else (evidence or {})
        except Exception: pass
        if pending is not None:
            if pending['base_sha'] != self.base:
                raise ValueError('Pending benchmark task has a stale base')
            self.task=pending
        elif parsed_ev.get('ticket_title'):
            tid = f"task:{parsed_ev.get('ticket_id', iteration)}"
            self.task = {
                'id': tid,
                'title': parsed_ev['ticket_title'][:120],
                'profile': 'patch',
                'facts': [fact['id']],
                'depends_on': [],
                'acceptance': (parsed_ev.get('ticket_description') or parsed_ev['ticket_title'])[:500],
                'rationale': (parsed_ev.get('ticket_description') or '')[:300],
                'target_files': list(code)[:5],
                'status': 'ready',
                'base_sha': self.base
            }
            self.state['tasks'][self.task['id']] = self.task
        else:
            reply,_=self.client.complete('propose_tasks',dict(goal=self.config['goal'],base_sha=self.base,output_contract=TASK_CONTRACT,
                         profiles=list(self.config['profiles']),untrusted_facts=current_facts,untrusted_source_files=code,
                         existing_tasks=[{k:t[k] for k in ('profile','target_files','status')} for t in list(self.state['tasks'].values())[-30:]]))
            tasks=validate_tasks(reply,self.base,current_facts,list(code),self.config,self.state)
            if not tasks: raise ValueError('GPT6 native planner returned no eligible tasks')
            self.task=tasks[0]; self.state['tasks'][self.task['id']]=self.task
        original={p:c.encode() for p,c in code.items()}
        reply,_=self.client.complete('propose_patch',dict(base_sha=self.base,output_contract=PATCH_CONTRACT,
                  task={k:self.task[k] for k in ('title','profile','acceptance','rationale','target_files')},
                  untrusted_facts=current_facts,untrusted_files=[dict(path=p,content=c,sha256=sha(c)) for p,c in code.items()],
                  max_changed_lines=self.config['max_patch_changed_lines'],
                  **({'previous_rejection':self.task['patch_rejection']} if self.task.get('patch_rejection') else {})))
        try:
            edits=validate_patch(reply,self.base,original,self.config,self.redactor)
        except ValueError as exc:
            self.task['patch_rejection']=self.redactor.clean(str(exc))[:1000]
            raise
        return self.task,{p:v.decode() for p,v in edits.items()}

    def feedback(self,summary,accepted):
        if hasattr(self,'task'):
            profile=self.state['profile_counts'][self.task['profile']]
            profile['alpha' if accepted else 'beta']+=1
            self.task['status']='completed' if accepted else 'ready'
            self.pending_task=None if accepted else self.task
            # Local benchmark emits a new evidence group each iteration. It deliberately does not
            # emulate GitHub's wall-clock task cooldown: that production mechanism is out of scope.
            self.task['benchmark_outcome']=summary
            del self.task
        dump(self.statefile,self.state)


class Opus5:
    label = 'native cycle + native repair in isolated Git clone + external oracle'
    def __init__(self,root,description,seed):
        sys.path.insert(0,str(ROOT/'opus5/src'))
        from intuition.config import Config
        from intuition.store import write_json
        self.root=root; self.cfg=Config.load(); self.cfg.root=root/'.bench/opus5'; self.cfg.dry_run=True
        self.cfg.n_candidates=2; self.cfg.per_cycle=1; self.cfg.embed_model=''
        write_json(self.cfg.goal_path,dict(text=description,generation=1,created_at=time.time()))
        self.facts=[]; self.description=description

    def propose_patch(self,evidence,code,iteration):
        from unittest.mock import patch
        from intuition.core import cycle
        from intuition.store import read_jsonl
        import contextlib,io
        from intuition.store import write_json
        parsed_ev = {}
        try: parsed_ev = json.loads(evidence) if isinstance(evidence, str) else (evidence or {})
        except Exception: pass
        if parsed_ev.get('goal'):
            write_json(self.cfg.goal_path, dict(text=parsed_ev['goal'], generation=1, created_at=time.time()))
        fact=dict(id=f'local-ci:{iteration}',ts=time.time(),kind='ci_failure',ref=str(iteration),source='local-tests',
                  paths=list(code),text=evidence)
        if self.facts: fact['supersedes']=self.facts[-1]['id']
        self.facts.append(fact)
        # The real native cycle computes state, friction, tension, utility, softmax and task selection.
        # Only its external read transport is replaced with identical local oracle evidence.
        with patch('intuition.core.ingest',return_value=self.facts), patch('intuition.core.gh.list_issues',return_value=[]), contextlib.redirect_stdout(io.StringIO()):
            result=cycle(self.cfg,cwd=str(self.root),code=code)
        if not result.get('created'): raise ValueError('Opus5 native cycle did not select a task')
        rows=list(read_jsonl(self.cfg.ledger_path)); self.task=rows[-1]
        from intuition.repair import repair
        from benchmark.fixtures import PROJECTS
        from benchmark.common import test
        import tempfile, shutil
        test_argv = getattr(self, 'native_test_argv', None)
        if test_argv is None:
            project = next(k for k,v in PROJECTS.items() if v['description'] == self.description)
            before = test(self.root, project, 3)
            allowed_failures = json.dumps([f['id'] for f in before['failures']])
            test_argv = [sys.executable, str(ROOT/'benchmark/native_gate.py'), project, str(iteration), allowed_failures]
        # Native repair owns its clone, tests, API validation, rollback and execution memory.
        # An outer clone keeps its commits separate from the benchmark's final acceptance gate.
        with tempfile.TemporaryDirectory(prefix='benchmark-opus-native-') as temp:
            work = Path(temp)/'repo'
            git(self.root, 'clone', '--quiet', '--no-hardlinks', str(self.root), str(work))
            for key in ('user.name','user.email'):
                git(work,'config',key,git(self.root,'config',key))
            memory = self.root/'.bench/native-repair'
            if memory.exists():
                shutil.copytree(memory,work/'.intuition-repair')
                git(work,'add','--','.intuition-repair')
                git(work,'commit','-m','Restore native execution memory')
            outcome = repair(self.cfg, work, self.task,
                test_argv)
            self.native_outcome = outcome
            if (work/'.intuition-repair').exists():
                shutil.copytree(work/'.intuition-repair', memory, dirs_exist_ok=True)
            if not outcome.get('passed'):
                raise ValueError('Native Opus5 repair rejected by test gate')
            edits = {name:(work/name).read_text() for name in code if (work/name).read_text()!=code[name]}
        return self.task,edits

    def feedback(self,summary,accepted):
        from intuition import model
        from intuition.core import _theta,_save_theta
        from intuition.store import append_jsonl
        if hasattr(self,'task'):
            import numpy as np
            updated=model.update_theta(_theta(self.cfg),np.asarray(self.task['phi']),int(accepted),self.cfg.lr)
            _save_theta(self.cfg,updated,{'feedback_source':'benchmark-test-gate'})
            append_jsonl(self.cfg.ledger_path,[dict(id=self.task['id'],resolution=True,y=int(accepted),resolved_at=time.time(),
                          title=self.task['title'],phi=self.task['phi'],benchmark_outcome=summary)])
            del self.task


ADAPTERS={'glm53':GLM53,'gpt6':GPT6,'opus5':Opus5}
