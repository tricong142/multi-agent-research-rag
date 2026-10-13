"""Small Gemini availability probe embedded in the Reader notebook; no retries."""
import http.client
import json
import re
import time
from datetime import datetime, timezone
from urllib.parse import quote, quote_plus


def redact_gemini_error_message(message, key):
    """Keep the provider's explanation while removing credentials and common identifiers."""
    if not isinstance(message, str):
        return ""
    # Redact before truncating, so a key crossing the output boundary cannot leak.
    if isinstance(key, str) and key:
        for value in sorted({key, quote(key, safe=""), quote_plus(key)}, key=len, reverse=True):
            message = re.sub(re.escape(value), "[REDACTED]", message, flags=re.IGNORECASE)
    patterns = (
        r"AIza[A-Za-z0-9_-]+",
        r"https?://[^\s<>\"']+",
        r"[A-Za-z0-9_.+%-]+@[A-Za-z0-9.-]+",
        r"\b(?:projects|organizations|folders|users)/[A-Za-z0-9_.:@-]+",
        r"\b(?:project|consumer|account)\s*(?:id|number)?\s*[:=]?\s*[\"'][^\"']+[\"']",
        r"\b(?:project|consumer|account)\s*(?:id|number)?\s*[:=]\s*[A-Za-z0-9_-]+",
        r"\b(?:\d{1,3}\.){3}\d{1,3}\b",
        r"(?<![\w:])(?:[0-9a-f]{0,4}:){2,}[0-9a-f]{0,4}(?![\w:])",
        r"\b\d{6,}\b",
        r"\b(?:bearer|api[_ -]?key|access[_ -]?token|authorization)\s*[:=]\s*[^\s,;]+",
        r"\bbearer\s+[A-Za-z0-9_.~+/-]+=*",
    )
    for pattern in patterns:
        message = re.sub(pattern, "[REDACTED]", message, flags=re.IGNORECASE)
    message = " ".join(message.split())
    return message[:1000] + ("..." if len(message) > 1000 else "")


def check_gemini_endpoint(model="gemini-3.6-flash"):
    result = {"checked_at_utc": datetime.now(timezone.utc).isoformat(),
              "model": model, "endpoint_available": False, "requests": []}
    if not re.fullmatch(r"[a-zA-Z0-9_.-]{1,100}", model):
        result.update(model="invalid", error_type="InvalidModelName", failure_stage="validate_model")
        return result
    key = None
    stage = "import_kaggle_secrets"
    try:
        from kaggle_secrets import UserSecretsClient
        stage = "create_secret_client"
        secret_client = UserSecretsClient()
        stage = "read_kaggle_secret"
        key = secret_client.get_secret("GEMINI_API_KEY")
        stage = "build_request"
        payload = {"contents": [{"parts": [{"text": "Return JSON with ok set to true."}]}],
                   "generationConfig": {"maxOutputTokens": 512, "responseMimeType": "application/json",
                       "responseSchema": {"type": "OBJECT", "properties": {"ok": {"type": "BOOLEAN"}},
                                          "required": ["ok"]}}}
        for stage, method, suffix, body in [("metadata", "GET", "", None),
                ("generation", "POST", ":generateContent", json.dumps(payload))]:
            event = {"stage": stage}
            result["requests"].append(event)
            started = time.monotonic()
            connection = http.client.HTTPSConnection("generativelanguage.googleapis.com", timeout=30)
            try:
                connection.request(method, "/v1beta/models/" + model + suffix, body=body,
                                   headers={"x-goog-api-key": key, "Content-Type": "application/json"})
                response = connection.getresponse()
                event["http_status"] = response.status
                data = json.loads(response.read(65536))
            finally:
                connection.close()
                event["elapsed_ms"] = round((time.monotonic() - started) * 1000, 3)
            if event["http_status"] != 200:
                error = data.get("error", {})
                status = error.get("status")
                event["api_status"] = status if status in (
                    "INVALID_ARGUMENT", "UNAUTHENTICATED", "PERMISSION_DENIED", "NOT_FOUND",
                    "RESOURCE_EXHAUSTED", "INTERNAL", "UNAVAILABLE", "DEADLINE_EXCEEDED"
                ) else "UNKNOWN"
                # Keep known reason codes; never copy ErrorInfo account metadata.
                known_reasons = ("SERVICE_DISABLED", "BILLING_DISABLED", "API_KEY_INVALID",
                    "API_KEY_SERVICE_BLOCKED", "API_KEY_HTTP_REFERRER_BLOCKED", "API_KEY_IP_ADDRESS_BLOCKED",
                    "API_KEY_ANDROID_APP_BLOCKED", "API_KEY_IOS_APP_BLOCKED", "USER_PROJECT_DENIED",
                    "CONSUMER_SUSPENDED", "CONSUMER_INVALID")
                details = error.get("details", [])
                event["error_reasons"] = sorted({detail["reason"] for detail in details
                    if isinstance(detail, dict) and detail.get("@type") == "type.googleapis.com/google.rpc.ErrorInfo"
                    and detail.get("reason") in known_reasons}) if isinstance(details, list) else []
                message = error.get("message", "")
                event["error_message_redacted"] = redact_gemini_error_message(message, key)
                if isinstance(message, str) and "reported as leaked" in message.lower():
                    event["message_hint"] = "API_KEY_REPORTED_LEAKED"
                result.update(failure_stage=stage, failure_reason="http_error")
                break
            if stage == "metadata":
                event["model_matches"] = data.get("name") == "models/" + model
                if not event["model_matches"]:
                    result.update(failure_stage=stage, failure_reason="model_name_mismatch")
                    break
            else:
                candidate = data.get("candidates", [{}])[0]
                finish = candidate.get("finishReason")
                if finish in ("STOP", "MAX_TOKENS", "SAFETY", "RECITATION", "OTHER"):
                    event["finish_reason"] = finish
                text = "".join(part.get("text", "") for part in candidate.get("content", {}).get("parts", [])
                               if not part.get("thought"))
                parsed = json.loads(text)
                event["structured_response_valid"] = isinstance(parsed, dict) and parsed.get("ok") is True
                result["endpoint_available"] = event["structured_response_valid"]
                if not result["endpoint_available"]:
                    result.update(failure_stage=stage, failure_reason="response_contract_mismatch")
                usage = data.get("usageMetadata", {})
                event["usage"] = {name: usage[name] for name in
                    ("promptTokenCount", "candidatesTokenCount", "thoughtsTokenCount", "totalTokenCount")
                    if type(usage.get(name)) is int and usage[name] >= 0}
    except Exception as exc:
        # Raw exception messages/bodies may contain credentials or account identifiers.
        result["error_type"] = type(exc).__name__
        result["failure_stage"] = stage
    finally:
        key = None
    return result
