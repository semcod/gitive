"""Contract fixtures and invalid lifecycle declarations; no Docker/Git side effects."""
import copy
import json
from pathlib import Path
import unittest
from jsonschema import Draft202012Validator, ValidationError

ROOT=Path(__file__).resolve().parents[1]
def load(path):return json.loads((ROOT/path).read_text())

class ContractTests(unittest.TestCase):
    def validator(self,name):
        schema=load('contracts/'+name+'.schema.json')
        Draft202012Validator.check_schema(schema)
        return Draft202012Validator(schema)
    def test_examples_validate_and_references_match(self):
        for name,path in [('workspace','workspace/workspace'),('workspace','workspace/control'),('workspace','workspace/browser'),('project','project/gitive.project'),('ticket','ticket/ticket')]:
            self.validator(name).validate(load('templates/'+path+'.json'))
        workspace=load('templates/workspace/workspace.json');project=load('templates/project/gitive.project.json');ticket=load('templates/ticket/ticket.json')
        self.assertEqual(project['workspace_ref'],workspace['id'])
        self.assertEqual(ticket['project_ref'],project['id'])
    def test_unverified_environment_cannot_declare_ready(self):
        row=load('templates/workspace/workspace.json');row['provisioning']='ready'
        with self.assertRaises(ValidationError):self.validator('workspace').validate(row)
    def test_pc_write_and_unknown_options_rejected(self):
        row=load('templates/workspace/workspace.json');row['source']['access']='read-write'
        with self.assertRaises(ValidationError):self.validator('workspace').validate(row)
        row=load('templates/workspace/workspace.json');row['environment']['api_key']='not-a-real-key'
        with self.assertRaises(ValidationError):self.validator('workspace').validate(row)
    def test_ticket_escape_and_unverified_merge_rejected(self):
        row=load('templates/ticket/ticket.json')
        for bad in ['../other','src/../../outside','/etc/passwd']:
            candidate=copy.deepcopy(row);candidate['allowed_paths']=[bad]
            with self.assertRaises(ValidationError):self.validator('ticket').validate(candidate)
        row['status']='merged'
        with self.assertRaises(ValidationError):self.validator('ticket').validate(row)
    def test_browser_has_no_project_requirement(self):
        row=load('templates/workspace/browser.json')
        self.assertEqual(row['project_refs'],[])
        self.assertEqual(row['kind'],'browser')
        self.validator('workspace').validate(row)
