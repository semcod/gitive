#!/usr/bin/env python3
"""Run nine isolated solution/project workers sequentially; each performs three iterations."""
from __future__ import annotations
import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import uuid
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from benchmark.common import ROOT,dump,git,source_snapshot,utc
from benchmark.fixtures import PROJECTS,FIXTURE_VERSION
from benchmark.report import summarize


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--solutions',nargs='+',choices=['glm53','gpt6','opus5'],default=['glm53','gpt6','opus5'])
    p.add_argument('--projects',nargs='+',choices=list(PROJECTS),default=list(PROJECTS))
    p.add_argument('--iterations',type=int,choices=[1,2,3],default=3)
    p.add_argument('--seed',type=int,default=7); p.add_argument('--mock',action='store_true')
    p.add_argument('--report',type=Path,help='Only regenerate the report for an existing run')
    args=p.parse_args()
    if args.report:
        print(json.dumps(summarize(args.report),indent=2)); return
    if len(set(args.solutions))!=len(args.solutions) or len(set(args.projects))!=len(args.projects):
        p.error('Duplicate solutions/projects')
    from dotenv import load_dotenv
    load_dotenv(ROOT/'.env',override=False,interpolate=False)
    if not args.mock and not os.getenv('OPENROUTER_API_KEY'): p.error('OPENROUTER_API_KEY is required in shared .env')
    stamp=utc().replace('-','').replace(':','').replace('+0000','Z').replace('.','-')
    stamp=stamp[:15]+'Z-'+uuid.uuid4().hex[:6]
    run_dir=ROOT/'benchmark/runs'/stamp
    private=ROOT/'.subactor/recovery/benchmark'/stamp
    run_dir.mkdir(parents=True,exist_ok=False); private.mkdir(parents=True,exist_ok=False)
    manifest=dict(execution_version=3,fixture_version=FIXTURE_VERSION,case_counts={p:len(PROJECTS[p]['cases']) for p in args.projects},run_id=stamp,started=utc(),mode='mock' if args.mock else 'live',model=os.getenv('LLM_MODEL','openrouter/z-ai/glm-5.3'),
        reasoning_effort=os.getenv('LLM_REASONING_EFFORT','low'),solutions=args.solutions,projects=args.projects,iterations=args.iterations,
        transcript_capture='redacted-sdk-request-response-v1',seed=args.seed,git_head=git(ROOT,'rev-parse','HEAD'),source_hashes=source_snapshot(),private_work_dir=str(private),
        max_calls_per_pair=args.iterations*2,request_timeout=120,worker_timeout=args.iterations*300,
        note='Native components plus disclosed local bridges; no remote publication')
    dump(run_dir/'manifest.json',manifest)
    print('BENCHMARK_RUN='+str(run_dir),flush=True)
    for solution in args.solutions:
        for project in args.projects:
            print(f'START {solution}/{project}',flush=True)
            cmd=[sys.executable,'-u',str(ROOT/'benchmark/worker.py'),'--run-dir',str(run_dir),'--work-dir',str(private/solution/project),
                 '--solution',solution,'--project',project,'--iterations',str(args.iterations),'--seed',str(args.seed)]
            if args.mock: cmd.append('--mock')
            log=private/f'{solution}--{project}.log'
            try:
                with log.open('w') as stream:
                    process=subprocess.Popen(cmd,cwd=ROOT,stdout=stream,stderr=subprocess.STDOUT,start_new_session=True)
                    try: code=process.wait(timeout=args.iterations*300)
                    except subprocess.TimeoutExpired:
                        import signal
                        os.killpg(process.pid,signal.SIGTERM); process.wait(timeout=10); code=124
            except Exception as exc:
                code=125
            if code:
                print(f'WORKER FAILED {solution}/{project}: exit={code}; private log={log}',flush=True)
                for iteration in range(1,args.iterations+1):
                    path=run_dir/'iterations'/f'{solution}--{project}--{iteration}.json'
                    if not path.exists(): dump(path,dict(solution=solution,project=project,iteration=iteration,status='worker_failed',worker_exit=code,accepted=False,seconds=0,llm_calls=[]))
            else:
                for path in sorted((run_dir/'iterations').glob(f'{solution}--{project}--*.json')):
                    row=json.loads(path.read_text()); after=row.get('after',{})
                    print(f"ITERATION {solution}/{project}/{row['iteration']}: {row['status']} tests={after.get('passed')}/{after.get('total')} seconds={row['seconds']}",flush=True)
            summarize(run_dir)
    manifest['finished']=utc(); dump(run_dir/'manifest.json',manifest)
    summary=summarize(run_dir)
    dump(ROOT/'benchmark/latest.json',dict(run_id=stamp,report=f'runs/{stamp}/report.md',mode=manifest['mode']))
    print('REPORT='+str(run_dir/'report.md'),flush=True)
    print(json.dumps(summary,indent=2),flush=True)


if __name__=='__main__': main()
