import sys
import tempfile
import threading
import time
import unittest
from gitive.engine import Engine

class ProcessTests(unittest.TestCase):
    def test_stop_terminates_child_and_records_exit(self):
        with tempfile.TemporaryDirectory() as tmp:
            engine=Engine(tmp,tmp);engine.state={'run':'test','status':'running','stop':False}
            errors=[]
            def run():
                try:engine.command([sys.executable,'-c','import time; time.sleep(30)'],'test-worker',60)
                except RuntimeError as exc:errors.append(str(exc))
            thread=threading.Thread(target=run);thread.start()
            deadline=time.monotonic()+5
            while not engine.state.get('process') and time.monotonic()<deadline:time.sleep(.01)
            engine.stop();thread.join(7)
            self.assertFalse(thread.is_alive())
            self.assertTrue(errors);self.assertEqual(engine.state['process']['status'],'finished')
            self.assertIsNotNone(engine.state['process']['returncode'])
