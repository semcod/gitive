import tempfile
import unittest
from types import SimpleNamespace
from gitive.planfile_bridge import PlanfileBridge, ENGINES

class Backend:
    def __init__(self):self.rows={};self.creates=0
    def create_ticket(self,payload):
        if not self.rows:
            self.creates+=1
            self.rows['1']=SimpleNamespace(id='1',name=payload['name'],description=payload['description'],status='open',url='https://github.com/example/repo/issues/1')
        return SimpleNamespace(id='1')
    def get_ticket(self,key):return self.rows[key]
    def update_ticket(self,key,**fields):
        row=self.rows[key]
        for key,value in fields.items():setattr(row,'description' if key=='body' else key,value)

class PlanfileBridgeTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.backend=Backend();self.bridge=PlanfileBridge(self.tmp.name,'example/repo',self.backend)
    def test_all_engines_use_native_project_store(self):
        for engine in ENGINES:
            t=self.bridge.ensure(engine,'Task '+engine,engine)
            self.assertEqual(self.bridge.ensure(engine,'Task '+engine,engine).id,t.id)
            self.assertEqual(t.executor.handler,engine)
            self.bridge.outcome(t.id,'repaired')
            self.assertEqual(self.bridge.store.get_ticket(t.id).status.value,'in_progress')
    def test_push_retry_pull_and_done_mapping(self):
        t=self.bridge.ensure('case','Test sync','glm53')
        self.bridge.sync(t.id);self.bridge.sync(t.id)
        self.assertEqual(self.backend.creates,1)
        self.backend.rows['1'].status='closed'
        self.bridge.sync(t.id,'pull')
        self.assertEqual(self.bridge.store.get_ticket(t.id).status.value,'done')
        self.bridge.sync(t.id,'push')
        self.assertEqual(self.backend.rows['1'].status,'closed')
    def test_conflicts_do_not_overwrite_either_side(self):
        t=self.bridge.ensure('case','Test sync','gpt6');self.bridge.sync(t.id)
        self.backend.rows['1'].name='Remote update'
        with self.assertRaises(RuntimeError):self.bridge.sync(t.id,'push')
        self.bridge.store.update_ticket(t.id,name='Local update')
        with self.assertRaises(RuntimeError):self.bridge.sync(t.id,'pull')
        self.assertEqual(self.backend.rows['1'].name,'Remote update')
        self.assertEqual(self.bridge.store.get_ticket(t.id).name,'Local update')
    def test_different_repository_is_rejected(self):
        t=self.bridge.ensure('case','Test sync','opus5');self.bridge.sync(t.id)
        self.bridge.repository='example/other'
        with self.assertRaises(ValueError):self.bridge.sync(t.id)
