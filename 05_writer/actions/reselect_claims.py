"""Replace a sentence with OTHER claims already present in the fixed claim pool."""

from ..report_schema_validator import parse_claims, validate_action, validate_report
from ..schemas import ReportSchema, VerifiedClaim, WriterAction


def reselect_claims(report: ReportSchema, action: WriterAction, claims: list[VerifiedClaim]) -> ReportSchema:
    claims = parse_claims(claims)
    report = validate_report(report, claims)
    action = validate_action(action, report, claims)
    if action.action != "reselect_claims":
        raise ValueError("reselect_claims received a different action type.")
    original = next(sentence for sentence in report.sentences if sentence.sentence_id == action.sentence_id)
    old_ids = set(original.claim_ids)
    available = [claim.claim_id for claim in claims if claim.claim_id not in old_ids]
    chosen = list(action.claim_ids) if action.claim_ids else available[:1]
    if not chosen:
        raise ValueError("No other existing verified claim is available for re-selection.")
    if old_ids.intersection(chosen):
        raise ValueError("reselect_claims must use other claims, excluding the sentence's current citations.")
    by_id = {claim.claim_id: claim for claim in claims}
    # Do not trust proposed replacement_text here. Re-selection is an exact-copy
    # operation, including when several existing claims are combined.
    replacement = " ".join(by_id[claim_id].text for claim_id in chosen)
    result = report.model_copy(deep=True)
    for sentence in result.sentences:
        if sentence.sentence_id == action.sentence_id:
            sentence.text = replacement
            sentence.claim_ids = chosen
    return validate_report(result, claims)
