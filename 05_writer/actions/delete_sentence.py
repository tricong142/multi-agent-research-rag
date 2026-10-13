"""Delete exactly the sentence named in a validated local action."""

from ..report_schema_validator import parse_claims, validate_action, validate_report
from ..schemas import ReportSchema, VerifiedClaim, WriterAction


def delete_sentence(report: ReportSchema, action: WriterAction, claims: list[VerifiedClaim]) -> ReportSchema:
    claims = parse_claims(claims)
    report = validate_report(report, claims)
    action = validate_action(action, report, claims)
    if action.action != "delete_sentence":
        raise ValueError("delete_sentence received a different action type.")
    result = report.model_copy(deep=True)
    result.sentences = [sentence for sentence in result.sentences if sentence.sentence_id != action.sentence_id]
    return validate_report(result, claims)
