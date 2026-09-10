import json
import subprocess
import sys
from unittest.mock import patch

from intuition.config import Config
from intuition.llm import complete_json_list, LLMError
from intuition.repair import repair


def test_parser_strings_and_invalid_responses():
    for raw in ['[{"title":"literal ] and ["}]', '```json\n[{"title":"a \\\"quote\\\""}]\n```',
                'Here is JSON: [{"title":"[check]"}]']:
        with patch('intuition.llm.complete', return_value=raw):
            assert len(complete_json_list('', '')) == 1
    for raw in ['[{"title":"broken"}', '[{}, 1]', '{"tasks":[{}, null]}']:
        with patch('intuition.llm.complete', return_value=raw):
            try:
                complete_json_list('', '')
            except LLMError:
                pass
            else:
                raise AssertionError('invalid response accepted')


def test_repair_accept_reject_resume(tmp_path):
    def git(*args):
        return subprocess.run(['git', *args], cwd=tmp_path, check=True, capture_output=True)
    git('init', '-b', 'main')
    git('config', 'user.name', 'Test')
    git('config', 'user.email', 'test@example.invalid')
    (tmp_path / 'src').mkdir()
    (tmp_path / 'src/core.py').write_text('def add(a, b): return a - b\n')
    (tmp_path / 'check.py').write_text('from src.core import add\nassert add(2, 3) == 5\nassert add(2, 0) == 2\n')
    git('add', '.')
    git('commit', '-m', 'fixture')
    task = {'id': 't1', 'title': 'Fix addition', 'files': ['src/core.py'], 'phi': [1., 0., -.1, 0.]}
    cfg = Config()
    def bad(*args, **kw):
        return [{'path': 'src/core.py', 'content': 'def add(a, b): return 5\n'}]
    def good(*args, **kw):
        return [{'path': 'src/core.py', 'content': 'def add(a, b): return a + b\n'}]
    result = repair(cfg, tmp_path, task, [sys.executable, 'check.py'], bad)
    assert result['status'] == 'rejected'
    assert 'a - b' in (tmp_path / 'src/core.py').read_text()
    result = repair(cfg, tmp_path, task, [sys.executable, 'check.py'], good)
    assert result['status'] == 'accepted'
    result = repair(cfg, tmp_path, task, [sys.executable, 'check.py'], bad)
    assert result['status'] == 'already-green'
    assert len(list((tmp_path / '.intuition-repair').glob('*.json'))) == 3
    assert git('status', '--porcelain').stdout == b''


def test_transport_limits_and_incomplete_response():
    from types import SimpleNamespace
    from unittest.mock import Mock
    from intuition.llm import complete
    for reason, content, error in [('length', '[]', 'incomplete_response'), ('stop', '', 'empty_response')]:
        call = Mock(return_value={'choices': [{'finish_reason': reason, 'message': {'content': content}}],
                                  'usage': {'total_tokens': 17}})
        with patch.dict('sys.modules', {'litellm': SimpleNamespace(completion=call)}):
            try:
                complete('', '', model='test-model')
            except LLMError as exc:
                assert str(exc) == error
            else:
                raise AssertionError('invalid completion accepted')
        assert complete.last_usage['tokens'] == 17
        assert call.call_args.kwargs['num_retries'] == 0
        assert call.call_args.kwargs['timeout'] > 0
    call = Mock(side_effect=TimeoutError('secret-provider-body'))
    with patch.dict('sys.modules', {'litellm': SimpleNamespace(completion=call)}):
        try:
            complete('', '', model='test-model')
        except LLMError as exc:
            assert str(exc) == 'transport:TimeoutError'
        else:
            raise AssertionError('timeout accepted')
    assert complete.last_usage['tokens'] is None
