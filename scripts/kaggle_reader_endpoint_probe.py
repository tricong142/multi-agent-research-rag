"""Compare real Reader requests through SDK and REST; four attempts, no retries or GPU."""
import argparse
import hashlib
import http.client
import json
import os
import re
import time
from datetime import datetime, timezone
from importlib.metadata import version
from pathlib import Path

import httpx
from google import genai

from train_agent2_reader import reader_policy

if __package__:
    from .kaggle_gemini_probe import redact_gemini_error_message
else:
    from kaggle_gemini_probe import redact_gemini_error_message


def reader_cases(inputs):
    return (
        ('router', reader_policy.RouterDecision,
         reader_policy.ROUTER_SYSTEM_PROMPT + '\n\nDac trung heuristic cua trang can quyet dinh:\n'
         + str(inputs['router_features'])),
        ('critique', reader_policy.CritiqueResult,
         reader_policy.CRITIQUE_SYSTEM_PROMPT + '\n\nTom tat ket qua trich xuat can danh gia:\n'
         + str(inputs['critique_summary'])),
    )


def client_options(transport=None, hooks=None):
    args = {}
    if transport is not None:
        args['transport'] = transport
    if hooks is not None:
        args['event_hooks'] = {'request': [hooks]}
    return {'api_version': 'v1beta', 'timeout': 30000, 'retry_options': {'attempts': 1},
            'client_args': args}


def capture_request(model, schema, prompt):
    """Use the installed SDK to serialize the exact body, with an offline transport."""
    captured = []
    def handler(request):
        captured.append((request.url.path, request.content))
        return httpx.Response(200, json={})
    client = genai.Client(api_key='offline-fixture-key', vertexai=False,
                         http_options=client_options(httpx.MockTransport(handler)))
    try:
        client.models.generate_content(model=model, contents=prompt,
            config={'response_mime_type': 'application/json', 'response_schema': schema,
                    'http_options': {'timeout': 30000, 'retry_options': {'attempts': 1}}})
    finally:
        client.close()
    if len(captured) != 1 or captured[0][0] != '/v1beta/models/' + model + ':generateContent':
        raise ValueError('Unexpected SDK request serialization')
    return captured[0]


def safe_error(event, payload, key):
    error = payload.get('error', payload) if isinstance(payload, dict) else {}
    if not isinstance(error, dict):
        error = {}
    status = error.get('status')
    if status in ('INVALID_ARGUMENT', 'UNAUTHENTICATED', 'PERMISSION_DENIED', 'NOT_FOUND',
                  'RESOURCE_EXHAUSTED', 'INTERNAL', 'UNAVAILABLE', 'DEADLINE_EXCEEDED'):
        event['api_status'] = status
    event['error_message_redacted'] = redact_gemini_error_message(error.get('message'), key)


