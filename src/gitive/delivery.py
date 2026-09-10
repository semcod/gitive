"""Host CLI bridge: Planfile → native GPT6 → draft PR → isolated local tests.

The protected independent publisher remains responsible for approval/merge.
"""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tarfile
import tempfile
import uuid
from filelock import FileLock

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'gpt6'))
from intuition_github.config import load_config
from intuition_github.github import GitHub
from intuition_github.llm import LiteLLMClient, load_env
from intuition_github.memory import Memory
from intuition_github.selected import SelectedController
from intuition_github.util import GuardError, canonical, digest


def command(args, cwd=None, timeout=180):
    p = subprocess.run(args, cwd=cwd, capture_output=True, timeout=timeout)
    if p.returncode:
        raise RuntimeError(f'{args[0]} failed (exit {p.returncode})')
    return p.stdout.decode().strip()


class ReviewHub(GitHub):
    def create_pull(self, branch, base, title, body):
        body = body.split('Kod wygenerowany przez LLM.')[0] + (
            'Gitive / native GPT6. Draft candidate; local tests are author evidence only. '
            'Independent review and publication remain required.\n')
        url = self.command(['pr', 'create', '--repo', self.repository, '--head', branch,
                            '--base', base, '--title', title, '--body-file', '-', '--draft'], body.encode()).strip()
        prefix = f'https://github.com/{self.repository}/pull/'
        if not url.startswith(prefix) or not url.removeprefix(prefix).isdigit():
            raise GuardError('Unrecognized PR response; retry will reconcile by branch')
        return self.pull(int(url.removeprefix(prefix)))


class DockerVerifier:
    def __init__(self, hub, image, argv, folder):
        self.hub, self.image, self.argv, self.folder = hub, image, argv, Path(folder)
        self.profile = digest(canonical({'image': image, 'argv': argv, 'network': 'none', 'version': 1}))

    def __call__(self, pr, head, base):
        identity = {'repository': self.hub.repository, 'pr': pr, 'head_sha': head,
                    'base_sha': base, 'test_profile_digest': self.profile, 'image': self.image}
        with tempfile.TemporaryDirectory(prefix='gitive-verify-') as temp:
            temp = Path(temp); gitdir = temp / 'repo.git'; source = temp / 'source'
            self.hub.command(['repo', 'clone', self.hub.repository, str(gitdir), '--', '--bare', '--quiet'])
            # Fetch the exact candidate after clone, including commits from a recently updated PR.
            command(['git', '--git-dir', str(gitdir), 'fetch', '--quiet', 'origin', head, base])
            result = subprocess.run(['git', '--git-dir', str(gitdir), 'merge-tree', '--write-tree', base, head],
                                    capture_output=True, text=True, timeout=60)
            if result.returncode:
                return {**identity, 'status': 'conflict', 'output': 'Candidate conflicts with current base'}
            tree = result.stdout.splitlines()[0]
            identity['merge_tree'] = tree
            archive = temp / 'source.tar'
            with archive.open('wb') as stream:
                subprocess.run(['git', '--git-dir', str(gitdir), 'archive', tree], stdout=stream, check=True, timeout=60)
            if archive.stat().st_size > 100_000_000:
                raise GuardError('Test source archive exceeds 100 MB')
            source.mkdir()
            with tarfile.open(archive) as tar:
                if any(not (m.isfile() or m.isdir()) for m in tar.getmembers()):
                    raise GuardError('Local verifier requires ordinary files/directories, without links/devices')
                tar.extractall(source, filter='data')
            # temp is 0700, mounted source is a separate readable tree, never host HOME/.git/.env.
            for path in source.rglob('*'):
                path.chmod(0o755 if path.is_dir() else 0o644)
            source.chmod(0o755)
            name = 'gitive-verify-' + uuid.uuid4().hex[:12]
            bootstrap = "import shutil,os,sys,json; shutil.copytree('/input','/work/repo'); os.chdir('/work/repo'); a=json.loads(sys.argv[1]); os.execvp(a[0],a)"
            argv = ['docker', 'run', '--name', name, '--rm', '--network=none', '--read-only',
                    '--cap-drop=ALL', '--security-opt=no-new-privileges', '--pids-limit=128',
                    '--memory=1g', '--cpus=1', '--user=65534:65534', '--tmpfs=/tmp:rw,nosuid,size=128m,mode=1777',
                    '--tmpfs=/work:rw,nosuid,size=256m,mode=1777',
                    '--mount', f'type=bind,src={source},dst=/input,readonly',
                    '--entrypoint=/usr/bin/env', self.image, '-i', 'PATH=/usr/local/bin:/usr/bin:/bin',
                    'HOME=/tmp', 'LANG=C.UTF-8', 'PYTHONDONTWRITEBYTECODE=1', 'PYTEST_DISABLE_PLUGIN_AUTOLOAD=1',
                    'LITELLM_LOCAL_MODEL_COST_MAP=True', 'python3', '-c', bootstrap, json.dumps(self.argv)]
            try:
                with tempfile.TemporaryFile() as output:
                    try:
                        p = subprocess.run(argv, stdout=output, stderr=subprocess.STDOUT, timeout=180)
                        code = p.returncode
                    except subprocess.TimeoutExpired:
                        code = 124
                    output.seek(max(0, output.tell() - 64000)); text = output.read().decode(errors='replace')
            finally:
                subprocess.run(['docker', 'rm', '-f', name], capture_output=True, timeout=30)
            status = 'passed' if code == 0 else 'infrastructure_error' if code in (124, 125, 126, 127) else 'failed'
            return {**identity, 'status': status, 'exit_code': code, 'output': text}


