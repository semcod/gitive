"""One solution × project: three consecutive repair iterations in its own Git repository."""
from __future__ import annotations
import argparse
import difflib
import json
import os
from pathlib import Path
import sys
import time
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from benchmark.common import ROOT,dump,git,sha,test,utc,validate_edits
from benchmark.fixtures import PROJECTS
from benchmark.adapters import ADAPTERS


def main():
    p=argparse.ArgumentParser(); p.add_argument('--run-dir',required=True); p.add_argument('--work-dir',required=True)
    p.add_argument('--solution',choices=list(ADAPTERS),required=True); p.add_argument('--project',choices=list(PROJECTS),required=True)
    p.add_argument('--iterations',type=int,default=3); p.add_argument('--seed',type=int,default=7); p.add_argument('--mock',action='store_true')
    args=p.parse_args(); run_dir=Path(args.run_dir); root=Path(args.work_dir); spec=PROJECTS[args.project]
    root.mkdir(parents=True,exist_ok=False); (root/'src').mkdir(); (root/'.bench').mkdir()
    (root/'src/core.py').write_text(spec['source']); (root/'README.md').write_text(spec['description'])
    (root/'.gitignore').write_text('.bench/\n__pycache__/\n.intuition.lock\n.intuition-pending.json\n')
    git(root,'init','-b','main'); git(root,'config','user.name','Benchmark'); git(root,'config','user.email','benchmark@example.invalid')
    git(root,'add','src/core.py','README.md','.gitignore'); git(root,'commit','-m','Controlled faulty fixture')
    calls=[]
    iteration=0
    from benchmark.transcripts import Recorder, phase
    recorder=Recorder(root/".bench/transcripts", ROOT)
    if not args.mock:
        from dotenv import load_dotenv
        load_dotenv(ROOT/'.env',override=False,interpolate=False)
        os.environ.setdefault('LLM_REASONING_EFFORT','low')
        import litellm
        original=litellm.completion
        def measured(*a,**kw):
            if len(calls)>=args.iterations*2: raise RuntimeError('Benchmark call budget exhausted')
            kw['num_retries']=0; kw['timeout']=120
            call_id=f'{args.solution}--{args.project}--{len(calls)+1:03d}'
            entry={'id':call_id,'iteration':iteration,'phase':phase(kw),'started':utc(),'model':kw.get('model'),'status':'started'}
            if a:
                raise ValueError('Positional LLM arguments are not supported by transcript capture')
            entry['request_receipt']=recorder.request(call_id,kw,dict(solution=args.solution,project=args.project,
                                                        iteration=iteration,phase=entry['phase'],started=entry['started']))
            calls.append(entry); start=time.monotonic()
            dump(root/'.bench/llm-calls.json',calls)
            try:
                response=original(*a,**kw)
                entry["response_receipt"]=recorder.response(call_id,response)
                usage=response.usage
                entry.update(status='ok',prompt_tokens=usage.prompt_tokens,completion_tokens=usage.completion_tokens,
                             total_tokens=usage.total_tokens,finish_reason=response.choices[0].finish_reason)
                cost=getattr(response,'_hidden_params',{}).get('response_cost')
                entry['cost_usd']=cost if isinstance(cost,(int,float)) else None
                return response
            except Exception as exc:
                entry.update(status='error',error_type=type(exc).__name__)
                entry['error_receipt']=recorder.write(call_id,'error',{'type':type(exc).__name__,'message':str(exc)})
                raise
            finally:
                entry['seconds']=round(time.monotonic()-start,3)
                dump(root/'.bench/llm-calls.json',calls)
        litellm.completion=measured
        adapter=ADAPTERS[args.solution](root,spec['description'],args.seed)
    else:
        adapter=None
    initial=test(root,args.project,3)
    dump(run_dir/'baselines'/f'{args.solution}--{args.project}.json',initial)
    for iteration in range(1,args.iterations+1):
        started=time.monotonic(); start_calls=len(calls)
        before=test(root,args.project,iteration); full_before=test(root,args.project,3)
        originals={'src/core.py':(root/'src/core.py').read_text()}
        row=dict(solution=args.solution,project=args.project,iteration=iteration,started=utc(),adapter=ADAPTERS[args.solution].label,
                 before=before,full_before=full_before,source_before=sha(originals['src/core.py']),head_before=git(root,'rev-parse','HEAD'),
                 mode='mock' if args.mock else 'live',accepted=False,status='pending')
        task=None; edits={}; candidate=before; full_candidate=full_before
        try:
            if before['green']:
                row['status']='already_green'
            elif args.mock:
                row['status']='mock_no_repair'
            else:
                evidence=json.dumps(dict(project=spec['description'],iteration=iteration,scope='Fix currently failing tests in src/core.py; preserve all behavior',
                                        failing_tests=before['failures']),ensure_ascii=False)
                task,edits=adapter.propose_patch(evidence,originals,iteration)
                edits=validate_edits(edits,originals)
                if not edits: raise ValueError('No source changes proposed')
                for name,content in edits.items(): (root/name).write_text(content)
                candidate=test(root,args.project,iteration); full_candidate=test(root,args.project,3)
                before_failed={f['id'] for f in full_before['failures']}; after_failed={f['id'] for f in full_candidate['failures']}
                row['regressions']=sorted(after_failed-before_failed)
                row['accepted']=candidate['passed']>before['passed'] and not row['regressions']
                diff=''.join(difflib.unified_diff(originals['src/core.py'].splitlines(True),(root/'src/core.py').read_text().splitlines(True),fromfile='a/src/core.py',tofile='b/src/core.py'))
                patch=run_dir/'patches'/f'{args.solution}--{args.project}--{iteration}.diff'; patch.parent.mkdir(exist_ok=True); patch.write_text(diff)
                row['patch']=str(patch.relative_to(run_dir)); row['changed_lines']=sum(line.startswith(('+','-')) and not line.startswith(('+++','---')) for line in diff.splitlines())
                if row['accepted']:
                    git(root,'add','--','src/core.py'); git(root,'commit','-m',f'Benchmark repair iteration {iteration}')
                    row['status']='repaired' if candidate['green'] else 'partial_improvement'
                else:
                    row['status']='rejected'
        except Exception as exc:
            row.update(status='error',error_type=type(exc).__name__,error=str(exc)[:600])
        finally:
            if not row['accepted']:
                for name,content in originals.items(): (root/name).write_text(content)
        if adapter is not None and hasattr(adapter,"native_outcome"):
            row["native_execution"]=adapter.native_outcome
            del adapter.native_outcome
        row.update(candidate=candidate,full_candidate=full_candidate)
        if adapter is not None and not before['green']:
            try:
                adapter.feedback(f"Iteration {iteration}: status={row['status']}; tests {candidate['passed']}/{candidate['total']}; accepted={row['accepted']}",row['accepted'])
            except Exception as exc:
                row['feedback_error']=type(exc).__name__+': '+str(exc)[:300]
        after=test(root,args.project,iteration); full_after=test(root,args.project,3)
        row.update(after=after,full_after=full_after,finished=utc(),seconds=round(time.monotonic()-started,3),
                   llm_calls=calls[start_calls:],head_after=git(root,'rev-parse','HEAD'),source_after=sha((root/'src/core.py').read_bytes()))
        dump(root/'.bench'/f'iteration-{iteration}.json',row)
        # Report contains only fixtures and generated edits, never raw environment/provider headers.
        rendered=json.dumps(row,ensure_ascii=False)
        for key,value in os.environ.items():
            if any(k in key for k in ('KEY','TOKEN','SECRET','PASSWORD')) and len(value)>7: rendered=rendered.replace(value,'[REDACTED]')
        safe=json.loads(rendered)
        dump(run_dir/'iterations'/f'{args.solution}--{args.project}--{iteration}.json',safe)
        print(json.dumps({k:safe[k] for k in ('solution','project','iteration','status','seconds')})+f" tests={after['passed']}/{after['total']}",flush=True)
    dump(run_dir/'final'/f'{args.solution}--{args.project}.json',dict(oracle=test(root,args.project,3),code=(root/'src/core.py').read_text(),
         state_location=str(root),head=git(root,'rev-parse','HEAD')))


if __name__=='__main__': main()
