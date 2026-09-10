"""Private, redacted SDK request/response records with public content receipts."""
from __future__ import annotations
import hashlib
import json
import os
from pathlib import Path
import re
import tempfile

REQUEST_FIELDS = {'model', 'messages', 'temperature', 'max_tokens', 'max_completion_tokens',
                  'reasoning_effort', 'response_format', 'timeout', 'num_retries', 'seed',
                  'extra_body', 'top_p', 'stop', 'stream', 'tools', 'tool_choice', 'api_base', 'base_url'}
OMIT = {'api_key', 'authorization', 'access_token', 'refresh_token', 'password',
        'headers', 'extra_headers', 'response_headers', 'request_headers', '_hidden_params'}


class Recorder:
    def __init__(self, directory, reference_root):
        self.directory = Path(directory)
        self.reference_root = Path(reference_root)
        self.directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.directory.chmod(0o700)
        self.secrets = [v for k, v in os.environ.items() if len(v) >= 6 and
                        any(x in k.upper() for x in ('API_KEY', 'TOKEN', 'PASSWORD', 'SECRET'))]

    def scrub(self, value):
        if isinstance(value, dict):
            return {self.scrub(str(k)): self.scrub(v) for k, v in value.items() if str(k).lower() not in OMIT}
        if isinstance(value, (tuple, list)):
            return [self.scrub(v) for v in value]
        if isinstance(value, str):
            for secret in sorted(self.secrets, key=len, reverse=True):
                value = value.replace(secret, '[REDACTED]')
            return re.sub(r'\b(?:sk-or-v1-|sk-proj-|gh[pousr]_|github_pat_)[A-Za-z0-9_-]+', '[REDACTED]', value)
        if value is None or isinstance(value, (bool, int, float)):
            return value
        raise TypeError('Transcript contains unsupported value type')

    def write(self, call_id, kind, payload):
        path = self.directory / f'{call_id}.{kind}.json'
        if path.exists():
            raise ValueError('Transcript already exists')
        data = (json.dumps(self.scrub(payload), ensure_ascii=False, indent=2, allow_nan=False) + '\n').encode()
        fd, temporary = tempfile.mkstemp(dir=self.directory, prefix='.record-')
        try:
            with os.fdopen(fd, 'wb') as stream:
                stream.write(data)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, path)
        finally:
            Path(temporary).unlink(missing_ok=True)
        return {'path': os.path.relpath(path, self.reference_root),
                'sha256': hashlib.sha256(data).hexdigest(), 'bytes': len(data)}

    def request(self, call_id, kwargs, metadata):
        return self.write(call_id, 'request', {'metadata': metadata,
                    'request': {k: v for k, v in kwargs.items() if k in REQUEST_FIELDS},
                    'capture_level': 'LiteLLM completion kwargs; credentials and headers excluded'})

    def response(self, call_id, response):
        # ModelResponse.model_dump includes all choices, reasoning fields and usage.
        payload = response.model_dump(mode='json') if hasattr(response, 'model_dump') else response
        return self.write(call_id, 'response', {'response': payload,
                    'capture_level': 'LiteLLM ModelResponse; not raw HTTP bytes'})


def phase(kwargs):
    messages = kwargs.get('messages') or []
    for message in messages:
        if message.get('role') == 'user':
            try:
                purpose = json.loads(message.get('content', '')).get('purpose')
                if isinstance(purpose, str):
                    return purpose
            except (ValueError, AttributeError, TypeError):
                pass
    return 'execute' if kwargs.get('temperature') == .2 else 'propose_or_goal'
