import json
import hashlib
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from benchmark.transcripts import Recorder


class TranscriptTests(unittest.TestCase):
    def test_full_content_redacted_and_receipts_verified(self):
        with tempfile.TemporaryDirectory() as temp, patch.dict(os.environ, {'OPENROUTER_API_KEY': 'synthetic-secret-123'}):
            root=Path(temp); recorder=Recorder(root/'private',root)
            receipt=recorder.request('call1', {'model':'fixture','messages':[{'role':'user','content':'code ] synthetic-secret-123'}],
                'api_key':'synthetic-secret-123','extra_headers':{'Authorization':'Bearer secret'}}, {'iteration':1})
            raw=(root/receipt['path']).read_bytes()
            self.assertEqual(hashlib.sha256(raw).hexdigest(),receipt['sha256'])
            self.assertNotIn(b'synthetic-secret-123',raw)
            data=json.loads(raw)
            self.assertEqual(data['request']['messages'][0]['content'],'code ] [REDACTED]')
            self.assertNotIn('extra_headers',data['request'])
            response={'choices':[{'message':{'content':'[malformed','reasoning_content':'explanation'},'finish_reason':'length'}],
                      'usage':{'total_tokens':42}}
            result=recorder.response('call1',response)
            self.assertEqual(json.loads((root/result['path']).read_text())['response'],response)
            self.assertEqual((root/result['path']).stat().st_mode & 0o777,0o600)
            with self.assertRaises(ValueError): recorder.response('call1',response)

    def test_error_redaction(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp); recorder=Recorder(root/'private',root)
            receipt=recorder.write('call1','error',{'message':'Authorization ghp_FAKE01234567890'})
            self.assertNotIn('ghp_', (root/receipt['path']).read_text())
