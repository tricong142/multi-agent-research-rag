"""Choose one local repair; the action vocabulary has no escalation route."""

from __future__ import annotations

from ..prompts import action_messages
from ..report_schema_validator import parse_claims, parse_critique, validate_action, validate_report
from ..schemas import CritiqueResult, ReportSchema, VerifiedClaim, WriterAction
from .backend import JsonGenerationBackend, parse_json_object


class ActionSelector:
    def __init__(self, backend: JsonGenerationBackend | None = None) -> None:
        self.backend = backend

    def select(
        self, claims: list[VerifiedClaim], intent: str, report: ReportSchema, critique: CritiqueResult
    ) -> WriterAction | None:
        claims = parse_claims(claims)
        report = validate_report(report, claims)
        critique = parse_critique(critique, report)
        violations = {review.sentence_id for review in critique.sentence_reviews if review.verdict != "supported"}
        if not violations:
            return None
        if self.backend is not None:
            action = validate_action(
                parse_json_object(self.backend.generate(action_messages(claims, intent, report, critique))),
                report,
                claims,
            )
            if action.sentence_id not in violations:
                raise ValueError("An action must target a sentence marked unsupported or uncertain.")
            return action
        by_id = {claim.claim_id: claim for claim in claims}
        # Preserve report order for reproducibility, preferring definite violations.
        definite = {review.sentence_id for review in critique.sentence_reviews if review.verdict == "unsupported"}
        sentence = next(item for item in report.sentences if item.sentence_id in (definite or violations))
        if sentence.claim_ids:
            replacement = " ".join(by_id[claim_id].text for claim_id in sentence.claim_ids)
            if " ".join(sentence.text.split()) != " ".join(replacement.split()):
                return validate_action(WriterAction(
                    action="rewrite_sentence", sentence_id=sentence.sentence_id,
                    claim_ids=list(sentence.claim_ids), replacement_text=replacement,
                    reason="Replace uncertain wording with the exact text of its existing verified claims.",
                ), report, claims)
        return validate_action(WriterAction(
            action="delete_sentence", sentence_id=sentence.sentence_id,
            reason="Remove a disputed sentence when exact-copy repair cannot improve it.",
        ), report, claims)