def llm_factory(config, folder):
    sys.path.insert(0, str(ROOT))
    from benchmark.transcripts import Recorder
    recorder = Recorder(Path(folder)/'transcripts', folder)
    def complete(**kwargs):
        import litellm
        call = uuid.uuid4().hex
        recorder.request(call, kwargs, {'transport': 'native-gpt6-delivery'})
        try:
            response = litellm.completion(**kwargs)
            recorder.response(call, response)
            return response
        except Exception as exc:
            recorder.write(call, 'error', {'error_type': type(exc).__name__})
            raise
    return lambda: LiteLLMClient(config, completion=complete)


def config_for(paths):
    config = load_config(ROOT / 'gpt6/.intuition/config.json')
    config.update(allowed_paths=paths, memory_branch='intuition-memory-gitive-delivery')
    return config


def summarize(task, ticket, repository):
    return {'ticket': ticket, 'issue': f'https://github.com/{repository}/issues/{task["issue_number"]}',
            'task': task['id'], 'status': task['status'],
            'pr': f'https://github.com/{repository}/pull/{task["pr_number"]}' if task['pr_number'] else None,
            'attempts': len(task['attempts']), 'tests': (task.get('local_verification') or {}).get('status'),
            'detail': task.get('human_reason'), 'merge_requested': False}


