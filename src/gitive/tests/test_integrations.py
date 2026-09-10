import unittest
from unittest.mock import patch, MagicMock
from gitive.integrations import match_project_for_repo, aggregate_tickets, get_github_token

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
