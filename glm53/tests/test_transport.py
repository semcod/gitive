import json
import os
from http.server import BaseHTTPRequestHandler, HTTPServer
import threading
import unittest
from unittest.mock import patch
from intuition.llm import Client


class TransportTests(unittest.TestCase):
    def test_budget_and_usage_on_invalid_json(self):
        from types import SimpleNamespace
        from unittest.mock import Mock
        completion = Mock(return_value=SimpleNamespace(choices=[SimpleNamespace(
            finish_reason="stop", message=SimpleNamespace(content="{"))],
            usage=SimpleNamespace(total_tokens=42)))
        with patch.dict('sys.modules', {'litellm': SimpleNamespace(completion=completion)}), patch.dict(
            os.environ, {'LLM_MAX_CALLS': '1'}, clear=True
        ):
            client = Client('litellm')
            with self.assertRaises(ValueError):
                client('PROPOSE.', '{}', .8)
            with self.assertRaisesRegex(RuntimeError, 'budget'):
                client('PROPOSE.', '{}', .8)
        self.assertEqual(completion.call_count, 1)
        self.assertEqual(client.events[0]['tokens'], 42)
        self.assertEqual(client.events[0]['status'], 'error')
        self.assertEqual(completion.call_args.kwargs['num_retries'], 0)

    def test_compatible_real_http(self):
        requests = []
        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass
            def do_POST(self):
                requests.append((self.path, json.loads(self.rfile.read(int(self.headers['Content-Length'])))))
                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({'choices': [{'message': {'content': '[{"content":"sample"}]'}}]}).encode())
        server = HTTPServer(('127.0.0.1', 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            with patch.dict(os.environ, {'LLM_BASE_URL': f'http://127.0.0.1:{server.server_port}/v1', 'LLM_MODEL': 'test-model'}):
                result = Client('compatible')('system', 'user', .8)
            self.assertEqual(result, [{'content': 'sample'}])
            self.assertEqual(requests[0][0], '/v1/chat/completions')
            self.assertEqual(requests[0][1]['temperature'], .8)
            self.assertEqual(requests[0][1]['model'], 'test-model')
        finally:
            server.shutdown()
            server.server_close()
            thread.join()

    def test_litellm_reasoning_and_truncated_response(self):
        from types import SimpleNamespace
        from unittest.mock import Mock
        completion = Mock(return_value=SimpleNamespace(choices=[SimpleNamespace(
            finish_reason='length', message=SimpleNamespace(content=None))]))
        with patch.dict('sys.modules', {'litellm': SimpleNamespace(completion=completion)}), patch.dict(
            os.environ, {'LLM_MODEL': 'openrouter/z-ai/glm-5.3', 'LLM_REASONING_EFFORT': 'low'}, clear=True
        ):
            with self.assertRaisesRegex(ValueError, 'truncated'):
                Client('litellm')('system', 'user', .2)
        self.assertEqual(completion.call_args.kwargs['reasoning_effort'], 'low')
        self.assertEqual(completion.call_count, 2)
