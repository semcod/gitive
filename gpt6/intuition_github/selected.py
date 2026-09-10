"""Explicit existing-Issue execution using the native GPT6 patch/PR state machine.

This local-review transport does not publish CI statuses or request merge.
Author-run tests never count as independent approval.
"""
import re
from .controller import Controller
from .config import path_allowed
from .util import GuardError, canonical, digest, now, integer, text


class SelectedController(Controller):
    def import_issue(self, number, paths, acceptance):
        number = integer(number)
        issue = self.hub.issue(number)
        if 'pull_request' in issue or issue.get('state') != 'open':
            raise GuardError('Select an open Issue, not a PR or closed Issue')
        expected = f'https://github.com/{self.hub.repository}/issues/{number}'
        if issue.get('html_url') != expected:
            raise GuardError('Issue repository identity mismatch')
        if (not paths or len(paths) > self.config['max_files_per_patch']
                or len(set(paths)) != len(paths)
                or any(not path_allowed(p, self.config) for p in paths)):
            raise GuardError('Choose bounded existing allowlisted source files')
        if not isinstance(acceptance, list) or not 1 <= len(acceptance) <= 8:
            raise GuardError('Provide 1–8 concrete acceptance criteria')
        for item in acceptance:
            text(item, 1500)
        key = f'github:{self.hub.repository}#{number}'
        tid = digest(key.encode())[:24]
        old = self.state['tasks'].get(tid)
        if old:
            if old['target_files'] != paths or old['acceptance'] != acceptance:
                raise GuardError('Existing delivery has a different scope; do not overwrite it')
            return old
        # Refuse a competing PR, including one left by another controller.
        pattern = re.compile(r'\b(?:close[sd]?|fix(?:e[sd])?|resolve[sd]?)\s+(?:'
                             + re.escape(self.hub.repository) + r')?#' + str(number) + r'\b', re.I)
        for pr in self.hub.pulls(state='all'):
            if pattern.search(pr.get('body') or '') and (pr['state'] == 'open' or pr.get('merged_at') or pr.get('merged')):
                raise GuardError('Issue already has an open/merged PR: ' + str(pr['number']))
        self.hub.files(self.base, paths, self.config['max_file_bytes'])
        title = self.redactor.public_text(issue['title'])[:160]
        body = self.redactor.clean(issue.get('body') or '')
        fact = {'id': key, 'kind': 'github_issue', 'status': 'observed',
                'text': (title + '\n' + body)[:8000], 'source': expected, 'observed_at': now()}
        task = {'id': tid, 'key': key, 'base_sha': self.base, 'score': 1.0,
                'title': title, 'profile': 'repair', 'target_files': paths,
                'acceptance': acceptance, 'rationale': 'Explicitly selected existing GitHub Issue',
                'fact_ids': [key], 'evidence': [fact], 'created_at': now(),
                'status': 'ready', 'attempts': [], 'issue_number': number, 'pr_number': None,
                'prepared': None, 'generation_failures': 0,
                'issue_version': digest(canonical([issue['title'], issue.get('body') or ''])),
                'transport': 'gitive-local-review'}
        self.state['tasks'][tid] = task
        self.memory.save('existing_issue_imported', {'task': tid, 'issue': number})
        return task

    def mark_human(self, task, reason):
        task.update(status='needs_human', human_reason=reason)
        self.memory.save('selected_task_needs_human', {'id': task['id'], 'reason': reason})

    def dispatch(self, task):
        # Native publish_prepared has persisted branch, PR and exact attempt SHA.
        task['status'] = 'awaiting_local_tests'
        self.memory.save('local_test_pending', {'task': task['id']})

    def cycle_issue(self, tid, verifier):
        task = self.state['tasks'].get(tid)
        if not task or task.get('transport') != 'gitive-local-review':
            raise GuardError('Unknown imported delivery task')
        issue = self.hub.issue(task['issue_number'])
        if task['pr_number']:
            pr = self.hub.pull(task['pr_number'])
            if pr.get('merged'):
                task['status'] = 'completed'
                self.memory.save('remote_merge_observed', {'task': tid, 'merge': pr.get('merge_commit_sha')})
                return task
            if pr['state'] != 'open':
                task['status'] = 'abandoned'
                self.memory.save('remote_pr_closed', {'task': tid})
                return task
            if pr['head']['sha'] != task['attempts'][-1]['head_sha']:
                self.mark_human(task, 'PR head changed outside this delivery')
                return task
        if issue['state'] != 'open':
            task['status'] = 'abandoned'
            self.memory.save('remote_issue_closed', {'task': tid})
            return task
        if digest(canonical([issue['title'], issue.get('body') or ''])) != task['issue_version']:
            self.mark_human(task, 'Issue changed; inspect acceptance criteria before continuing')
            return task
        if task['status'] in ('needs_human', 'no_change', 'abandoned', 'completed'):
            return task
        if self.state['paused_reason']:
            return task
        if task['status'] == 'awaiting_review':
            receipt = task.get('local_verification', {})
            if receipt.get('base_sha') == self.base:
                return task
            task['status'] = 'awaiting_local_tests'
        if task['status'] == 'ready' or task.get('prepared'):
            if not task['pr_number'] and len([p for p in self.hub.pulls()
                    if p['head']['ref'].startswith('intuition/')]) >= self.config['max_open_prs']:
                raise GuardError('Open PR limit reached')
            self.generate_patch(task)
        if task['status'] == 'awaiting_local_tests':
            attempt = task['attempts'][-1]
            result = verifier(task['pr_number'], attempt['head_sha'], self.base)
            # A passing test of an old candidate/base must never advance the state.
            current = self.hub.pull(task['pr_number'])
            if (current['state'] != 'open' or current['head']['sha'] != attempt['head_sha']
                    or current['base']['ref'] != self.default or self.hub.ref(self.default) != self.base
                    or result.get('head_sha') != attempt['head_sha'] or result.get('base_sha') != self.base):
                raise GuardError('Candidate/base changed during verification; retry against current identity')
            task['local_verification'] = result
            if result.get('status') == 'passed':
                task['status'] = 'awaiting_review'
                attempt['outcome'] = 'local_pass'
            elif result.get('status') == 'failed':
                attempt['outcome'] = 'local_fail'
                task['status'] = 'ready'
                task['evidence'].append({'id': 'local-test:' + attempt['head_sha'],
                    'text': self.redactor.clean(result.get('output', ''))[-8000:],
                    'source': 'local Docker test', 'observed_at': now()})
                if len(task['attempts']) >= self.config['max_attempts_per_issue']:
                    self.mark_human(task, 'Candidate tests failed; attempt limit reached')
            # Infrastructure/conflict remains pending, not a model failure.
            self.memory.save('local_verification_recorded', {'task': tid, 'status': result.get('status')})
        return task
