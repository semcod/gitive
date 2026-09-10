import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from gitive.novnc_workspace import activate


class ActivationTests(unittest.TestCase):
    def test_private_install_preserves_source_and_previous_profile(self):
        with tempfile.TemporaryDirectory() as tmp:
            base=Path(tmp);clone='a'*32;store=base/'app-data/workspaces'
            (store/'clones').mkdir(parents=True)
            name='snap/firefox/common/.mozilla/firefox'
            (store/'clones'/f'{clone}.json').write_text(json.dumps({'session_paths':[name]}))
            source=store/('restored-home-'+clone)/name;source.mkdir(parents=True)
            (source/'profiles.ini').write_text('imported')
            desktop=base/'desktop';desktop.mkdir()
            (desktop/'browser-install.json').write_text(json.dumps({'firefox':{'binary':'/private/firefox','version':'155.0.1'}}))
            active=desktop/'home/browser/.mozilla/firefox';active.mkdir(parents=True)
            (active/'profiles.ini').write_text('previous')
            with patch('gitive.isolation.BASE',base),patch('gitive.isolation.audit'),patch('gitive.novnc_workspace.subprocess.check_output',return_value='Firefox 155.0.1'),patch('gitive.novnc_workspace.subprocess.run'):
                receipt=activate(clone,'firefox')
            self.assertEqual((source/'profiles.ini').read_text(),'imported')
            self.assertEqual((active/'profiles.ini').read_text(),'imported')
            self.assertEqual((Path(receipt['backup'])/'previous/.mozilla/firefox/profiles.ini').read_text(),'previous')
            self.assertFalse(receipt['login_verified'])

    def test_invalid_clone_rejected_before_docker(self):
        with tempfile.TemporaryDirectory() as tmp,patch('gitive.isolation.BASE',Path(tmp)),patch('gitive.isolation.audit') as audit:
            with self.assertRaises(ValueError):activate('../escape','firefox')
            audit.assert_not_called()