def run_cli(args):
    from .cli import ticket_bridge
    from .planfile_bridge import local_version
    # Load shared PC .env, including when running from a delivery worktree.
    primary = command(['git', 'rev-parse', '--path-format=absolute', '--git-common-dir'], ROOT)
    load_env(Path(primary).parent / '.env')
    bridge = ticket_bridge(args.project, getattr(args, 'repo', None))
    folder = bridge.root / '.planfile/gitive-delivery'
    folder.mkdir(mode=0o700, parents=True, exist_ok=True)
    with FileLock(str(folder/'delivery.lock'), timeout=1):
        if args.delivery_action == 'import':
            hub = ReviewHub(args.repo)
            # Confirm a usable immutable local runtime before any remote write.
            image = command(['docker', 'image', 'inspect', '--format', '{{.Id}}', args.image])
            if not image.startswith('sha256:'):
                raise GuardError('Select a locally available Docker image')
            test = json.loads(args.test)
            if not isinstance(test, list) or not test or any(not isinstance(x,str) or not x for x in test):
                raise GuardError('Test must be a nonempty JSON argv list')
            config = config_for(args.file)
            memory = Memory(hub, config)
            control = SelectedController(hub, memory, config)
            tid = digest(f'github:{args.repo}#{args.issue}'.encode())[:24]
            spec_path = folder / (tid+'.json')
            spec = {'repository': args.repo, 'issue': args.issue, 'paths': args.file,
                    'acceptance': args.accept, 'image': image, 'test': test, 'task': tid}
            if spec_path.exists():
                old = json.loads(spec_path.read_text())
                if any(old[k] != v for k,v in spec.items()):
                    raise GuardError('Existing delivery profile differs; retained without overwrite')
            task = control.import_issue(args.issue, args.file, args.accept)
            # Canonical remote identity, no new Issue and no gh auth token extraction.
            ticket = bridge.ensure('github:'+args.repo+'#'+str(args.issue), task['title'], 'gpt6', task['evidence'][0]['text'])
            with bridge.lock:
                ticket = bridge.store.get_ticket(ticket.id)
                current = ticket.sync.get('github', {})
                if current and (current.get('repository'), str(current.get('id'))) != (args.repo, str(args.issue)):
                    raise GuardError('Planfile ticket already belongs to a different Issue')
                bridge.store.update_ticket(ticket.id, sync={**ticket.sync, 'github': {
                    'repository': args.repo, 'id': str(args.issue), 'url': task['evidence'][0]['source'],
                    'local_version': local_version(ticket), 'remote_version': None, 'status': 'open', 'is_external': True}})
                src = ticket.source.model_copy(deep=True);src.context['delivery'] = spec
                bridge.store.update_ticket(ticket.id, source=src)
            spec['ticket'] = ticket.id
            temporary = spec_path.with_suffix('.tmp');temporary.write_text(json.dumps(spec, indent=2));temporary.replace(spec_path)
        else:
            ticket = bridge.store.get_ticket(args.ticket)
            if not ticket or not ticket.source or not ticket.source.context.get('delivery'):
                raise GuardError('First use delivery import for this ticket')
            spec = ticket.source.context['delivery'];hub = ReviewHub(spec['repository'])
            config = config_for(spec['paths']);memory = Memory(hub, config)
            task = memory.state['tasks'].get(spec['task'])
            if not task:
                raise GuardError('Remote delivery memory is missing; do not silently restart')
            if args.delivery_action == 'run':
                if not args.apply:
                    raise GuardError('Remote edits require delivery run --apply')
                run = uuid.uuid4().hex; logs = folder / run; logs.mkdir(mode=0o700)
                bridge.execution(ticket.id, 'running', run)
                try:
                    for _ in range(args.cycles):
                        memory = Memory(hub, config)
                        control = SelectedController(hub, memory, config, llm_factory(config, logs))
                        task = control.cycle_issue(spec['task'], DockerVerifier(hub, spec['image'], spec['test'], logs))
                        (logs/'result.json').write_text(json.dumps(task, ensure_ascii=False, indent=2))
                        if task['status'] not in ('ready',):break
                    bridge.execution(ticket.id, 'complete', run, str(logs/'result.json'))
                except Exception as exc:
                    bridge.execution(ticket.id, 'failed', run, error=type(exc).__name__)
                    raise
                # No GitHub push of Planfile status: remote merge/closure is observed, not fabricated.
                mapped={'awaiting_review':'review', 'completed':'done', 'abandoned':'canceled',
                        'needs_human':'blocked', 'ready':'in_progress', 'awaiting_local_tests':'in_progress', 'no_change':'blocked'}
                current=bridge.store.get_ticket(ticket.id)
                if current.status.value not in ('done','canceled'):
                    bridge.store.update_ticket(ticket.id,status=mapped.get(task['status'],'in_progress'),actor='gitive.delivery',reason='Native GPT6: '+task['status'])
        value = summarize(task, ticket.id, hub.repository)
        if getattr(args,'json',False):print(json.dumps(value, ensure_ascii=False, indent=2))
        else:
            for key in ('ticket','status','issue','pr','attempts','tests','detail'):
                if value.get(key) is not None:print(f'{key}: {value[key]}')
        return value