def run_probe(inputs, output_dir, *, model, key, interval=61):
    if not re.fullmatch(r'[A-Za-z0-9_.-]{1,100}', model) or not key:
        raise ValueError('A valid model and API key are required')
    if interval != 61:
        raise ValueError('The diagnostic preserves the 61-second request interval')
    output_dir.mkdir(parents=True, exist_ok=False)
    criteria = {'recorded_before_requests': True, 'model': model, 'sdk_version': version('google-genai'),
                'maximum_live_requests': 4, 'attempts_per_case': 1, 'request_timeout_seconds': 30,
                'request_interval_seconds': interval, 'case_order': ['router/sdk', 'router/rest', 'critique/sdk', 'critique/rest'],
                'scope': 'Request/response contract diagnostic on frozen development inputs; not extraction quality or final E2E.',
                'inputs_sha256': hashlib.sha256(json.dumps(inputs, ensure_ascii=False).encode()).hexdigest()}
    (output_dir / 'criteria.json').write_text(json.dumps(criteria, indent=2), encoding='utf-8')
    (output_dir / 'inputs.json').write_text(json.dumps(inputs, ensure_ascii=False, indent=2), encoding='utf-8')
    records, last_started = [], None
    with (output_dir / 'requests.jsonl').open('x', encoding='utf-8') as log:
        stop = False
        for role, schema, prompt in reader_cases(inputs):
            path, body = capture_request(model, schema, prompt)
            (output_dir / (role + '-request.json')).write_bytes(body)
            for backend in ('sdk', 'rest'):
                event = {'role': role, 'backend': backend, 'model': model, 'http_status': None,
                         'contract_pass': False, 'request_sha256': hashlib.sha256(body).hexdigest(),
                         'request_bytes': len(body), 'attempts': 1}
                if last_started is not None:
                    wait = max(0, last_started + interval - time.monotonic())
                    if wait:
                        time.sleep(wait)
                started = last_started = time.monotonic()
                event['checked_at_utc'] = datetime.now(timezone.utc).isoformat()
                client = connection = None
                try:
                    if backend == 'sdk':
                        sent = []
                        def guard(request):
                            if sent:
                                raise RuntimeError('More than one SDK request was attempted')
                            sent.append(request.content)
                            if request.url.host != 'generativelanguage.googleapis.com' or request.url.path != path or request.content != body:
                                raise ValueError('SDK live payload differs from its offline serialization')
                        client = genai.Client(api_key=key, vertexai=False,
                                             http_options=client_options(hooks=guard))
                        response = client.models.generate_content(model=model, contents=prompt,
                            config={'response_mime_type': 'application/json', 'response_schema': schema,
                                    'http_options': {'timeout': 30000, 'retry_options': {'attempts': 1}}})
                        parsed = schema.model_validate(response.parsed)
                        usage = getattr(response, 'usage_metadata', None)
                        usage = usage.model_dump() if usage is not None else {}
                    else:
                        connection = http.client.HTTPSConnection('generativelanguage.googleapis.com', timeout=30)
                        connection.request('POST', path, body=body,
                                           headers={'x-goog-api-key': key, 'Content-Type': 'application/json'})
                        response = connection.getresponse()
                        event['http_status'] = response.status
                        data = json.loads(response.read(1024 * 1024))
                        if response.status != 200:
                            safe_error(event, data, key)
                            raise RuntimeError('Provider HTTP error')
                        candidates = data.get('candidates') or []
                        parts = candidates[0].get('content', {}).get('parts', []) if candidates else []
                        text = ''.join(part.get('text', '') for part in parts if not part.get('thought'))
                        parsed = schema.model_validate_json(text)
                        usage = data.get('usageMetadata', {})
                    event['contract_pass'] = True
                    if not isinstance(usage, dict):
                        usage = {}
                    usage_names = (('promptTokenCount', 'prompt_token_count'),
                                   ('candidatesTokenCount', 'candidates_token_count'),
                                   ('thoughtsTokenCount', 'thoughts_token_count'),
                                   ('totalTokenCount', 'total_token_count'))
                    event['usage'] = {camel: value for camel, snake in usage_names
                                      if type(value := usage.get(camel if backend == 'rest' else snake)) is int and value >= 0}
                    # Keep only bounded decision fields; no generated explanation or raw body.
                    event['decision'] = ({'chosen_tool': parsed.chosen_tool, 'confidence': parsed.confidence}
                                         if role == 'router' else
                                         {'is_acceptable': parsed.is_acceptable, 'suggested_action': parsed.suggested_action})
                except Exception as exc:
                    event['error_type'] = type(exc).__name__
                    code = getattr(exc, 'code', None)
                    if type(code) is int:
                        event['http_status'] = code
                    if backend == 'sdk':
                        safe_error(event, getattr(exc, 'details', {}), key)
                finally:
                    if client is not None:
                        client.close()
                    if connection is not None:
                        connection.close()
                    event['elapsed_ms'] = round((time.monotonic() - started) * 1000, 3)
                    records.append(event)
                    log.write(json.dumps(event, ensure_ascii=False) + '\n')
                    log.flush()
                if event['http_status'] in (400, 401, 403, 404, 429):
                    stop = True
                    break
            if stop:
                break
    passed = {backend: all(any(r['role'] == role and r['backend'] == backend and r['contract_pass']
                              for r in records) for role in ('router', 'critique')) for backend in ('sdk', 'rest')}
    result = {'model': model, 'request_count': len(records), 'backend_contract_pass': passed,
              'stopped_on_client_or_quota_error': stop, 'requests': records,
              'quality_gate_pass': None, 'backend_promotion': False,
              'cost_usd': None,
              'note': 'Single observations can suggest a transport difference, but do not establish causality or extraction quality.'}
    (output_dir / 'summary.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--inputs', type=Path, required=True)
    parser.add_argument('--output-dir', type=Path, required=True)
    args = parser.parse_args()
    result = run_probe(json.loads(args.inputs.read_text(encoding='utf-8')), args.output_dir,
                       model=os.environ.get('GEMINI_MODEL', 'gemini-3.6-flash'), key=os.environ.get('GEMINI_API_KEY'))
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if all(result['backend_contract_pass'].values()) else 1


if __name__ == '__main__':
    raise SystemExit(main())
