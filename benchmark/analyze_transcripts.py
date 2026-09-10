#!/usr/bin/env python3
"""Validate private transcript receipts and emit content-free quality metrics."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from benchmark.common import ROOT, dump


def analyze(run):
    rows=[json.loads(p.read_text()) for p in sorted((run/'iterations').glob('*.json'))]
    calls=[]
    def read(receipt):
        raw=(ROOT/receipt['path']).read_bytes()
        if hashlib.sha256(raw).hexdigest()!=receipt['sha256']:
            raise ValueError('Transcript hash mismatch')
        return json.loads(raw)
    for row in rows:
        for call in row.get('llm_calls',[]):
            request=read(call['request_receipt'])['request']
            result=dict(id=call['id'],solution=row['solution'],project=row['project'],iteration=row['iteration'],
                phase=call['phase'],status=call['status'],request_receipt=call['request_receipt'],
                prompt_chars=sum(len(str(m.get('content',''))) for m in request.get('messages',[])),
                message_roles=[m.get('role') for m in request.get('messages',[])],temperature=request.get('temperature'),
                response_format=request.get('response_format'),tokens=call.get('total_tokens'),
                iteration_status=row['status'])
            if 'response_receipt' in call:
                response=read(call['response_receipt'])['response']
                content=response['choices'][0]['message'].get('content') or ''
                result.update(response_receipt=call['response_receipt'],response_chars=len(content),
                              finish_reason=response['choices'][0].get('finish_reason'))
                try:
                    data=json.loads(content)
                    result['strict_json']=True
                    result['json_shape']='array' if isinstance(data,list) else 'object' if isinstance(data,dict) else 'scalar'
                    result['top_level_keys']=sorted(data) if isinstance(data,dict) else []
                    items=data if isinstance(data,list) else next((data[k] for k in ('tasks','files','edits','candidates') if isinstance(data,dict) and isinstance(data.get(k),list)),[])
                    result['output_items']=len(items)
                except ValueError:
                    result['strict_json']=False
            if 'error_receipt' in call:
                read(call['error_receipt']); result['error_receipt']=call['error_receipt']
            calls.append(result)
    if len({c['id'] for c in calls})!=len(calls): raise ValueError('Duplicate call ID')
    summary={}
    for solution in ('glm53','gpt6','opus5'):
        group=[c for c in calls if c['solution']==solution]
        summary[solution]={'calls':len(group),'responses':sum('response_receipt' in c for c in group),
                          'strict_json_responses':sum(c.get('strict_json',False) for c in group),
                          'phases':dict(Counter(c['phase'] for c in group)),
                          'prompt_chars':sum(c['prompt_chars'] for c in group),
                          'response_chars':sum(c.get('response_chars',0) for c in group)}
    result={'capture':'redacted LiteLLM kwargs and ModelResponse, not HTTP wire bytes',
            'receipts_verified':True,'call_count':len(calls),'solutions':summary,'calls':calls}
    dump(run/'transcript-audit.json',result)
    return result


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__); p.add_argument('run',type=Path)
    args=p.parse_args(); result=analyze(args.run)
    print(json.dumps(result['solutions'],indent=2))
