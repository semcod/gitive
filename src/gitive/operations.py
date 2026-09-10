"""Allowlisted operation telemetry. Never record arguments, source, prompts or tokens."""
from contextlib import contextmanager
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import sys
import uuid


class Operations:
    def __init__(self, destination, project, ticket, solution, run, root):
        self.folder = Path(destination)
        self.folder.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.identity = dict(project=project, ticket=ticket, solution=solution, run=run, pid=os.getpid())
        self.stack = []
        self.sequence = 0
        # Exact source paths avoid confusing the two packages named intuition.
        prefixes = {'glm53': 'glm53/intuition', 'gpt6': 'gpt6/intuition_github', 'opus5': 'opus5/src/intuition'}
        self.native = str(Path(root).resolve() / prefixes[solution]) + '/'
        self.common = str(Path(root).resolve() / 'benchmark/common.py')
        self.frames = {}

    def emit(self, operation, function, status='running'):
        self.sequence += 1
        row = dict(self.identity, sequence=self.sequence, at=datetime.now(timezone.utc).isoformat(),
                   operation=operation, function=function, status=status)
        with (self.folder/'operations.jsonl').open('a', encoding='utf-8') as stream:
            os.chmod(stream.name, 0o600)
            stream.write(json.dumps(row, ensure_ascii=False)+'\n')
        temp = self.folder/('operation.'+uuid.uuid4().hex+'.tmp')
        temp.write_text(json.dumps(row), encoding='utf-8')
        temp.chmod(0o600)
        temp.replace(self.folder/'operation.json')

    @contextmanager
    def stage(self, operation, function):
        token = object()
        self.stack.append((token, operation, function))
        self.emit(operation, function)
        try:
            yield
        finally:
            self.pop(token)

    def pop(self, token):
        self.stack = [entry for entry in self.stack if entry[0] is not token]
        if self.stack:
            _, operation, function = self.stack[-1]
            self.emit(operation, function)
        else:
            self.emit('idle', 'gitive.develop', 'idle')

    def classify(self, frame):
        filename, name = frame.f_code.co_filename, frame.f_code.co_name
        native = filename.startswith(self.native)
        if not native and filename != self.common:
            return None
        function = (self.identity['solution']+'.'+Path(filename).stem if native else 'benchmark.common')+'.'+name
        if name == 'git':
            args = frame.f_locals.get('args', ())
            command = args[0] if args else ''
            operation = {'commit': 'commit', 'merge': 'merge', 'fetch': 'fetch', 'clone': 'clone',
                         'log': 'log-reading', 'show': 'log-reading', 'diff': 'log-reading'}.get(command)
            return (operation, function) if operation else None
        if not native:
            return None
        if name == 'complete' and self.identity['solution'] == 'gpt6':
            return ('coding' if frame.f_locals.get('purpose') == 'propose_patch' else 'planning', function)
        if Path(filename).stem == 'llm' and name in ('__call__', 'complete_json_list'):
            # Low-temperature execution call; never infer its meaning from generated text.
            if frame.f_locals.get('temperature') == .2 or frame.f_locals.get('kw', {}).get('temperature') == .2:
                return ('coding', function)
        operation = {'propose': 'planning', 'choose': 'planning', 'cycle': 'planning',
                     'score': 'scoring', 'validate_tasks': 'scoring', 'ingest': 'log-reading',
                     'validate_patch': 'validation', 'validate_edits': 'validation',
                     'validate_python_api': 'validation', 'repair': 'repair', '_repair': 'repair',
                     'test': 'tests', 'run_tests': 'tests', 'persist': 'learning',
                     'feedback': 'learning'}.get(name)
        return (operation, function) if operation else None

    def profile(self, frame, event, arg):
        if event == 'call':
            value = self.classify(frame)
            if value:
                token = object()
                self.frames[id(frame)] = token
                self.stack.append((token, *value))
                self.emit(*value)
        elif event == 'return':
            token = self.frames.pop(id(frame), None)
            if token is not None:
                self.pop(token)

    @contextmanager
    def observe(self):
        previous = sys.getprofile()
        sys.setprofile(self.profile)
        try:
            yield self
        finally:
            sys.setprofile(previous)
            self.frames.clear()
            self.stack.clear()
            self.emit('idle', 'gitive.develop', 'finished')


def current(data, state, project, ticket):
    """Only report a live operation when run, project, ticket and worker PID all match."""
    empty = dict(operation='idle', project=project, ticket=ticket, events=[])
    if state.get('project') != project or state.get('ticket_id') != ticket:
        return empty
    run, cycle = state.get('run', ''), state.get('cycle')
    if not re.fullmatch(r'[0-9]{8}T[0-9]{6}Z-[a-f0-9]{6}', run) or type(cycle) is not int or cycle < 1:
        return dict(empty, operation='unknown' if state.get('status') == 'running' else 'idle')
    folder = Path(data)/run/f'develop-{cycle}'
    process = state.get('process') or {}
    bound = dict(project=project, ticket=ticket, run=run, solution=(state.get('selection') or {}).get('solution'))
    def matches(row):
        return isinstance(row, dict) and all(row.get(k) == v for k, v in bound.items()) and row.get('pid') == process.get('pid')
    try:
        row = json.loads((folder/'operation.json').read_text())
        with (folder/'operations.jsonl').open('rb') as stream:
            stream.seek(max(0, (folder/'operations.jsonl').stat().st_size-32000))
            lines = stream.read().splitlines()
        events = []
        for line in lines:
            try:
                event = json.loads(line)
                if matches(event): events.append(event)
            except (ValueError, TypeError): pass
        empty['events'] = events[-20:]
    except (OSError, ValueError):
        row = {}
    if state.get('status') not in ('running', 'stopping') or process.get('status') != 'running':
        return dict(empty, execution_status=state.get('status'), operation='interrupted' if state.get('status') == 'interrupted' else 'idle')
    try:
        pid = process['pid']
        if type(pid) is not int or pid <= 0: raise ValueError('pid')
        os.kill(pid, 0)
    except (OSError, KeyError, ValueError):
        return dict(empty, operation='unknown')
    if not matches(row): return dict(empty, operation='unknown')
    return dict(row, events=empty['events'])
