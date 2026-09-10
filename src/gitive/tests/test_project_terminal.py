from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from gitive.digitaltwin import DigitalTwin,pc_identity
from gitive.project_terminal import setup_ssh,verify_identity


class TerminalTests(unittest.TestCase):
    def test_identity_uses_pc_owner_not_docker_base_user(self):
        with tempfile.TemporaryDirectory() as source:
            with patch('pathlib.Path.stat',return_value=SimpleNamespace(st_uid=1000,st_gid=1001)),patch('pwd.getpwuid',return_value=SimpleNamespace(pw_name='tom',pw_dir='/home/tom')) as user,patch('grp.getgrgid',return_value=SimpleNamespace(gr_name='tom')) as group:
                result=pc_identity(source)
            self.assertEqual(result['username'],'tom');self.assertEqual(result['home'],'/home/tom')
            self.assertEqual((result['uid'],result['gid']),(1000,1001))
            user.assert_called_once_with(1000);group.assert_called_once_with(1001)

    def test_identity_rejects_root_even_with_home_account_metadata(self):
        with patch('pathlib.Path.stat',return_value=SimpleNamespace(st_uid=0,st_gid=0)),patch('pwd.getpwuid',return_value=SimpleNamespace(pw_name='tom',pw_dir='/home/tom')),patch('grp.getgrgid',return_value=SimpleNamespace(gr_name='tom')):
            with self.assertRaisesRegex(ValueError,'non-root PC project owner'):
                pc_identity('/fixture/project')

    def test_launch_keeps_original_home_and_source_without_pc_mount(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);identity=dict(username='tom',uid=1000,gid=1000,home='/home/tom')
            plan=dict(source='/home/tom/github/org/demo',roots=['/home/tom/github/org/demo','/home/tom/miniconda3'],
                      identity=identity,python=dict(executable='/home/tom/miniconda3/bin/python',base_prefix='/home/tom/miniconda3'),
                      node=None,terminal={'network':'private-network'})
            with patch('gitive.digitaltwin.command') as command:DigitalTwin(root).launch('owned',root,plan,'image')
            argv=command.call_args.args[0]
            self.assertIn('1000:1000',argv);self.assertIn('HOME=/home/tom',argv)
            self.assertNotIn('HOME=/gitive-home',argv)
            mounts=[argv[i+1] for i,a in enumerate(argv) if a=='--mount']
            self.assertTrue(all('src='+str(root) in mount for mount in mounts))
            self.assertIn('type=bind,src='+str(root/'home')+',dst=/home/tom',mounts)
            self.assertEqual(argv[-5:],['/usr/sbin/sshd','-D','-e','-f','/gitive-ssh/sshd_config'])
            self.assertNotIn('docker.sock',str(argv));self.assertNotIn('--privileged',argv)

    def test_session_uses_verified_path_and_disables_password_and_agent_access(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);folder=root/'ssh';folder.mkdir()
            for key in ('host_ed25519','client_ed25519'):
                (folder/key).write_text('fixture-key');(folder/(key+'.pub')).write_text('ssh-ed25519 fixture-public')
            workspace=dict(source="/home/tom/github/a space/demo",python=dict(executable='/home/tom/venv/bin/python',base_prefix='/home/tom/python'),node=None)
            setup_ssh(root,workspace,dict(username='tom',home='/home/tom'))
            config=(folder/'sshd_config').read_text();session=(folder/'session').read_text()
            self.assertIn('PasswordAuthentication no',config);self.assertIn('AllowAgentForwarding no',config)
            self.assertIn('AllowUsers tom',config);self.assertIn("cd -- '/home/tom/github/a space/demo'",session)
            self.assertIn('HOME=/home/tom',session)
            self.assertNotIn('/workspace/github',session)
            self.assertEqual((folder/'client_ed25519').stat().st_mode&0o777,0o600)

    def test_verification_rejects_cosmetic_prompt_with_wrong_real_user(self):
        identity=dict(username='tom',uid=1000,gid=1000,home='/home/tom')
        workspace=dict(source='/home/tom/github/org/demo',python={'executable':'python'})
        with patch('gitive.project_terminal.command',return_value='{"username":"browser","uid":1000,"gid":1000,"home":"/home/tom","pwd":"/home/tom/github/org/demo"}'):
            with self.assertRaisesRegex(RuntimeError,'identity/path'):verify_identity('container',workspace,identity)
