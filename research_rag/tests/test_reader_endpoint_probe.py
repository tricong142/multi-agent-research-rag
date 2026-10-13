"""Exercise both diagnostic transports without network, model weights or a GPU."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import httpx
from google import genai

from scripts import kaggle_reader_endpoint_probe as probe
from research_rag.tests.test_reader_api_retry import Clock


INPUTS = {'router_features': {'has_text_layer': True, 'avg_block_count': 45,
          'image_area_ratio': 0.12, 'page_width': 600, 'page_height': 800},
          'critique_summary': {'source_tool': 'layoutlmv3', 'num_blocks': 128,
          'avg_confidence': 0.9, 'sample_texts': ['fixture'], 'page_width': 600, 'page_height': 800}}
DECISIONS = {'router': {'chosen_tool': 'layoutlmv3', 'confidence': 0.9, 'reasoning': 'fixture'},
             'critique': {'is_acceptable': True, 'issues': [], 'suggested_action': 'accept', 'reasoning': 'fixture'}}


class ReaderEndpointProbeTests(unittest.TestCase):
    def exercise(self, sdk_status=200, rest_status=200, *, invalid_rest=False):
        clock, sdk_requests, rest_requests = Clock(), [], []
        secret = 'diagnostic-private-key'
        def data(role, status, invalid=False):
            if status != 200:
                return {'error': {'code': status, 'status': 'UNAVAILABLE' if status == 503 else 'PERMISSION_DENIED',
                                 'message': 'Provider explanation ' + secret + ' person@example.test projects/private-project'}}
            decision = {'chosen_tool': 'invalid-tool'} if invalid else DECISIONS[role]
            return {'candidates': [{'content': {'role': 'model', 'parts': [{'text': json.dumps(decision)}]}}],
                    'usageMetadata': {'promptTokenCount': 8, 'candidatesTokenCount': 3, 'totalTokenCount': 11}}
        def role_of(body):
            return 'router' if 'chosen_tool' in json.loads(body)['generationConfig']['responseSchema']['properties'] else 'critique'
        def handler(request):
            role = role_of(request.content)
            sdk_requests.append((role, request.content, clock.now))
            return httpx.Response(sdk_status, json=data(role, sdk_status))
        real_client = genai.Client
        def client_factory(**kwargs):
            options = kwargs['http_options']
            self.assertEqual(options['retry_options']['attempts'], 1)
            if 'transport' not in options['client_args']:
                options['client_args']['transport'] = httpx.MockTransport(handler)
            return real_client(**kwargs)
        def connection_factory(host, timeout):
            self.assertEqual(host, 'generativelanguage.googleapis.com')
            self.assertEqual(timeout, 30)
            connection = Mock()
            def request(method, path, *, body, headers):
                self.assertEqual(method, 'POST')
                self.assertNotIn(secret, path)
                self.assertEqual(headers['x-goog-api-key'], secret)
                role = role_of(body)
                rest_requests.append((role, body, clock.now))
                connection.getresponse.return_value = Mock(status=rest_status)
                connection.getresponse.return_value.read.return_value = json.dumps(data(role, rest_status, invalid_rest)).encode()
            connection.request.side_effect = request
            return connection
        with tempfile.TemporaryDirectory() as temp, \
                patch.object(probe.genai, 'Client', side_effect=client_factory), \
                patch.object(probe.http.client, 'HTTPSConnection', side_effect=connection_factory), \
                patch.object(probe.time, 'monotonic', side_effect=lambda: clock.now), \
                patch.object(probe.time, 'sleep', side_effect=clock.sleep):
            out = Path(temp) / 'result'
            result = probe.run_probe(INPUTS, out, model='gemini-3.6-flash', key=secret)
            self.assertEqual(result, json.loads((out / 'summary.json').read_text()))
            self.assertEqual(len((out / 'requests.jsonl').read_text().splitlines()), result['request_count'])
            for file in out.iterdir():
                self.assertNotIn(secret, file.read_text())
                self.assertNotIn('person@example.test', file.read_text())
                self.assertNotIn('projects/private-project', file.read_text())
            before = {p.name: p.read_bytes() for p in out.iterdir()}
            with self.assertRaises(FileExistsError):
                probe.run_probe(INPUTS, out, model='gemini-3.6-flash', key=secret)
            self.assertEqual(before, {p.name: p.read_bytes() for p in out.iterdir()})
        return result, sdk_requests, rest_requests, clock

    def test_identical_sdk_and_rest_payloads_pass_both_contracts_with_pacing(self):
        result, sdk, rest, clock = self.exercise()
        self.assertEqual(result['request_count'], 4)
        self.assertEqual(result['backend_contract_pass'], {'sdk': True, 'rest': True})
        self.assertEqual([(role, body) for role, body, _ in sdk], [(role, body) for role, body, _ in rest])
        self.assertEqual([e['backend'] for e in result['requests']], ['sdk', 'rest', 'sdk', 'rest'])
        self.assertEqual(clock.sleeps, [61, 61, 61])
        self.assertIsNone(result['quality_gate_pass'])
        self.assertFalse(result['backend_promotion'])
        self.assertTrue(all(e['usage'] == {'promptTokenCount': 8, 'candidatesTokenCount': 3, 'totalTokenCount': 11}
                            for e in result['requests']))

    def test_repeated_503_is_four_comparisons_without_hidden_sdk_retries(self):
        result, sdk, rest, _ = self.exercise(503, 503)
        self.assertEqual((len(sdk), len(rest)), (2, 2))
        self.assertEqual(result['backend_contract_pass'], {'sdk': False, 'rest': False})
        self.assertTrue(all(e['http_status'] == 503 for e in result['requests']))
        self.assertTrue(all('Provider explanation' in e['error_message_redacted'] for e in result['requests']))

    def test_rest_only_success_is_recorded_without_promoting_a_backend(self):
        result, sdk, rest, _ = self.exercise(503, 200)
        self.assertEqual((len(sdk), len(rest)), (2, 2))
        self.assertEqual(result['backend_contract_pass'], {'sdk': False, 'rest': True})
        self.assertFalse(result['backend_promotion'])

    def test_client_and_quota_errors_stop_before_further_requests(self):
        for status in (400, 401, 403, 404, 429):
            with self.subTest(status=status):
                result, sdk, rest, clock = self.exercise(status, 200)
                self.assertEqual((len(sdk), len(rest)), (1, 0))
                self.assertTrue(result['stopped_on_client_or_quota_error'])
                self.assertEqual(clock.sleeps, [])

    def test_invalid_structured_rest_output_never_passes_the_contract(self):
        result, _, _, _ = self.exercise(200, 200, invalid_rest=True)
        self.assertEqual(result['backend_contract_pass'], {'sdk': True, 'rest': False})
        self.assertTrue(all(not e['contract_pass'] for e in result['requests'] if e['backend'] == 'rest'))


if __name__ == '__main__':
    unittest.main()
