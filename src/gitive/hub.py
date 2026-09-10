"""Use the existing account-hub execution boundary, never docker exec or credentials copies."""
import json
import os
from pathlib import Path
import urllib.request
import urllib.error
import uuid

class Hub:
    def __init__(self):
        self.url = os.getenv('HUB_URL', 'http://10.240.0.1:8088').rstrip('/')
    def call(self, path, body=None):
        token = Path(os.environ['HUB_TOKEN_FILE']).read_text().strip()
        req = urllib.request.Request(self.url+path,
            data=None if body is None else json.dumps(body).encode(),
            headers={'Authorization':'Bearer '+token,'Content-Type':'application/json'})
        try:
            with urllib.request.urlopen(req,timeout=660) as response:
                return json.load(response)
        except urllib.error.HTTPError as exc:
            raise RuntimeError(f'Hub HTTP {exc.code}; sprawdź konfigurację i uprawnienia Control') from None
    def plan(self, prompt):
        request = dict(account_id=os.getenv('HUB_ACCOUNT','softreck'), provider='chatgpt',tool_id='codex',
            dsl={'schema':'llmhub.scoped-cli-dsl/v1','operation':'task','project':'semcod/gitive',
                 'prompt':prompt,'timeout_seconds':300})
        plan = self.call('/v1/cli/executions/plan', request)
        for field in ('execution_id','valid_until','plan_hash'):
            request[field] = plan[field]
        return request, plan
    def execute(self, request, plan):
        # Authority remains enforced by Hub; each plan gets one consumed grant and intent.
        grant_id, intent_id = str(uuid.uuid4()), str(uuid.uuid4())
        ticket = 'gitive-loop-'+request['execution_id']
        self.call('/v1/grants/issue', {**plan['authorization']['issue_grant'],
            'grant_id':grant_id,'command_id':'grant-'+grant_id,'ticket':ticket})
        self.call('/v1/intents/start', {**plan['authorization']['start_intent'],
            'grant_id':grant_id,'intent_id':intent_id,'command_id':'intent-'+intent_id,'ticket':ticket})
        return self.call('/v1/cli/executions/apply', {**request,'grant_id':grant_id,'intent_id':intent_id,'ticket':ticket})
