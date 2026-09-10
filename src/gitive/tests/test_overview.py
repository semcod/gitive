import unittest
from gitive.overview import overview

class OverviewTests(unittest.TestCase):
    def test_snapshot_without_browser_is_not_ready_clone(self):
        snapshot={'id':'test','project':'org/repo','sessions':[]}
        result=overview({'status':'idle'},{'status':'complete','operation':'snapshot','result':snapshot},{'snapshots':[snapshot]}, {})
        self.assertEqual(result['counts']['clones'],0)
        self.assertIn('brak — nie skopiowano przeglądarki','\n'.join(result['lines']))
        self.assertFalse(any('resync' in a['argv'] for a in result['actions']))
    def test_busy_workspace_offers_only_read_actions(self):
        result=overview({'status':'idle'},{'status':'running'},{'clones':[{'id':'a','source':'s','target':'t'}]}, {})
        self.assertTrue(result['busy'])
        self.assertFalse(any('resync' in a['argv'] or 'clone' in a['argv'] for a in result['actions']))
    def test_ready_clone_offers_preview_and_block_reason(self):
        result=overview({'status':'blocked','error':'Brak wdrożenia API'},{'status':'complete'},{'clones':[{'id':'a','source':'s','target':'t'}]}, {})
        action=next(a for a in result['actions'] if 'resync' in a['argv'])
        self.assertNotIn('--apply',action['argv'])
        self.assertIn('Brak wdrożenia API','\n'.join(result['lines']))
