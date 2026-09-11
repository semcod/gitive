import unittest
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock
from gitive.integrations import (
    match_project_for_repo,
    aggregate_tickets,
    get_github_token,
    fetch_github_issues,
    discover_local_tickets,
    is_ticket_busy,
    _normalize_ticket_num
)

class IntegrationsTests(unittest.TestCase):
    def test_match_project_for_repo(self):
        projects = {
            'code2logic': {'source_path': '/source/github/semcod/code2logic'},
            'gitive': {'source_path': '/source/github/semcod/gitive'},
            'doctor-agent': {'source_path': '/source/github/subactor/doctor-agent'}
        }
        self.assertEqual(match_project_for_repo('semcod/code2logic', projects), 'code2logic')
        self.assertEqual(match_project_for_repo('code2logic', projects), 'code2logic')
        self.assertEqual(match_project_for_repo('subactor/doctor-agent', projects), 'doctor-agent')
        self.assertEqual(match_project_for_repo('unknown/repo', projects), 'code2logic')  # fallback to first

    def test_token_retrieval(self):
        token = get_github_token()
        self.assertTrue(token is None or isinstance(token, str))

    def test_aggregate_tickets_empty(self):
        res = aggregate_tickets({}, source='local')
        self.assertIsInstance(res, list)

    def test_normalize_ticket_num(self):
        self.assertEqual(_normalize_ticket_num(15), 15)
        self.assertEqual(_normalize_ticket_num("15"), 15)
        self.assertEqual(_normalize_ticket_num("ticket-015"), 15)
        self.assertEqual(_normalize_ticket_num("ticket-321--fix"), 321)

    @patch('urllib.request.urlopen')
    def test_fetch_github_issues_only_open_and_non_wip(self, mock_urlopen):
        mock_resp = MagicMock()
        mock_resp.__enter__.return_value = mock_resp
        mock_resp.read.return_value = b'''[
            {"number": 1, "title": "Closed Task", "state": "closed", "labels": []},
            {"number": 2, "title": "PR Item", "state": "open", "pull_request": {}, "labels": []},
            {"number": 3, "title": "WIP Task", "state": "open", "labels": [{"name": "in-progress"}]},
            {"number": 4, "title": "Valid Open Task", "state": "open", "labels": [{"name": "bug"}]}
        ]'''
        mock_urlopen.return_value = mock_resp

        issues = fetch_github_issues("example/repo", "fake", state="open")
        self.assertEqual(len(issues), 1)
        self.assertEqual(issues[0]["number"], 4)
        self.assertEqual(issues[0]["status"], "open")

    def test_is_ticket_busy(self):
        busy = {("gitive", 15), 13}
        self.assertTrue(is_ticket_busy("semcod/gitive", 15, busy))
        self.assertTrue(is_ticket_busy("semcod/gitive", "ticket-015", busy))
        self.assertTrue(is_ticket_busy("other/repo", 13, busy))
        self.assertFalse(is_ticket_busy("semcod/gitive", 99, busy))

    def test_local_planfile_ticket_contains_detail_link(self):
        from gitive.planfile_bridge import PlanfileBridge
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            bridge = PlanfileBridge(root)
            bridge.ensure('local-link', 'Planfile task', 'glm53')
            rows = discover_local_tickets({'demo': {'path': str(root)}})
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]['planfile_id'], 'PLF-001')
            self.assertIn('tab=tickets', rows[0]['planfile_url'])
            self.assertIn('project=demo', rows[0]['planfile_url'])
            self.assertIn('ticket=PLF-001', rows[0]['planfile_url'])
