"""Exercise the actual SDK transport policy without sending data to Gemini."""

import json
import unittest
from datetime import datetime, timezone
from email.utils import format_datetime
from types import SimpleNamespace
from unittest.mock import Mock, patch

import httpx
from google import genai
from google.genai import errors

from train_agent2_reader import reader_policy
from train_agent2_reader.reader_agent import ReaderAgent


class Clock:
    def __init__(self):
        self.now = 100.0
        self.sleeps = []

    def sleep(self, seconds):
        self.sleeps.append(seconds)
        self.now += seconds


class ReaderApiRetryTests(unittest.TestCase):
    def run_requests(self, statuses, *, interval=0, budget=240, retry_after=None,
                     duration=0, use_reader=False, error_details=None):
        requests, starts, events = [], [], []
        clock = Clock()

        def handler(request):
            requests.append(request)
            starts.append(clock.now)
            clock.now += duration
            status = statuses[min(len(requests) - 1, len(statuses) - 1)]
            if status != 200:
                return httpx.Response(status, headers={"Retry-After": str(retry_after)} if retry_after else {},
                                      json={"error": {"code": status, "message": "secret-in-error",
                                            "status": "RESOURCE_EXHAUSTED", "details": error_details or []}})
            return httpx.Response(200, json={"candidates": [{"content": {"role": "model", "parts": [
                {"text": '{"is_acceptable":true,"issues":[],"suggested_action":"accept","reasoning":"fixture"}'}
            ]}}]})

        real_client = genai.Client
        clients = []

        def client_factory(**kwargs):
            self.assertEqual(kwargs["http_options"]["retry_options"]["attempts"], 1)
            kwargs["http_options"]["client_args"] = {"transport": httpx.MockTransport(handler)}
            client = real_client(**kwargs)
            clients.append(client)
            return client

        try:
            with patch.object(reader_policy, "_client", None), \
                    patch.object(reader_policy, "_last_request_at", None), \
                    patch.object(reader_policy.time, "monotonic", side_effect=lambda: clock.now), \
                    patch.object(reader_policy.time, "sleep", side_effect=clock.sleep), \
                    patch.object(reader_policy.random, "uniform", return_value=0.25), \
                    patch.dict("os.environ", {"GEMINI_API_KEY": "test-only", "GOOGLE_GENAI_USE_VERTEXAI": "false",
                        "GEMINI_REQUEST_INTERVAL_SECONDS": str(interval), "GEMINI_CALL_BUDGET_SECONDS": str(budget)}), \
                    patch.object(reader_policy.genai, "Client", side_effect=client_factory):
                try:
                    if use_reader:
                        agent = ReaderAgent()
                        features = {"has_text_layer": True, "avg_block_count": 1, "image_area_ratio": 0,
                                    "page_width": 600, "page_height": 800}
                        with patch.object(agent, "_extract_heuristic_features", return_value=features), \
                                patch.object(agent, "_run_tool", return_value=[SimpleNamespace(text="fixture", confidence=1)]):
                            result = agent.process_page("unused.pdf")
                        events.extend(result["attempts"][0]["api_attempts"])
                    else:
                        result = reader_policy.get_critique({"sample_texts": ["synthetic fixture"]}, on_attempt=events.append)
                except (errors.APIError, reader_policy.ReaderApiBudgetExceeded) as exc:
                    result = exc
            return result, requests, starts, events, clock
        finally:
            for client in clients:
                client.close()

    def test_transient_503_recovers_with_one_retry_owner_and_real_transport_timeout(self):
        result, requests, starts, events, _ = self.run_requests([503, 200])
        self.assertTrue(result.is_acceptable)
        self.assertEqual(len(requests), 2)
        self.assertEqual(requests[0].extensions["timeout"]["read"], 30.0)
        self.assertEqual([event["outcome"] for event in events], ["retry", "success"])
        self.assertIsNone(events[-1]["http_status"])
        self.assertEqual(starts, [100, 101.25])
        self.assertEqual({event["stage"] for event in events}, {"critique"})
        self.assertEqual({event["model"] for event in events}, {reader_policy.GEMINI_MODEL})
        self.assertNotIn("secret-in-error", json.dumps(events))
        self.assertNotIn("test-only", json.dumps(events))

    def test_persistent_503_stops_after_three_transport_attempts(self):
        result, requests, _, events, _ = self.run_requests([503])
        self.assertEqual(result.code, 503)
        self.assertEqual(len(requests), 3)
        self.assertEqual(events[-1]["outcome"], "exhausted")
        self.assertTrue(all(event.get("next_backoff_ms", 0) <= 4000 for event in events))

    def test_quota_metadata_is_allowlisted_and_sdk_retry_info_is_honored(self):
        details = [
            {"@type": "type.googleapis.com/google.rpc.ErrorInfo", "reason": "RATE_LIMIT_EXCEEDED",
             "domain": "googleapis.com", "metadata": {"consumer": "projects/private-identity", "key": "test-only"}},
            {"@type": "type.googleapis.com/google.rpc.QuotaFailure", "violations": [
                {"quotaMetric": "generativelanguage.googleapis.com/generate_content_free_tier_requests",
                 "quotaId": "GenerateRequestsPerDayPerProjectPerModel-FreeTier", "quotaValue": "20",
                 "description": "secret-in-error", "subject": "private-identity",
                 "quotaDimensions": {"model": "gemini-test", "location": "global", "project": "private-identity"}}]},
            {"@type": "type.googleapis.com/google.rpc.RetryInfo", "retryDelay": "70.5s"},
            {"@type": "unknown", "token": "test-only"}]
        result, requests, starts, events, _ = self.run_requests([429, 200], error_details=details)
        self.assertTrue(result.is_acceptable)
        self.assertEqual(starts, [100, 170.5])
        info = events[0]["error_details"]
        self.assertEqual(info["error_info"]["reason"], "RATE_LIMIT_EXCEEDED")
        self.assertEqual(info["quota_violations"][0]["quotaValue"], "20")
        self.assertEqual(events[0]["retry_after_ms"], 70500)
        for secret in ("secret-in-error", "test-only", "private-identity", "consumer", "description"):
            self.assertNotIn(secret, json.dumps(events))
        result, requests, _, events, clock = self.run_requests([429], budget=60, error_details=details)
        self.assertIsInstance(result, reader_policy.ReaderApiBudgetExceeded)
        self.assertEqual(len(requests), 1)
        self.assertEqual(clock.sleeps, [])
        self.assertEqual(events[-1]["outcome"], "deadline_exceeded")

    def test_malformed_metadata_and_secrets_inside_allowed_fields_are_not_logged(self):
        key = "AIza" + "x" * 35
        details = {"error": {"status": key, "message": "secret message", "details": [
            {"@type": "type.googleapis.com/google.rpc.ErrorInfo", "reason": "test-only", "domain": "projects/private"},
            {"@type": "type.googleapis.com/google.rpc.QuotaFailure", "violations": [
                {"quotaMetric": key, "quotaId": "https://example.invalid", "quotaValue": 10**400,
                 "quotaDimensions": {"model": "test-only", "location": "test-only"}}, None]},
            {"@type": "type.googleapis.com/google.rpc.RetryInfo", "retryDelay": "Infinitys"}, None]}}
        with patch.dict("os.environ", {"GEMINI_API_KEY": "test-only"}):
            result = reader_policy.safe_error_details(errors.APIError(429, details))
        for secret in (key, "test-only", "private", "secret message", "example.invalid"):
            self.assertNotIn(secret, json.dumps(result))
        self.assertNotIn("retry_delay_seconds", result)
        for payload in (None, [], {"error": None}, {"error": {"details": "invalid"}}):
            self.assertEqual(reader_policy.safe_error_details(SimpleNamespace(details=payload)), {})

    def test_non_retryable_client_errors_stop_after_one_attempt(self):
        for status in (400, 401, 403, 404):
            with self.subTest(status=status):
                result, requests, _, events, _ = self.run_requests([status])
                self.assertEqual(result.code, status)
                self.assertEqual(len(requests), 1)
                self.assertEqual(events[-1]["outcome"], "non_retryable")

    def test_pacing_applies_to_each_transport_retry(self):
        _, requests, starts, events, _ = self.run_requests([503, 503, 200], interval=61)
        self.assertEqual(len(requests), 3)
        self.assertEqual(starts, [100, 161, 222])
        self.assertEqual([event["wait_ms"] for event in events], [0, 61000, 61000])

    def test_retry_after_is_respected_without_unbounded_wait(self):
        _, _, starts, _, _ = self.run_requests([503, 200], retry_after=10)
        self.assertEqual(starts, [100, 110])
        result, requests, _, events, clock = self.run_requests([503, 200], retry_after=300)
        self.assertIsInstance(result, reader_policy.ReaderApiBudgetExceeded)
        self.assertEqual(len(requests), 1)
        self.assertEqual(clock.sleeps, [])
        self.assertEqual(events[-1]["outcome"], "deadline_exceeded")

    def test_retry_after_http_date_and_invalid_headers(self):
        with patch.object(reader_policy.time, "time", return_value=100):
            date = format_datetime(datetime.fromtimestamp(109, timezone.utc), usegmt=True)
            exc = SimpleNamespace(response=SimpleNamespace(headers={"Retry-After": date}))
            self.assertEqual(reader_policy._retry_after(exc), 9)
            for value in ("nan", "inf", "-1", "invalid", ""):
                exc.response.headers["Retry-After"] = value
                self.assertEqual(reader_policy._retry_after(exc), 0)

    def test_budget_includes_pacing_and_shrinks_transport_timeout(self):
        result, requests, _, events, _ = self.run_requests([503, 200], interval=61, budget=60)
        self.assertIsInstance(result, reader_policy.ReaderApiBudgetExceeded)
        self.assertEqual(len(requests), 1)
        result, requests, _, _, _ = self.run_requests([503, 200], retry_after=9, budget=10)
        self.assertTrue(result.is_acceptable)
        self.assertEqual(requests[1].extensions["timeout"]["read"], 1.0)

    def test_late_response_is_rejected(self):
        result, requests, _, events, _ = self.run_requests([200], budget=10, duration=11)
        self.assertIsInstance(result, reader_policy.ReaderApiBudgetExceeded)
        self.assertEqual(len(requests), 1)
        self.assertEqual(events[0]["outcome"], "deadline_exceeded")
        self.assertIsNone(events[-1]["http_status"])

    def test_late_success_does_not_report_prior_503_as_latest_status(self):
        result, requests, _, events, _ = self.run_requests([503, 200], budget=22, duration=11)
        self.assertIsInstance(result, reader_policy.ReaderApiBudgetExceeded)
        self.assertEqual(len(requests), 2)
        self.assertIsNone(events[-1]["http_status"])
        self.assertEqual(events[-2]["outcome"], "deadline_exceeded")

    def test_reader_failure_keeps_api_trace_and_never_accepts_text(self):
        result, requests, _, events, _ = self.run_requests([503], use_reader=True)
        self.assertFalse(result["success"])
        self.assertEqual(result["blocks"], [])
        self.assertEqual(len(requests), 3)
        self.assertEqual(result["attempts"][0]["http_status"], 503)
        self.assertEqual(len(events), 3)
        self.assertNotIn("secret-in-error", json.dumps(result))

    def test_router_and_critic_share_pacing_between_logical_calls(self):
        clock = Clock()
        client = Mock()
        client.models.generate_content.return_value = SimpleNamespace(parsed="parsed fixture")
        with patch.dict("os.environ", {"GEMINI_REQUEST_INTERVAL_SECONDS": "2"}), \
                patch.object(reader_policy, "get_client", return_value=client), \
                patch.object(reader_policy, "_last_request_at", 99.0), \
                patch.object(reader_policy.time, "monotonic", side_effect=lambda: clock.now), \
                patch.object(reader_policy.time, "sleep", side_effect=clock.sleep):
            self.assertEqual(reader_policy.get_router_decision({}), "parsed fixture")
            self.assertEqual(reader_policy.get_critique({}), "parsed fixture")
        self.assertEqual(clock.sleeps, [1.0, 2.0])

    def test_invalid_policy_fails_before_api_call(self):
        for name, values in (("GEMINI_REQUEST_INTERVAL_SECONDS", ["nan", "inf", "-1"]),
                             ("GEMINI_CALL_BUDGET_SECONDS", ["nan", "inf", "-1", "0"])):
            for value in values:
                with self.subTest(name=name, value=value), patch.dict("os.environ", {name: value}), \
                        patch.object(reader_policy, "get_client") as client:
                    with self.assertRaises(ValueError):
                        reader_policy.get_critique({})
                    client.assert_not_called()


if __name__ == "__main__":
    unittest.main()
