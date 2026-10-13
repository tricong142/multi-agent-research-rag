"""Rewrite locally using supplied claims; the critic checks free-form rewrites."""

from ..report_schema_validator import parse_claims, validate_action, validate_report
from ..schemas import ReportSchema, VerifiedClaim, WriterAction


def rewrite_sentence(report: ReportSchema, action: WriterAction, claims: list[VerifiedClaim]) -> ReportSchema:
    claims = parse_claims(claims)
    report = validate_report(report, claims)
    action = validate_action(action, report, claims)
    if action.action != "rewrite_sentence":
        raise ValueError("rewrite_sentence received a different action type.")
    original = next(sentence for sentence in report.sentences if sentence.sentence_id == action.sentence_id)
    claim_ids = list(action.claim_ids or original.claim_ids)
    if not claim_ids:
        raise ValueError("A rewritten sentence must cite an existing verified claim.")
    by_id = {claim.claim_id: claim for claim in claims}
    replacement = action.replacement_text
    if replacement is None:
        replacement = " ".join(by_id[claim_id].text for claim_id in claim_ids)
    if not replacement.strip():
        raise ValueError("A rewrite must contain non-empty text; use delete_sentence to remove it.")
    result = report.model_copy(deep=True)
    for sentence in result.sentences:
        if sentence.sentence_id == action.sentence_id:
            sentence.text = replacement
            sentence.claim_ids = claim_ids
    return validate_report(result, claims)
