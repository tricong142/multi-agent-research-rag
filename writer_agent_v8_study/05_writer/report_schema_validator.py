"""Structural/citation validation. A valid citation is NOT semantic entailment."""
from __future__ import annotations

import json
from typing import Any
from .schemas import CritiqueResult, ReportSchema, VerifiedClaim, WriterAction


def _unique(values: list[str], what: str) -> None:
    if len(values) != len(set(values)):
        raise ValueError(f"duplicate {what}")
    if any(not value.strip() for value in values):
        raise ValueError(f"blank {what}")


def _payload(value: Any) -> Any:
    if isinstance(value, str):
        def pairs(items):
            result = {}
            for key, item in items:
                if key in result:
                    raise ValueError(f"duplicate JSON key: {key}")
                result[key] = item
            return result
        def reject_constant(constant):
            raise ValueError(f"non-finite JSON value: {constant}")
        return json.loads(value, object_pairs_hook=pairs, parse_constant=reject_constant)
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    return value


def parse_claims(payload: Any) -> list[VerifiedClaim]:
    if not isinstance(payload, (list, tuple)):
        raise ValueError("verified_claims must be a list")
    claims = [VerifiedClaim.model_validate(_payload(item)) for item in payload]
    _unique([c.claim_id for c in claims], "claim_id")
    return claims


def validate_report(payload: Any, claims: list[VerifiedClaim]) -> ReportSchema:
    report = ReportSchema.model_validate(_payload(payload))
    pool = {c.claim_id for c in parse_claims(claims)}
    _unique([s.sentence_id for s in report.sentences], "sentence_id")
    # Non-evidence text cannot bypass sentence-level checking through a title or
    # limitations field. Only these neutral UI metadata values are permitted.
    if report.title != "Research report":
        raise ValueError("title must be the neutral literal 'Research report'")
    allowed = {
        "Insufficient verified claims to answer the intent.",
        "Some statements could not be verified within the internal retry budget.",
        "The available claims may not fully answer the intent.",
        "Writer input or model output could not be validated.",
    }
    if any(item not in allowed for item in report.limitations):
        raise ValueError("limitations must use the documented non-factual status messages")
    for sentence in report.sentences:
        if not sentence.text.strip():
            raise ValueError("blank sentence text")
        _unique(sentence.claim_ids, "citation")
        if not set(sentence.claim_ids) <= pool:
            raise ValueError(f"unknown claim reference in {sentence.sentence_id}")
    return report


def parse_critique(payload: Any, report: ReportSchema) -> CritiqueResult:
    critique = CritiqueResult.model_validate(_payload(payload))
    ids = [review.sentence_id for review in critique.sentence_reviews]
    _unique(ids, "critique sentence_id")
    if set(ids) != {s.sentence_id for s in report.sentences}:
        raise ValueError("critic must review every sentence exactly once")
    return critique


def validate_action(payload: Any, report: ReportSchema, claims: list[VerifiedClaim]) -> WriterAction:
    action = WriterAction.model_validate(_payload(payload))
    pool = {c.claim_id for c in parse_claims(claims)}
    sentence = next((s for s in report.sentences if s.sentence_id == action.sentence_id), None)
    if sentence is None:
        raise ValueError("action targets unknown sentence")
    _unique(action.claim_ids, "action citation")
    if not set(action.claim_ids) <= pool:
        raise ValueError("action cannot introduce new claims")
    if action.action == "delete_sentence":
        if action.claim_ids or action.replacement_text is not None:
            raise ValueError("delete_sentence cannot carry replacement content")
    elif action.action == "rewrite_sentence":
        if not action.claim_ids:
            raise ValueError("rewrite_sentence requires citations")
        if not set(action.claim_ids) <= set(sentence.claim_ids):
            raise ValueError("rewrite uses original citations; use reselect_claims to change them")
    else:
        if not action.claim_ids or set(action.claim_ids) & set(sentence.claim_ids):
            raise ValueError("reselect_claims must use OTHER claims from the existing pool")
    return action
